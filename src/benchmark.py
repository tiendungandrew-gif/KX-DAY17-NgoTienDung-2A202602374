from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from typing import Any

from tabulate import tabulate

from agent_advanced import AdvancedAgent
from agent_baseline import BaselineAgent
from config import LabConfig, load_config


@dataclass
class BenchmarkRow:
    agent_name: str
    agent_tokens_only: int
    prompt_tokens_processed: int
    recall_score: float
    response_quality: float
    memory_growth_bytes: int
    compactions: int


def load_conversations(path: Path) -> list[dict[str, Any]]:
    """Read JSON conversations from disk."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def recall_points(answer: str, expected: list[str]) -> float:
    """Return fraction of expected facts present in answer (0.0 to 1.0)."""
    if not expected:
        return 1.0
    ans_lower = answer.lower()
    matched = sum(1 for exp in expected if exp.lower() in ans_lower)
    return round(matched / len(expected), 2)


def heuristic_quality(answer: str, expected: list[str]) -> float:
    """Lightweight quality score for offline evaluations."""
    if not answer or not answer.strip():
        return 0.0
    r_score = recall_points(answer, expected)
    quality = r_score * 0.7

    # Bonus for clear structure (bullets, colons, newlines)
    if any(mark in answer for mark in ["-", ":", "•", "\n"]):
        quality += 0.15
    # Bonus for appropriate length without verbosity
    if 20 <= len(answer) <= 450:
        quality += 0.15
    elif len(answer) > 0:
        quality += 0.10

    return min(1.0, round(quality, 2))


def run_agent_benchmark(
    agent_name: str,
    agent: BaselineAgent | AdvancedAgent,
    conversations: list[dict[str, Any]],
    config: LabConfig,
) -> BenchmarkRow:
    """Evaluate one agent over conversations."""
    total_agent_tokens = 0
    total_prompt_tokens = 0
    total_compactions = 0
    all_recall_scores: list[float] = []
    all_quality_scores: list[float] = []
    unique_users: set[str] = set()

    for conv in conversations:
        user_id = conv.get("user_id", "user")
        unique_users.add(user_id)
        thread_id = conv.get("id", "thread")

        # 1. Feed conversation turns in the main thread
        for turn in conv.get("turns", []):
            res = agent.reply(user_id=user_id, thread_id=thread_id, message=turn)
            total_agent_tokens += res.get("tokens", 0)
            total_prompt_tokens += res.get("prompt_tokens", 0)

        # Record compactions on this thread
        total_compactions += agent.compaction_count(thread_id)

        # 2. Ask recall questions in a fresh thread to test cross-session recall
        for idx, q_item in enumerate(conv.get("recall_questions", [])):
            recall_thread = f"{thread_id}_recall_{idx}"
            q_text = q_item.get("question", "")
            expected = q_item.get("expected_contains", [])

            res = agent.reply(user_id=user_id, thread_id=recall_thread, message=q_text)
            total_agent_tokens += res.get("tokens", 0)
            total_prompt_tokens += res.get("prompt_tokens", 0)

            ans = res.get("response", "")
            all_recall_scores.append(recall_points(ans, expected))
            all_quality_scores.append(heuristic_quality(ans, expected))

    # Memory growth across all unique users
    memory_growth_bytes = 0
    if hasattr(agent, "memory_file_size"):
        memory_growth_bytes = sum(agent.memory_file_size(u) for u in unique_users)

    avg_recall = round(sum(all_recall_scores) / len(all_recall_scores), 2) if all_recall_scores else 0.0
    avg_quality = round(sum(all_quality_scores) / len(all_quality_scores), 2) if all_quality_scores else 0.0

    return BenchmarkRow(
        agent_name=agent_name,
        agent_tokens_only=total_agent_tokens,
        prompt_tokens_processed=total_prompt_tokens,
        recall_score=avg_recall,
        response_quality=avg_quality,
        memory_growth_bytes=memory_growth_bytes,
        compactions=total_compactions,
    )


def format_rows(rows: list[BenchmarkRow]) -> str:
    """Format benchmark rows as a markdown table."""
    headers = [
        "Agent",
        "Agent tokens only",
        "Prompt tokens processed",
        "Cross-session recall",
        "Response quality",
        "Memory growth (bytes)",
        "Compactions",
    ]
    table_data = []
    for r in rows:
        table_data.append([
            r.agent_name,
            f"{r.agent_tokens_only:,}",
            f"{r.prompt_tokens_processed:,}",
            f"{r.recall_score * 100:.1f}%",
            f"{r.response_quality * 100:.1f}%",
            f"{r.memory_growth_bytes:,}",
            r.compactions,
        ])
    return tabulate(table_data, headers=headers, tablefmt="github")


def main() -> None:
    """Run both standard benchmark and long-context stress benchmark."""
    config = load_config(Path(__file__).resolve().parent.parent)

    standard_path = config.data_dir / "conversations.json"
    stress_path = config.data_dir / "advanced_long_context.json"

    standard_convs = load_conversations(standard_path)
    stress_convs = load_conversations(stress_path)

    print("================================================================================")
    print("DAY 17: MEMORY SYSTEMS FOR AI AGENT - BENCHMARK REPORT")
    print("================================================================================\n")

    # 1. Standard Benchmark Suite
    print("### 1. Standard Benchmark (data/conversations.json - 10 conversations)")
    profiles_dir = config.state_dir / "profiles"
    if profiles_dir.exists():
        shutil.rmtree(profiles_dir)
    profiles_dir.mkdir(parents=True, exist_ok=True)

    baseline_agent_std = BaselineAgent(config, force_offline=True)
    row_baseline_std = run_agent_benchmark("Baseline", baseline_agent_std, standard_convs, config)

    advanced_agent_std = AdvancedAgent(config, force_offline=True)
    row_advanced_std = run_agent_benchmark("Advanced", advanced_agent_std, standard_convs, config)

    print(format_rows([row_baseline_std, row_advanced_std]))
    print()

    # 2. Long-Context Stress Benchmark Suite
    print("### 2. Long-Context Stress Benchmark (data/advanced_long_context.json - 16 long turns)")
    if profiles_dir.exists():
        shutil.rmtree(profiles_dir)
    profiles_dir.mkdir(parents=True, exist_ok=True)

    baseline_agent_stress = BaselineAgent(config, force_offline=True)
    row_baseline_stress = run_agent_benchmark("Baseline", baseline_agent_stress, stress_convs, config)

    advanced_agent_stress = AdvancedAgent(config, force_offline=True)
    row_advanced_stress = run_agent_benchmark("Advanced", advanced_agent_stress, stress_convs, config)

    print(format_rows([row_baseline_stress, row_advanced_stress]))
    print("\n================================================================================")


if __name__ == "__main__":
    main()
