"""Rule-based stand-ins for the interview prompts, used by the mock LLM provider.

They keep interviews fully usable without a model (tests, offline development): short
answers get a follow-up, detailed ones move on, and the report scores answers by how much
substance they contain. Real quality comes from real models.
"""

import json
import re

from app.llm.factory import MOCK_HANDLERS
from app.llm.routing import Task
from app.llm.types import CompletionRequest

_ANSWER = re.compile(r"<answer>\n?(.*?)\n?</answer>", re.S)
_COUNT = re.compile(r"Write (\d+) questions")
_TITLE = re.compile(r"role: (.+?) at (.+?)\.")
_RUBRIC_KEY = re.compile(r"^- (\w+): ", re.M)
_QUESTION = re.compile(r"^Question (\d+): ", re.M)
DETAILED = 120  # characters


def _plan(request: CompletionRequest) -> str:
    prompt = request.messages[-1].content
    count = int(m.group(1)) if (m := _COUNT.search(prompt)) else 3
    title = m.group(1) if (m := _TITLE.search(prompt)) else "this role"
    questions = [
        {
            "prompt": f"Question {n + 1} about {title}: walk me through a relevant project.",
            "focus": "Experience",
            "kind": "technical",
            "expected_points": ["Concrete project", "Own role", "Outcome"],
        }
        for n in range(count)
    ]
    return json.dumps({"questions": questions})


def _interviewer(request: CompletionRequest) -> str:
    answers = _ANSWER.findall(request.messages[-1].content)
    last = answers[-1] if answers else ""
    if len(last) >= DETAILED:
        return "Thanks, that's a clear answer.\n[[NEXT]]"
    return "Can you go deeper on that? What trade-offs did you consider?"


def _hint(_: CompletionRequest) -> str:
    return "Try breaking the problem into smaller steps first."


def _report(request: CompletionRequest) -> str:
    system, user = request.messages[0].content, request.messages[-1].content
    keys = _RUBRIC_KEY.findall(system)
    blocks = _QUESTION.split(user)[1:]  # [index, body, index, body, ...]
    questions = []
    for index, body in zip(blocks[::2], blocks[1::2], strict=False):
        answers = " ".join(_ANSWER.findall(body))
        if answers:
            questions.append(
                {
                    "index": int(index),
                    "score": min(10, 3 + len(answers) // 60),
                    "feedback": "Solid structure; add more specifics.",
                    "strengths": ["Clear explanation"],
                    "improvements": ["Quantify the impact"],
                }
            )
    return json.dumps(
        {
            "summary": "You communicated clearly. Add more concrete detail to stand out.",
            "criteria": [
                {"key": k, "score": 3, "evidence": "", "comment": "Adequate."} for k in keys
            ],
            "questions": questions,
            "strengths": ["Clear communication"],
            "weaknesses": ["Few concrete numbers"],
            "tips": ["Quantify the results of your work"],
            "next_practice": {
                "type": "behavioral",
                "focus": "Impact stories",
                "reason": "Practise results.",
            },
        }
    )


MOCK_HANDLERS[Task.INTERVIEW_PLAN] = _plan
MOCK_HANDLERS[Task.INTERVIEWER] = _interviewer
MOCK_HANDLERS[Task.INTERVIEW_HINT] = _hint
MOCK_HANDLERS[Task.INTERVIEW_REPORT] = _report
