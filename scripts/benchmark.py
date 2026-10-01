"""Benchmark minimal : une question, des compteurs, un succès ou un échec.

Usage : python scripts/benchmark.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent import run_agent
from src.config import get_settings

QUESTIONS_PATH = ROOT / "data" / "evaluation_questions.json"
OUTPUT_PATH = ROOT / "outputs" / "benchmark_last.json"


def main() -> None:
    settings = get_settings()
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    results = []
    print(f"[BENCH] model={settings.model_name} base_url={settings.openai_base_url}")
    for item in questions:
        started = time.perf_counter()
        record = {
            "id": item["id"],
            "question": item["question"],
            "model": settings.model_name,
            "success": False,
        }
        try:
            result = run_agent(item["question"], settings)
            elapsed = time.perf_counter() - started
            tools = [step.tool for step in result.steps]
            expected_tool = item.get("expected_tool")
            tool_ok = (not expected_tool) or expected_tool in tools
            blob = "\n".join(
                [result.answer, *[step.result_text for step in result.steps]]
            ).casefold()
            missing_facts = [
                fact for fact in item.get("expected_facts", []) if fact.casefold() not in blob
            ]
            success = result.error is None and tool_ok and not missing_facts and bool(result.answer.strip())
            record.update(
                {
                    "success": success,
                    "elapsed_s": round(elapsed, 2),
                    "llm_calls": result.llm_calls,
                    "tool_calls": result.tool_calls,
                    "tools": tools,
                    "expected_tool": expected_tool,
                    "tool_ok": tool_ok,
                    "missing_facts": missing_facts,
                    "error": result.error,
                    "answer_preview": result.answer[:400],
                }
            )
            status = "OK" if success else "FAIL"
            print(
                f"[BENCH] {item['id']} {status} "
                f"time={elapsed:.1f}s llm_calls={result.llm_calls} tool_calls={result.tool_calls} "
                f"tools={tools}"
            )
            if not tool_ok:
                print(f"[BENCH]   outil attendu absent : {expected_tool}")
            if missing_facts:
                print(f"[BENCH]   faits absents : {missing_facts}")
            if result.error:
                print(f"[BENCH]   erreur : {result.error}")
        except Exception as exc:  # noqa: BLE001 - une question ne doit pas arrêter le lot
            elapsed = time.perf_counter() - started
            record.update({"elapsed_s": round(elapsed, 2), "error": f"{type(exc).__name__}: {exc}"})
            print(f"[BENCH] {item['id']} FAIL time={elapsed:.1f}s error={exc}")
        results.append(record)

    passed = sum(1 for record in results if record["success"])
    summary = {
        "model": settings.model_name,
        "passed": passed,
        "total": len(results),
        "results": results,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[BENCH] {passed}/{len(results)} succès. Détail : {OUTPUT_PATH}")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
