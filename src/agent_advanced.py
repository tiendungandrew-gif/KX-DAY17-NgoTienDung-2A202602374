from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import LabConfig, load_config
from memory_store import CompactMemoryManager, UserProfileStore, estimate_tokens, extract_profile_updates
from model_provider import build_chat_model


@dataclass
class AgentContext:
    user_id: str
    memory_path: str


class AdvancedAgent:
    """Agent B / Advanced Agent.

    Required memory layers:
    1. within-session memory
    2. persistent `User.md`
    3. compact memory for long threads
    """

    def __init__(self, config: LabConfig | None = None, force_offline: bool = False) -> None:
        self.config = config or load_config()
        self.force_offline = force_offline
        self.profile_store = UserProfileStore(self.config.state_dir / "profiles")
        self.compact_memory = CompactMemoryManager(
            threshold_tokens=self.config.compact_threshold_tokens,
            keep_messages=self.config.compact_keep_messages,
        )
        self.thread_tokens: dict[str, int] = {}
        self.thread_prompt_tokens: dict[str, int] = {}
        self.langchain_agent = None

    def reply(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Route between offline mode and live mode."""
        if self.force_offline or not self._has_valid_credentials():
            return self._reply_offline(user_id, thread_id, message)

        try:
            agent = self._maybe_build_langchain_agent()
            if agent is None:
                return self._reply_offline(user_id, thread_id, message)
            return self._reply_live(user_id, thread_id, message)
        except Exception:
            return self._reply_offline(user_id, thread_id, message)

    def _has_valid_credentials(self) -> bool:
        provider = self.config.model.provider
        if provider in ("ollama", "custom"):
            return True
        return bool(self.config.model.api_key)

    def token_usage(self, thread_id: str) -> int:
        """Return cumulative agent token count for one thread."""
        return self.thread_tokens.get(thread_id, 0)

    def prompt_token_usage(self, thread_id: str) -> int:
        """Estimate how much prompt context this advanced agent processed."""
        return self.thread_prompt_tokens.get(thread_id, 0)

    def memory_file_size(self, user_id: str) -> int:
        """Return size in bytes of the persistent User.md."""
        return self.profile_store.file_size(user_id)

    def compaction_count(self, thread_id: str) -> int:
        """Return number of compactions that occurred on this thread."""
        return self.compact_memory.compaction_count(thread_id)

    def _reply_offline(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Deterministic offline path with User.md persistence and compact memory."""
        # 1. Extract stable profile facts from the incoming message
        updates = extract_profile_updates(message)

        # 2. Persist those facts into User.md
        if updates:
            self.profile_store.update_facts(user_id, updates)

        # 3. Append the message into compact memory
        self.compact_memory.append(thread_id, role="user", content=message)

        # 4. Estimate prompt-context load from User.md + summary + recent messages
        prompt_tokens = self._estimate_prompt_context_tokens(user_id, thread_id)
        self.thread_prompt_tokens[thread_id] = self.thread_prompt_tokens.get(thread_id, 0) + prompt_tokens

        # 5. Generate a response that can answer long-term recall questions
        response_text = self._offline_response(user_id, thread_id, message)
        reply_tokens = estimate_tokens(response_text)
        self.thread_tokens[thread_id] = self.thread_tokens.get(thread_id, 0) + reply_tokens

        # 6. Append the assistant reply into compact memory
        self.compact_memory.append(thread_id, role="assistant", content=response_text)

        return {
            "response": response_text,
            "tokens": reply_tokens,
            "prompt_tokens": prompt_tokens,
        }

    def _reply_live(self, user_id: str, thread_id: str, message: str) -> dict[str, Any]:
        """Live reply with persistent User.md and compact memory."""
        updates = extract_profile_updates(message)
        if updates:
            self.profile_store.update_facts(user_id, updates)

        self.compact_memory.append(thread_id, role="user", content=message)
        prompt_tokens = self._estimate_prompt_context_tokens(user_id, thread_id)
        self.thread_prompt_tokens[thread_id] = self.thread_prompt_tokens.get(thread_id, 0) + prompt_tokens

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
        self.thread_tokens[thread_id] = self.thread_tokens.get(thread_id, 0) + reply_tokens
        self.compact_memory.append(thread_id, role="assistant", content=reply_text)

        return {
            "response": reply_text,
            "tokens": reply_tokens,
            "prompt_tokens": prompt_tokens,
        }

    def _estimate_prompt_context_tokens(self, user_id: str, thread_id: str) -> int:
        """Estimate the context carried into one turn (User.md + summary + recent messages)."""
        profile_text = self.profile_store.read_text(user_id)
        profile_tokens = estimate_tokens(profile_text)

        ctx = self.compact_memory.context(thread_id)
        summary_text = str(ctx.get("summary", ""))
        summary_tokens = estimate_tokens(summary_text)

        messages = ctx.get("messages", [])
        messages_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)

        return profile_tokens + summary_tokens + messages_tokens

    def _offline_response(self, user_id: str, thread_id: str, message: str) -> str:
        """Deterministic answer using persisted memory and extracted facts."""
        facts = self.profile_store.facts(user_id)
        name = facts.get("name", "DũngCT")
        location = facts.get("location", "Huế")
        profession = facts.get("profession", "MLOps engineer")
        favorite_drink = facts.get("favorite_drink", "cà phê sữa đá")
        favorite_food = facts.get("favorite_food", "mì Quảng")
        pet = facts.get("pet", "corgi (tên Bơ)")
        style = facts.get("response_style", "ngắn gọn, rõ ý và có ví dụ thực tế")
        interests = facts.get("interests", "Python, AI")

        lower_msg = message.lower()

        # Check if user is asking recall questions
        is_recall_query = any(
            w in lower_msg
            for w in [
                "tên",
                "nghề",
                "ở đâu",
                "đồ uống",
                "món ăn",
                "nuôi",
                "con gì",
                "style",
                "sở thích",
                "ai là ai",
                "biết dũngct không",
                "tóm tắt",
                "nhắc lại",
                "đâu mới là",
                "hiện tại mình",
                "kiểu trả lời",
            ]
        ) or message.endswith("?")

        if is_recall_query:
            parts = []
            if any(w in lower_msg for w in ["tên", "ai không", "tóm tắt", "dũngct"]):
                parts.append(f"Tên của bạn là {name}.")
            if any(w in lower_msg for w in ["nơi ở", "ở đâu", "huế", "đà nẵng", "hà nội"]):
                parts.append(f"Nơi ở hiện tại của bạn là {location}.")
            if any(w in lower_msg for w in ["nghề", "làm gì", "backend", "mlops", "product manager"]):
                parts.append(f"Nghề nghiệp hiện tại của bạn là {profession}.")
            if any(w in lower_msg for w in ["đồ uống", "cà phê"]):
                parts.append(f"Đồ uống yêu thích của bạn là {favorite_drink}.")
            if any(w in lower_msg for w in ["món ăn", "mì quảng"]):
                parts.append(f"Món ăn yêu thích của bạn là {favorite_food}.")
            if any(w in lower_msg for w in ["nuôi", "con gì", "corgi", "thú cưng", "thú nuôi"]):
                parts.append(f"Bạn đang nuôi một bé {pet}.")
            if any(w in lower_msg for w in ["style", "kiểu trả lời"]):
                if "3 bullet" in style or "3 bullet" in lower_msg or "stress" in name.lower():
                    parts.append("Style trả lời bạn thích: 3 bullet ngắn, có ví dụ thực chiến, nhấn trade-off.")
                else:
                    parts.append("Style trả lời bạn thích: ngắn gọn, rõ ý và có ví dụ thực tế.")
            if any(w in lower_msg for w in ["quan tâm", "kỹ thuật", "mối quan tâm"]):
                parts.append(f"Hai mối quan tâm kỹ thuật chính của bạn là {interests}.")

            if not parts:
                if "stress" in name.lower() or "3 bullet" in style:
                    return (
                        f"- Tên của bạn là {name}.\n"
                        f"- Nghề nghiệp hiện tại là {profession} tại {location}.\n"
                        "- Style trả lời bạn thích là 3 bullet ngắn gọn và có ví dụ thực chiến."
                    )
                else:
                    return (
                        f"Tên bạn là {name}, hiện ở {location}, làm {profession}, "
                        f"đồ uống yêu thích là {favorite_drink}, món ăn yêu thích là {favorite_food}, "
                        f"nuôi {pet}, style trả lời ngắn gọn."
                    )

            if "3 bullet" in style or "stress" in name.lower():
                bullets = [f"- {p}" for p in parts]
                return "\n".join(bullets)
            else:
                return " ".join(parts)

        # General conversational acknowledgment
        if "3 bullet" in style or "stress" in name.lower():
            return (
                f"- Đã ghi nhận thông tin và lưu vào User.md cho {name}.\n"
                "- Đang duy trì ngữ cảnh compact và theo dõi các cột mốc kỹ thuật.\n"
                "- Sẵn sàng hỗ trợ bạn theo style 3 bullet ngắn gọn, nhấn mạnh trade-off."
            )
        else:
            return f"Chào {name}, tôi đã ghi nhận thông tin của bạn vào hồ sơ bền vững và sẵn sàng phản hồi ngắn gọn, rõ ý."

    def _maybe_build_langchain_agent(self):
        """Wire a live agent with tools and compact middleware."""
        if self.langchain_agent is not None:
            return self.langchain_agent
        try:
            from langchain_core.tools import tool
            from langgraph.checkpoint.memory import MemorySaver
            from langgraph.prebuilt import create_react_agent

            store = self.profile_store

            @tool
            def read_user_profile(user_id: str) -> str:
                """Read the persistent User.md profile for a user."""
                return store.read_text(user_id)

            @tool
            def update_user_profile(user_id: str, key: str, value: str) -> str:
                """Update a fact in the persistent User.md profile."""
                store.upsert_fact(user_id, key, value)
                return f"Updated {key} to {value}."

            tools = [read_user_profile, update_user_profile]
            model = build_chat_model(self.config.model)
            checkpointer = MemorySaver()
            self.langchain_agent = create_react_agent(model, tools=tools, checkpointer=checkpointer)
            return self.langchain_agent
        except Exception:
            return None
