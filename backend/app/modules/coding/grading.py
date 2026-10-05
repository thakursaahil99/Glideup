"""Run a program against test cases and decide the verdict."""

import asyncio
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.db.models import Language, TestCase, Verdict
from app.modules.coding.runner import RunRequest, RunResult, get_runner

DETAIL_CHARS = 2000  # of stdin/stdout/stderr shown for a visible test

_VERDICT_FOR_STATUS = {
    "compile_error": Verdict.COMPILE_ERROR,
    "runtime_error": Verdict.RUNTIME_ERROR,
    "time_limit": Verdict.TIME_LIMIT,
    "memory_limit": Verdict.MEMORY_LIMIT,
    "sandbox_error": Verdict.SANDBOX_ERROR,
}


def normalize(text: str) -> str:
    """Ignore trailing spaces on each line and trailing blank lines."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


@dataclass
class Grade:
    verdict: Verdict
    passed: int
    total: int
    results: list[dict[str, Any]] = field(default_factory=list)
    compile_output: str | None = None
    max_time_ms: int | None = None


def _case_result(test: TestCase, run: RunResult) -> dict[str, Any]:
    if run.status == "ok":
        verdict = (
            Verdict.ACCEPTED
            if normalize(run.stdout) == normalize(test.expected_output)
            else Verdict.WRONG_ANSWER
        )
    else:
        verdict = _VERDICT_FOR_STATUS[run.status]
    entry: dict[str, Any] = {
        "position": test.position,
        "hidden": test.hidden,
        "verdict": verdict.value,
        "time_ms": run.time_ms,
        "memory_kb": run.memory_kb,
    }
    if not test.hidden:  # hidden tests reveal only pass/fail, never data
        entry |= {
            "input": test.input[:DETAIL_CHARS],
            "expected": test.expected_output[:DETAIL_CHARS],
            "stdout": run.stdout[:DETAIL_CHARS],
            "stderr": run.stderr[:DETAIL_CHARS],
        }
    return entry


async def grade(language: Language, code: str, tests: list[TestCase]) -> Grade:
    """Run every test. The first runs alone so a compile error is reported once (and
    without spending N sandbox runs); the rest run in parallel, capped."""
    runner = get_runner()
    ordered = sorted(tests, key=lambda t: t.position)
    if not ordered:
        return Grade(Verdict.SANDBOX_ERROR, 0, 0)

    def request(test: TestCase) -> RunRequest:
        return RunRequest(
            language=language.key,
            code=code,
            stdin=test.input,
            time_limit_s=language.time_limit_s,
            memory_limit_mb=language.memory_limit_mb,
        )

    first = await runner.run(request(ordered[0]))
    if first.status == "compile_error":
        return Grade(
            Verdict.COMPILE_ERROR,
            0,
            len(ordered),
            [_case_result(ordered[0], first)],
            compile_output=first.compile_output[:DETAIL_CHARS],
        )
    gate = asyncio.Semaphore(get_settings().code_runner_concurrency)

    async def run_one(test: TestCase) -> RunResult:
        async with gate:
            return await runner.run(request(test))

    rest = await asyncio.gather(*(run_one(t) for t in ordered[1:]))
    results = [_case_result(t, r) for t, r in zip(ordered, [first, *rest], strict=True)]
    passed = sum(r["verdict"] == Verdict.ACCEPTED for r in results)
    failing = next((r for r in results if r["verdict"] != Verdict.ACCEPTED), None)
    times = [r["time_ms"] for r in results if r["time_ms"] is not None]
    return Grade(
        verdict=Verdict(failing["verdict"]) if failing else Verdict.ACCEPTED,
        passed=passed,
        total=len(results),
        results=results,
        max_time_ms=max(times) if times else None,
    )
