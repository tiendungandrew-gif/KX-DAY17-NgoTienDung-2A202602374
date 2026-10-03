from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config import LabConfig, load_config
from memory_store import estimate_tokens
from model_provider import build_chat_model


@dataclass
class SessionState:
    messages: list[dict[str, str]] = field(default_factory=list)
    token_usage: int = 0
    prompt_tokens_processed: int = 0


class BaselineAgent:
    """Agent A / Baseline Agent.

    Requirements:
    - Within-session memory only (keyed by thread_id)
    - No persistent `User.md`
    - Should forget long-term facts across new threads
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.sessions: dict[str, SessionState] = {}
        self.langchain_agent = None

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Return the agent response and token accounting."""
        if self.force_offline or not self._has_valid_credentials():
            return self._reply_offline(thread_id, message)

        try:
            agent = self._maybe_build_langchain_agent()
            if agent is None:
                return self._reply_offline(thread_id, message)
            return self._reply_live(thread_id, message)
        except Exception:
            return self._reply_offline(thread_id, message)

    def _has_valid_credentials(self) -> bool:
        provider = self.config.model.provider
        if provider in ("ollama", "custom"):
            return True
        return bool(self.config.model.api_key)

    def token_usage(self, thread_id: str) -> int:
        """Return cumulative agent token count for one thread."""
        session = self.sessions.get(thread_id)
        return session.token_usage if session else 0

    def prompt_token_usage(self, thread_id: str) -> int:
        """Estimate how much prompt context this baseline kept processing."""
        session = self.sessions.get(thread_id)
        return session.prompt_tokens_processed if session else 0

    def compaction_count(self, thread_id: str) -> int:
        """Baseline has no compact memory."""
        return 0

    def _reply_offline(self, thread_id: str, message: str) -> dict[str, Any]:
        """Deterministic offline behavior for Baseline Agent."""
        if thread_id not in self.sessions:
            self.sessions[thread_id] = SessionState()

        session = self.sessions[thread_id]
        session.messages.append({"role": "user", "content": message})

        # Baseline carries ALL previous raw messages in this session
        prompt_tokens = sum(estimate_tokens(m["content"]) for m in session.messages)
        session.prompt_tokens_processed += prompt_tokens

        # In a new/fresh thread (like cross-session recall test), session.messages has only this 1 message
        if len(session.messages) <= 1:
            reply_text = "Chào bạn, tôi chưa có thông tin về bạn trong phiên làm việc mới này."
        else:
            reply_text = f"Đã ghi nhận thông tin trong phiên: {message[:60]}..."

        reply_tokens = estimate_tokens(reply_text)
        session.token_usage += reply_tokens
        session.messages.append({"role": "assistant", "content": reply_text})

        return {
            "response": reply_text,
            "tokens": reply_tokens,
            "prompt_tokens": prompt_tokens,
        }

    def _reply_live(self, thread_id: str, message: str) -> dict[str, Any]:
        """Live reply using LangGraph / LangChain agent."""
        if thread_id not in self.sessions:
            self.sessions[thread_id] = SessionState()

        session = self.sessions[thread_id]
        session.messages.append({"role": "user", "content": message})
        prompt_tokens = sum(estimate_tokens(m["content"]) for m in session.messages)
        session.prompt_tokens_processed += prompt_tokens

        agent = self._maybe_build_langchain_agent()
        config = {"configurable": {"thread_id": thread_id}}
        result = agent.invoke({"messages": [("user", message)]}, config=config)

        messages = result.get("messages", [])
        if messages:
            last_message = messages[-1]
            reply_text = getattr(last_message, "content", str(last_message))
        else:
            reply_text = "Đã nhận tin nhắn."

        reply_tokens = estimate_tokens(reply_text)
        session.token_usage += reply_tokens
        session.messages.append({"role": "assistant", "content": reply_text})

        return {
            "response": reply_text,
            "tokens": reply_tokens,
            "prompt_tokens": prompt_tokens,
        }

    def _maybe_build_langchain_agent(self):
        """Wire `create_react_agent` + `MemorySaver`."""
        if self.langchain_agent is not None:
            return self.langchain_agent
        try:
            from langgraph.checkpoint.memory import MemorySaver
            from langgraph.prebuilt import create_react_agent

            model = build_chat_model(self.config.model)
            checkpointer = MemorySaver()
            self.langchain_agent = create_react_agent(model, tools=[], checkpointer=checkpointer)
            return self.langchain_agent
        except Exception:
            return None
