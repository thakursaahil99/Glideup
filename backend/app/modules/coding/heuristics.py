"""Mock-provider stand-in for question generation (tests, offline development)."""

import json

from app.llm.factory import MOCK_HANDLERS
from app.llm.routing import Task
from app.llm.types import CompletionRequest


def _generate(request: CompletionRequest) -> str:
    topic = request.messages[-1].content.split("about:", 1)[-1].strip() or "arrays"
    return json.dumps(
        {
            "title": f"Sum of Numbers ({topic})",
            "statement": "Read n and then n integers. Print their sum.\n\n**Input**\n"
            "n, then n integers.\n\n**Output**\nThe sum.",
            "topics": [topic],
            "tests": [
                {"input": "3\n1 2 3\n", "hidden": False},
                {"input": "1\n-5\n", "hidden": True},
                {"input": "4\n10 20 30 40\n", "hidden": True},
            ],
            "reference_solution": "# fake:sum\nimport sys\nd = sys.stdin.read().split()\n"
            "print(sum(map(int, d[1:])))\n",
        }
    )


MOCK_HANDLERS[Task.QUESTION_GENERATE] = _generate
