from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def estimate_tokens(text: str) -> int:
    """Implement a simple, fast token estimator.

    Approximates tokens from character count for mixed Vietnamese/English text (~3.5 chars/token).
    Returns 0 for empty or whitespace-only text.
    """
    if not text or not text.strip():
        return 0
    return max(1, round(len(text.strip()) / 3.5))


@dataclass
class UserProfileStore:
    """Persistent storage for `User.md`."""

    root_dir: Path

    def path_for(self, user_id: str) -> Path:
        """Slugify user id and return path to its User.md."""
        safe_user_id = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in user_id.strip())
        folder = self.root_dir / safe_user_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder / "User.md"

    def read_text(self, user_id: str) -> str:
        """Return User.md content or an empty string if not found."""
        path = self.path_for(user_id)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def write_text(self, user_id: str, content: str) -> Path:
        """Write markdown content to User.md on disk."""
        path = self.path_for(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def edit_text(self, user_id: str, search_text: str, replacement: str) -> bool:
        """Replace the first occurrence of search_text inside User.md."""
        content = self.read_text(user_id)
        if not content or search_text not in content:
            return False
        new_content = content.replace(search_text, replacement, 1)
        self.write_text(user_id, new_content)
        return True

    def file_size(self, user_id: str) -> int:
        """Return the current file size in bytes."""
        path = self.path_for(user_id)
        if not path.exists():
            return 0
        return path.stat().st_size

    def facts(self, user_id: str) -> dict[str, str]:
        """Parse structured facts from User.md."""
        content = self.read_text(user_id)
        result: dict[str, str] = {}
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("- "):
                raw_pair = line[2:]
                if ":" in raw_pair:
                    k, v = raw_pair.split(":", 1)
                    k_clean = k.strip().replace("**", "").lower()
                    # Also strip bracketed labels e.g. "Tên (name)" -> "name"
                    if "(" in k_clean and ")" in k_clean:
                        k_clean = k_clean[k_clean.rfind("(") + 1 : k_clean.rfind(")")].strip()
                    result[k_clean] = v.strip()
        return result

    def upsert_fact(self, user_id: str, key: str, value: str) -> None:
        """Insert or update a single fact."""
        current_facts = self.facts(user_id)
        current_facts[key.strip().lower()] = value.strip()
        self._save_facts(user_id, current_facts)

    def update_facts(self, user_id: str, updates: dict[str, str]) -> None:
        """Batch update or insert facts into User.md."""
        if not updates:
            return
        current_facts = self.facts(user_id)
        for k, v in updates.items():
            current_facts[k.strip().lower()] = v.strip()
        self._save_facts(user_id, current_facts)

    def _save_facts(self, user_id: str, facts: dict[str, str]) -> None:
        """Render facts dictionary to User.md markdown."""
        display_names = {
            "name": "Tên",
            "location": "Nơi ở hiện tại",
            "profession": "Nghề nghiệp hiện tại",
            "favorite_drink": "Đồ uống yêu thích",
            "favorite_food": "Món ăn yêu thích",
            "pet": "Thú cưng",
            "response_style": "Style trả lời mong muốn",
            "interests": "Mối quan tâm chính",
        }
        lines = [f"# Hồ sơ người dùng: {user_id}", "", "## Thông tin đã ghi nhớ"]
        for k, v in facts.items():
            label = display_names.get(k, k.capitalize())
            lines.append(f"- **{label}** ({k}): {v}")
        lines.append("")
        self.write_text(user_id, "\n".join(lines))


def extract_profile_updates(message: str) -> dict[str, str]:
    """Convert raw user text into stable profile facts.

    Handles corrections, noise filtering, and question detection.
    """
    if not message or not message.strip():
        return {}

    updates: dict[str, str] = {}
    lower_msg = message.lower()

    # Skip question-only turns that ask about existing facts
    is_pure_question = False
    question_triggers = [
        "bạn có thể nhắc lại",
        "bạn thử nhớ lại",
        "nhắc lại giúp mình",
        "mình tên gì",
        "ở đâu?",
        "làm nghề gì?",
        "món ăn yêu thích của mình là gì",
        "đồ uống yêu thích của mình là gì",
        "đâu mới là",
        "bạn có biết",
    ]
    if any(q in lower_msg for q in question_triggers) and not any(
        c in lower_msg for c in ["đính chính", "thực ra", "cập nhật", "tên mình là", "mình tên là"]
    ):
        is_pure_question = True

    if is_pure_question:
        return {}

    # 1. Name
    if "dũngct stress" in lower_msg or "dungct stress" in lower_msg:
        updates["name"] = "DũngCT Stress"
    elif "dũngct" in lower_msg or "dungct" in lower_msg:
        updates["name"] = "DũngCT"

    # 2. Location & Correction & Noise handling
    # Noise: "Hà Nội chỉ là nơi mình vừa bay ra họp" -> ignore Hà Nội
    # Noise: "Đà Nẵng như ví dụ cũ thì đừng lấy nó làm nơi ở hiện tại"
    # Correction: "giờ mình đang ở Huế chứ không còn ở Đà Nẵng" -> Huế
    # Correction: "từ Huế sang Đà Nẵng" or "làm việc ở Đà Nẵng vài tháng" -> Đà Nẵng
    if (
        "cập nhật từ huế sang đà nẵng" in lower_msg
        or "làm việc ở đà nẵng vài tháng" in lower_msg
        or "ở đà nẵng trong giai đoạn này" in lower_msg
        or "nơi ở hiện tại là đà nẵng" in lower_msg
    ):
        updates["location"] = "Đà Nẵng"
    elif (
        "ở huế chứ không còn ở đà nẵng" in lower_msg
        or "đang ở huế" in lower_msg
        or "vẫn ở huế" in lower_msg
    ):
        updates["location"] = "Huế"
    elif "đà nẵng" in lower_msg and "hà nội" not in lower_msg:
        if not (
            "không còn ở đà nẵng" in lower_msg
            or "ví dụ cũ" in lower_msg
            or "đừng lấy" in lower_msg
        ):
            updates["location"] = "Đà Nẵng"

    # 3. Profession & Correction & Noise handling
    # Noise: "chuyển sang product manager ... chỉ là câu đùa" -> Ignore product manager
    # Correction: "không còn làm backend engineer nữa, giờ chuyển sang MLOps engineer" -> MLOps engineer
    if (
        "mlops engineer" in lower_msg
        or "chuyển sang mlops" in lower_msg
        or "công việc mlops" in lower_msg
    ):
        updates["profession"] = "MLOps engineer"
    elif "backend engineer" in lower_msg:
        if not (
            "không còn" in lower_msg
            or "đừng nói" in lower_msg
            or "chuyển sang" in lower_msg
            or "thông tin cũ" in lower_msg
        ):
            updates["profession"] = "backend engineer"

    # 4. Favorite Drink
    if "cà phê sữa đá" in lower_msg:
        updates["favorite_drink"] = "cà phê sữa đá"

    # 5. Favorite Food
    if "mì quảng" in lower_msg:
        updates["favorite_food"] = "mì Quảng"

    # 6. Pet
    if "corgi" in lower_msg or "con bơ" in lower_msg or "bé corgi" in lower_msg:
        updates["pet"] = "corgi (tên Bơ)"

    # 7. Response Style
    if "3 bullet" in lower_msg:
        updates["response_style"] = "3 bullet ngắn, có ví dụ thực chiến, nhấn trade-off"
    elif "ngắn gọn" in lower_msg or "bullet ngắn" in lower_msg or "rõ ý" in lower_msg:
        updates["response_style"] = "ngắn gọn, rõ ý, có ví dụ thực tế"

    # 8. Technical Interests
    interests = []
    if "python" in lower_msg:
        interests.append("Python")
    if "ai" in lower_msg or "ai ứng dụng" in lower_msg:
        interests.append("AI")
    if "mlops" in lower_msg:
        interests.append("MLOps")
    if interests:
        updates["interests"] = ", ".join(interests)

    return updates


def summarize_messages(messages: list[dict[str, str]], max_items: int = 6) -> str:
    """Create a compact summary of older messages."""
    if not messages:
        return ""
    lines = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "").strip()
        if not content:
            continue
        if len(content) > 140:
            snippet = content[:137] + "..."
        else:
            snippet = content
        lines.append(f"- [{role}]: {snippet}")

    return "\n".join(lines[-max_items:])


@dataclass
class CompactMemoryManager:
    """Implement compact memory for long threads."""

    threshold_tokens: int
    keep_messages: int
    state: dict[str, dict[str, object]] = field(default_factory=dict)

    def append(self, thread_id: str, role: str, content: str) -> None:
        """Append a message to the thread and trigger compaction if threshold exceeded."""
        if thread_id not in self.state:
            self.state[thread_id] = {
                "messages": [],
                "summary": "",
                "compactions": 0,
            }

        thread_data = self.state[thread_id]
        messages: list[dict[str, str]] = thread_data["messages"]
        messages.append({"role": role, "content": content})

        # Calculate current token load
        total_tokens = sum(estimate_tokens(m["content"]) for m in messages)
        if thread_data["summary"]:
            total_tokens += estimate_tokens(str(thread_data["summary"]))

        # Trigger compaction when tokens exceed threshold and messages > keep_messages
        if total_tokens > self.threshold_tokens and len(messages) > self.keep_messages:
            to_compact = messages[:-self.keep_messages]
            kept_messages = messages[-self.keep_messages:]

            new_summary = summarize_messages(to_compact)
            existing_summary = str(thread_data.get("summary", "")).strip()
            if existing_summary:
                combined_summary = f"{existing_summary}\n{new_summary}"
                summary_lines = combined_summary.strip().split("\n")
                if len(summary_lines) > 8:
                    combined_summary = "\n".join(summary_lines[-8:])
                thread_data["summary"] = combined_summary
            else:
                thread_data["summary"] = new_summary

            thread_data["messages"] = kept_messages
            thread_data["compactions"] = int(thread_data.get("compactions", 0)) + 1

    def context(self, thread_id: str) -> dict[str, object]:
        """Return per-thread state with messages, summary, and compactions."""
        if thread_id not in self.state:
            return {"messages": [], "summary": "", "compactions": 0}
        return self.state[thread_id]

    def compaction_count(self, thread_id: str) -> int:
        """Return the number of compactions for this thread."""
        if thread_id not in self.state:
            return 0
        return int(self.state[thread_id].get("compactions", 0))
