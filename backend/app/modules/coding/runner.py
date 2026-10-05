"""Code execution sandboxes behind one interface.

User code never runs in the API process or on the host: it goes to a sandbox service that
runs each program in an isolated, network-less box with CPU, memory, time and output limits.

- **Piston** (default for local development): self-hosted, free, works on cgroup v2 hosts
  such as Docker Desktop.
- **Judge0 CE**: the brief's choice. Version 1.13 needs cgroup v1, so it suits Linux hosts
  configured for it (or a managed Judge0); switch with CODE_RUNNER=judge0.
- **Fake**: deterministic stand-in for tests. It never executes anything.
"""

import asyncio
import base64
import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, ClassVar, Literal, Protocol

import httpx
import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

RunStatus = Literal[
    "ok", "compile_error", "runtime_error", "time_limit", "memory_limit", "sandbox_error"
]
MAX_OUTPUT_CHARS = 64_000  # we never keep more than this from a run


@dataclass(frozen=True, slots=True)
class RunRequest:
    language: str  # our language key: python, javascript, typescript, java, cpp, go
    code: str
    stdin: str
    time_limit_s: float
    memory_limit_mb: int


@dataclass(frozen=True, slots=True)
class RunResult:
    status: RunStatus
    stdout: str = ""
    stderr: str = ""
    compile_output: str = ""
    time_ms: int | None = None
    memory_kb: int | None = None


class CodeRunner(Protocol):
    name: str

    async def run(self, request: RunRequest) -> RunResult: ...


def _clip(text: str | None) -> str:
    return (text or "")[:MAX_OUTPUT_CHARS]


# ------------------------------------------------------------------ Piston


PISTON_LANGUAGES: dict[str, tuple[str, str]] = {  # key -> (piston language, file name)
    "python": ("python", "main.py"),
    "javascript": ("javascript", "main.js"),
    "typescript": ("typescript", "main.ts"),
    "java": ("java", "Main.java"),
    "cpp": ("c++", "main.cpp"),
    "go": ("go", "main.go"),
}


class PistonRunner:
    name = "piston"

    def __init__(self, base_url: str, client: httpx.AsyncClient | None = None):
        self._url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=60)

    async def run(self, request: RunRequest) -> RunResult:
        language, filename = PISTON_LANGUAGES[request.language]
        payload = {
            "language": language,
            "version": "*",
            "files": [{"name": filename, "content": request.code}],
            "stdin": request.stdin,
            "run_timeout": int(request.time_limit_s * 1000),
            "compile_timeout": 15_000,
            "run_memory_limit": request.memory_limit_mb * 1024 * 1024,
        }
        try:
            response = await self._client.post(f"{self._url}/api/v2/execute", json=payload)
        except httpx.HTTPError as exc:
            logger.warning("piston_unreachable", error=str(exc))
            return RunResult("sandbox_error", stderr="The code sandbox is unavailable.")
        if response.status_code != 200:
            return RunResult("sandbox_error", stderr=f"Sandbox error ({response.status_code}).")
        return piston_result(response.json())


def piston_result(data: dict[str, Any]) -> RunResult:
    compile_ = data.get("compile") or {}
    run = data.get("run") or {}
    if compile_ and compile_.get("code") not in (0, None):
        return RunResult("compile_error", compile_output=_clip(compile_.get("output")))
    piston_status = run.get("status")
    status: RunStatus
    if piston_status == "TO":
        status = "time_limit"
    elif piston_status == "XX":
        status = "sandbox_error"
    elif run.get("signal") == "SIGKILL" or piston_status == "SG":
        status = "memory_limit"
    elif run.get("code") not in (0, None) or piston_status == "RE":
        status = "runtime_error"
    else:
        status = "ok"
    cpu, memory = run.get("cpu_time"), run.get("memory")
    return RunResult(
        status,
        stdout=_clip(run.get("stdout")),
        stderr=_clip(run.get("stderr")),
        time_ms=int(cpu) if isinstance(cpu, (int, float)) else None,
        memory_kb=int(memory) // 1024 if isinstance(memory, (int, float)) else None,
    )


# ------------------------------------------------------------------ Judge0


JUDGE0_LANGUAGES = {  # Judge0 CE 1.13 language ids
    "python": 71,
    "javascript": 63,
    "typescript": 74,
    "java": 62,
    "cpp": 54,
    "go": 60,
}
_JUDGE0_STATUS: dict[int, RunStatus] = {
    3: "ok",
    4: "ok",
    5: "time_limit",
    6: "compile_error",
    13: "sandbox_error",
    14: "sandbox_error",
}


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def _unb64(value: str | None) -> str:
    return _clip(base64.b64decode(value).decode(errors="replace")) if value else ""


class Judge0Runner:
    name = "judge0"

    def __init__(self, base_url: str, token: str | None, client: httpx.AsyncClient | None = None):
        self._url = base_url.rstrip("/")
        self._headers = {"X-Auth-Token": token} if token else {}
        self._client = client or httpx.AsyncClient(timeout=60)

    async def run(self, request: RunRequest) -> RunResult:
        payload = {
            "source_code": _b64(request.code),
            "language_id": JUDGE0_LANGUAGES[request.language],
            "stdin": _b64(request.stdin),
            "cpu_time_limit": request.time_limit_s,
            "wall_time_limit": request.time_limit_s * 3,
            "memory_limit": request.memory_limit_mb * 1024,
            "enable_network": False,
        }
        try:
            response = await self._client.post(
                f"{self._url}/submissions?base64_encoded=true&wait=true",
                json=payload,
                headers=self._headers,
            )
        except httpx.HTTPError as exc:
            logger.warning("judge0_unreachable", error=str(exc))
            return RunResult("sandbox_error", stderr="The code sandbox is unavailable.")
        if response.status_code not in (200, 201):
            return RunResult("sandbox_error", stderr=f"Sandbox error ({response.status_code}).")
        data = response.json()
        status_id = int((data.get("status") or {}).get("id", 13))
        status = _JUDGE0_STATUS.get(
            status_id, "runtime_error" if 7 <= status_id <= 12 else "sandbox_error"
        )
        return RunResult(
            status,
            stdout=_unb64(data.get("stdout")),
            stderr=_unb64(data.get("stderr")),
            compile_output=_unb64(data.get("compile_output")),
            time_ms=int(float(data["time"]) * 1000) if data.get("time") else None,
            memory_kb=int(data["memory"]) if data.get("memory") else None,
        )


# ------------------------------------------------------------------ fake (tests)


_FAKE = re.compile(r"fake:(\w+)")


class FakeRunner:
    """Never executes code. Behaviour is picked by markers in the source:
    COMPILE_ERROR / TIMEOUT / CRASH / OOM, or `fake:<name>` for a registered function of
    stdin. Anything else echoes stdin."""

    name = "fake"
    programs: ClassVar[dict[str, Callable[[str], str]]] = {}

    async def run(self, request: RunRequest) -> RunResult:
        await asyncio.sleep(0)
        code = request.code
        if "COMPILE_ERROR" in code:
            return RunResult("compile_error", compile_output="main: error: expected ';'")
        if "TIMEOUT" in code:
            return RunResult("time_limit", time_ms=int(request.time_limit_s * 1000))
        if "CRASH" in code:
            return RunResult("runtime_error", stderr="Traceback: ZeroDivisionError")
        if "OOM" in code:
            return RunResult("memory_limit")
        match = _FAKE.search(code)
        program = self.programs.get(match.group(1)) if match else None
        output = program(request.stdin) if program else request.stdin
        return RunResult("ok", stdout=output, time_ms=12, memory_kb=4096)


@lru_cache(maxsize=1)
def get_runner() -> CodeRunner:
    settings = get_settings()
    if settings.code_runner == "fake":
        return FakeRunner()
    if settings.code_runner == "judge0":
        token = (
            settings.judge0_auth_token.get_secret_value() if settings.judge0_auth_token else None
        )
        return Judge0Runner(settings.judge0_url, token)
    return PistonRunner(settings.piston_url)
