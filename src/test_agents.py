from __future__ import annotations

from pathlib import Path

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import LabConfig
from memory_store import UserProfileStore
from model_provider import ProviderConfig


def make_config(tmp_path: Path) -> LabConfig:
    """Build an isolated config for tests with low compaction threshold."""
    repo_root = Path(__file__).resolve().parent.parent
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "profiles").mkdir(parents=True, exist_ok=True)

    dummy_model = ProviderConfig(provider="openai", model_name="gpt-4o-mini", temperature=0.0)

    return LabConfig(
        base_dir=tmp_path,
        data_dir=repo_root / "data",
        state_dir=state_dir,
        compact_threshold_tokens=80,
        compact_keep_messages=2,
        model=dummy_model,
        judge_model=dummy_model,
    )


def test_user_markdown_read_write_edit(tmp_path: Path) -> None:
    """Verify `User.md` can be created, updated, and edited."""
    profiles_dir = tmp_path / "profiles"
    store = UserProfileStore(profiles_dir)

    # 1. Write initial text
    file_path = store.write_text("test_user", "# Hồ sơ ban đầu\n- name: DũngCT\n- location: Đà Nẵng")
    assert file_path.exists()
    assert store.file_size("test_user") > 0

    # 2. Read text back
    content = store.read_text("test_user")
    assert "DũngCT" in content
    assert "Đà Nẵng" in content

    # 3. Edit text (replace Đà Nẵng with Huế)
    changed = store.edit_text("test_user", "Đà Nẵng", "Huế")
    assert changed is True
    updated_content = store.read_text("test_user")
    assert "Huế" in updated_content
    assert "Đà Nẵng" not in updated_content

    # 4. Structured fact updates
    store.update_facts("test_user", {"profession": "MLOps engineer"})
    facts = store.facts("test_user")
    assert facts.get("profession") == "MLOps engineer"


def test_compact_trigger(tmp_path: Path) -> None:
    """Verify long threads trigger compaction in AdvancedAgent."""
    config = make_config(tmp_path)
    agent = AdvancedAgent(config=config, force_offline=True)

    thread_id = "test_compact_thread"
    assert agent.compaction_count(thread_id) == 0

    # Send messages exceeding the 80 token threshold and 2 kept messages
    for i in range(6):
        agent.reply(
            user_id="test_user",
            thread_id=thread_id,
            message=f"Lượt {i}: Đây là một tin nhắn có nội dung dài để kích hoạt bộ nhớ compact của agent.",
        )

    # Compactions should have occurred
    assert agent.compaction_count(thread_id) > 0
    ctx = agent.compact_memory.context(thread_id)
    assert ctx["summary"] != ""
    assert len(ctx["messages"]) <= 3


def test_cross_session_recall(tmp_path: Path) -> None:
    """Verify advanced agent remembers facts across new threads while baseline forgets."""
    config = make_config(tmp_path)
    baseline = BaselineAgent(config=config, force_offline=True)
    advanced = AdvancedAgent(config=config, force_offline=True)

    user_id = "cross_session_user"

    # Thread 1: user introduces stable profile facts
    intro_message = "Chào bạn, mình tên là DũngCT. Mình ở Huế và đồ uống yêu thích là cà phê sữa đá."
    baseline.reply(user_id, "session_1", intro_message)
    advanced.reply(user_id, "session_1", intro_message)

    # Thread 2: ask recall question in a completely fresh session
    recall_question = "Mình tên gì và đồ uống yêu thích là gì?"
    res_baseline = baseline.reply(user_id, "session_2", recall_question)["response"]
    res_advanced = advanced.reply(user_id, "session_2", recall_question)["response"]

    # Baseline has no User.md, so in session_2 it must forget
    assert "DũngCT" not in res_baseline
    assert "cà phê sữa đá" not in res_baseline

    # Advanced uses persistent User.md, so in session_2 it recalls accurately
    assert "DũngCT" in res_advanced
    assert "cà phê sữa đá" in res_advanced


def test_compact_reduces_prompt_load_on_long_thread(tmp_path: Path) -> None:
    """Compare prompt load of baseline vs advanced on a long thread."""
    config = make_config(tmp_path)
    baseline = BaselineAgent(config=config, force_offline=True)
    advanced = AdvancedAgent(config=config, force_offline=True)

    user_id = "stress_user"
    thread_id = "long_thread_comparison"

    # Sequence of long conversational turns
    turns = [
        f"Lượt {i}: Thông tin kỹ thuật chi tiết về kiến trúc AI memory, quản lý token và tối ưu ngữ cảnh dài với nhiều dữ kiện."
        for i in range(12)
    ]

    for turn in turns:
        baseline.reply(user_id, thread_id, turn)
        advanced.reply(user_id, thread_id, turn)

    baseline_prompt_tokens = baseline.prompt_token_usage(thread_id)
    advanced_prompt_tokens = advanced.prompt_token_usage(thread_id)

    # Advanced must trigger compaction
    assert advanced.compaction_count(thread_id) > 0

    # Advanced prompt tokens processed should be lower than baseline due to compaction
    assert advanced_prompt_tokens < baseline_prompt_tokens
