"""The JARVIS agent loop.

Connects Gemini function-calling to the local tool registry through the
permission/confirmation gate, drives multi-step tasks, records results into
session memory, and returns the assistant's final spoken text. This is the
"decide -> act -> observe -> continue" core; it never trusts Gemini to execute
anything directly.
"""
from __future__ import annotations

from dataclasses import dataclass

from config.settings import Settings
from ai.gemini_client import GeminiClient
from core.conversation import ChatMessage, ChatPart, Conversation
from core.context import ContextManager
from core.events import CancellationToken, TaskCancelled
from core.executor import ToolExecutor
from core.logging_setup import get_logger
from core.memory import MemoryManager
from core.permissions import PermissionManager
from core.planner import Planner, Task, TaskStatus
from safety.confirmation import ConfirmationManager
from safety.validator import describe_action
from tools.base import ToolCall
from tools.registry import ToolRegistry
from ai.prompts import system_instruction

logger = get_logger("core.agent")

MAX_ITERATIONS = 12


@dataclass
class AgentResult:
    text: str
    awaiting_confirmation: bool = False
    cancelled: bool = False


class Agent:
    def __init__(self, settings: Settings, client: GeminiClient, registry: ToolRegistry,
                 memory: MemoryManager) -> None:
        self.settings = settings
        self.client = client
        self.registry = registry
        self.memory = memory
        self.context = ContextManager(settings, memory.short_term)
        self.permissions = PermissionManager(settings, registry)
        self.executor = ToolExecutor(registry, memory.short_term, settings)
        self.confirmation = ConfirmationManager()
        self.planner = Planner()
        self.conversation = Conversation()
        self.task: Task | None = None
        self._pending_calls: list[dict] | None = None

    # --- public -------------------------------------------------------------
    def handle_text(self, user_text: str, token: CancellationToken | None = None) -> AgentResult:
        token = token or CancellationToken()
        user_text = (user_text or "").strip()
        if not user_text:
            return AgentResult("I didn't catch that.")

        # 1) resolve an outstanding confirmation first
        if self._pending_calls is not None:
            decision = self.confirmation.interpret(user_text)
            if decision == "yes":
                self._commit_calls(self._pending_calls, cancelled=False, token=token)
                self._pending_calls = None
                return self._run_loop(token)
            if decision == "no":
                self._commit_calls(self._pending_calls, cancelled=True, token=token)
                self._pending_calls = None
                return self._run_loop(token)
            # changed the subject -> abandon the pending batch, then treat as new
            self._commit_calls(self._pending_calls, cancelled=True, token=token)
            self._pending_calls = None

        # 2) new instruction
        self.conversation.add_user(user_text)
        self.context.keep_recent(self.conversation)
        self.task = self.planner.new_task(user_text)
        self.memory.short_term.current_task = user_text
        return self._run_loop(token)

    def cancel(self) -> None:
        self._pending_calls = None
        if self.task and not self.task.is_terminal:
            self.task.status = TaskStatus.CANCELLED

    # --- internals ----------------------------------------------------------
    def _system_instruction(self) -> str:
        parts = [system_instruction(self.settings.assistant_name)]
        structured = self.context.structured_context()
        if structured:
            parts.append(structured)
        if self.conversation.summary:
            parts.append(f"[EARLIER CONTEXT]\n{self.conversation.summary}")
        return "\n\n".join(parts)

    def _run_loop(self, token: CancellationToken) -> AgentResult:
        schemas = self.registry.schemas()
        for _ in range(MAX_ITERATIONS):
            try:
                token.check()
            except TaskCancelled:
                if self.task:
                    self.task.status = TaskStatus.CANCELLED
                return AgentResult("Cancelled.", cancelled=True)

            try:
                response = self.client.respond(
                    self.conversation.messages, schemas, self._system_instruction()
                )
            except TaskCancelled:
                raise
            except Exception as exc:  # noqa: BLE001 - AI failure must not crash the loop
                logger.exception("Gemini request failed")
                msg = f"I ran into an issue reaching my reasoning service: {_friendly(exc)}"
                return AgentResult(msg)

            if response.kind == "text":
                text = response.text or "I'm not sure how to help with that yet."
                self.conversation.add_model_text(text)
                if self.task:
                    self.task.status = TaskStatus.COMPLETED
                self.memory.short_term.last_assistant_text = text
                return AgentResult(text)

            calls = response.function_calls
            risky = next(
                (c for c in calls if self.permissions.needs_confirmation(c["name"], c["args"])),
                None,
            )
            if risky is not None:
                self._pending_calls = calls
                if self.task:
                    self.task.status = TaskStatus.WAITING_FOR_CONFIRMATION
                question = (
                    f"I need to {describe_action(risky['name'], risky['args'])}. "
                    f"Should I continue?"
                )
                logger.info("Confirmation required: %s", question)
                return AgentResult(question, awaiting_confirmation=True)

            self._commit_calls(calls, cancelled=False, token=token)

        msg = "I reached my step limit for that request. Could you break it down a little?"
        self.conversation.add_model_text(msg)
        return AgentResult(msg)

    def _commit_calls(self, calls: list[dict], cancelled: bool, token: CancellationToken) -> None:
        """Add the model's function-call turn, execute, then add responses."""
        model_parts = [
            ChatPart(function_call={"name": c["name"], "args": c["args"], "id": c.get("id")})
            for c in calls
        ]
        self.conversation.messages.append(ChatMessage(role="model", parts=model_parts))

        response_parts = []
        for call in calls:
            tool_call = ToolCall(name=call["name"], arguments=call["args"])
            if cancelled and self.permissions.needs_confirmation(call["name"], call["args"]):
                result_dict = {
                    "success": False, "tool": call["name"], "result": None,
                    "error": {"type": "USER_DECLINED", "message": "The user did not confirm this action."},
                }
            else:
                try:
                    result = self.executor.execute(tool_call, token)
                except TaskCancelled:
                    raise
                result_dict = result.to_dict()
            response_parts.append(ChatPart(
                function_response={"name": call["name"], "response": result_dict, "id": call.get("id")}
            ))
        self.conversation.messages.append(ChatMessage(role="user", parts=response_parts))


def _friendly(exc: Exception) -> str:
    from core.exceptions import AuthenticationError, RateLimitError

    if isinstance(exc, AuthenticationError):
        return "the API key seems invalid. Please check your .env GEMINI_API_KEY."
    if isinstance(exc, RateLimitError):
        return "I'm being rate limited. Let's wait a moment and try again."
    return str(exc)[:200]
