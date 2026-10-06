"""Adapter: translate JARVIS tools/conversation into google-genai SDK types.

Centralizing the `google.genai` coupling here means the agent, registry and
safety layers never import the SDK directly.
"""
from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types

from core.conversation import ChatMessage, ChatPart

_TYPE_MAP = {
    "string": types.Type.STRING,
    "integer": types.Type.INTEGER,
    "number": types.Type.NUMBER,
    "boolean": types.Type.BOOLEAN,
    "array": types.Type.ARRAY,
    "object": types.Type.OBJECT,
}


def _to_schema(node: dict[str, Any]) -> types.Schema:
    kwargs: dict[str, Any] = {}
    t = node.get("type")
    if t in _TYPE_MAP:
        kwargs["type"] = _TYPE_MAP[t]
    if node.get("description"):
        kwargs["description"] = node["description"]
    if node.get("properties"):
        kwargs["properties"] = {k: _to_schema(v) for k, v in node["properties"].items()}
    if node.get("required"):
        kwargs["required"] = node["required"]
    if node.get("items"):
        kwargs["items"] = _to_schema(node["items"])
    return types.Schema(**kwargs)


def build_tools(schemas: list[dict[str, Any]]) -> list[types.Tool]:
    declarations = [
        types.FunctionDeclaration(
            name=s["name"],
            description=s["description"],
            parameters=_to_schema(s.get("parameters", {"type": "object"})),
        )
        for s in schemas
    ]
    return [types.Tool(function_declarations=declarations)]


def _part_from_chat_part(part: ChatPart) -> types.Part:
    if part.function_call is not None:
        return types.Part(function_call=types.FunctionCall(
            name=part.function_call["name"],
            args=part.function_call.get("args", {}),
        ))
    if part.function_response is not None:
        return types.Part(function_response=types.FunctionResponse(
            name=part.function_response["name"],
            response=part.function_response.get("response", {}),
        ))
    return types.Part.from_text(text=part.text or "")


def to_contents(messages: list[ChatMessage]) -> list[types.Content]:
    contents: list[types.Content] = []
    for message in messages:
        contents.append(types.Content(role=message.role,
                                      parts=[_part_from_chat_part(p) for p in message.parts]))
    return contents
