"""Example variables for each prompt, used by the admin "test this prompt" playground."""

from typing import Any

_RESUME = (
    "Asha Verma\nSenior Backend Engineer\nSkills: Python, FastAPI, PostgreSQL, Redis, Docker\n"
    "Senior Backend Engineer, Example Corp (2021 - present): designed REST APIs serving "
    "2M requests/day."
)
_JOB = (
    "We are hiring a Senior Backend Engineer to scale our payments platform. You will design "
    "APIs in Python, run PostgreSQL and Kafka in production, and mentor engineers."
)
_TURNS = [
    {"role": "interviewer", "content": "Tell me about a time you disagreed with a teammate."},
    {
        "role": "candidate",
        "content": "We disagreed on caching; I ran a benchmark and we chose Redis.",
    },
]
_RUBRIC = [
    {"key": "action", "name": "Action", "description": "Specific actions they took.", "weight": 2},
    {"key": "result", "name": "Result", "description": "Concrete outcomes.", "weight": 1.5},
]

SAMPLES: dict[str, dict[str, Any]] = {
    "resume_parse": {"resume_text": _RESUME, "today": "2026-10-05"},
    "portfolio_parse": {
        "url": "https://asha.dev",
        "site_text": "Asha Verma - backend engineer. Projects: payments API (FastAPI, Postgres).",
    },
    "skill_gap": {
        "title": "Senior Backend Engineer",
        "company": "Acme",
        "level": "senior",
        "job_skills": ["Python", "PostgreSQL", "Kafka"],
        "missing": ["Kafka"],
        "job_text": _JOB,
        "candidate": "Skills: Python (5 yrs), FastAPI, PostgreSQL, Redis",
    },
    "interview_plan": {
        "count": 3,
        "difficulty": "medium",
        "title": "Senior Backend Engineer",
        "company": "Acme",
        "job_skills": ["Python", "PostgreSQL", "Kafka"],
        "job_text": _JOB,
        "candidate": "Skills: Python, FastAPI, PostgreSQL, Redis. 7 years of experience.",
    },
    "interviewer": {
        "persona": "hiring manager",
        "type_name": "Behavioral",
        "difficulty": "medium",
        "number": 1,
        "total": 4,
        "question": "Tell me about a time you disagreed with a teammate.",
        "expected_points": ["The disagreement", "How they made their case", "Outcome"],
        "followups_left": 2,
        "minutes_left": 25,
        "focus_guidance": "Probe for missing STAR parts.",
        "turns": _TURNS,
    },
    "interview_hint": {
        "type_name": "DSA / coding",
        "question": "Find the longest substring without repeating characters.",
        "expected_points": ["Sliding window", "Hash map of last seen index", "O(n)"],
        "hint_number": 1,
        "turns": [{"role": "candidate", "content": "I'd check every substring."}],
    },
    "interview_report": {
        "type_name": "Behavioral",
        "difficulty": "medium",
        "rubric": _RUBRIC,
        "type_keys": ["behavioral", "dsa", "job_specific", "system_design"],
        "hints_used": 0,
        "questions": [
            {
                "index": 0,
                "prompt": "Tell me about a time you disagreed with a teammate.",
                "expected_points": ["The disagreement", "Outcome"],
                "turns": _TURNS,
            }
        ],
    },
    "question_generate": {"topic": "sliding window", "difficulty": "medium"},
    "framework_grade": {
        "framework": "React",
        "question_type": "viva",
        "statement": "When does a React component re-render?",
        "code": "",
        "items": [
            {"key": "state", "description": "Its state changes"},
            {"key": "parent", "description": "Its parent re-renders"},
        ],
        "answer": "When state changes or the parent renders again.",
    },
}
