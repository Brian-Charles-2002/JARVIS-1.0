"""Context manager: structured session context and bounded history."""
from core.conversation import Conversation
from core.context import ContextManager
from memory.short_term import ShortTermMemory


def test_structured_context_lists_state(settings):
    st = ShortTermMemory()
    st.last_created_folder = "C:/Desktop/Projects"
    st.current_application = "chrome"
    cm = ContextManager(settings, st)
    text = cm.structured_context()
    assert "last_created_folder" in text
    assert "current_application" in text


def test_empty_state_gives_no_context(settings):
    cm = ContextManager(settings, ShortTermMemory())
    assert cm.structured_context() == ""


def test_keep_recent_folds_older_turns(settings):
    from dataclasses import replace

    settings = replace(settings, context_summary_threshold=6, max_recent_messages=2)
    conv = Conversation()
    for i in range(12):
        conv.add_user(f"message {i}")
    cm = ContextManager(settings, ShortTermMemory())
    cm.keep_recent(conv)
    assert len(conv.messages) == 2
    assert conv.summary and "message" in conv.summary
