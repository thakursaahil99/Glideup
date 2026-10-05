# ruff: noqa: E501  (a data table: long rubric descriptions read better unwrapped)
"""The interview types GlideUp ships with. Admins edit them afterwards; these are only the
starting point (`ensure_types` inserts any that are missing and never overwrites)."""

from typing import Any

from app.db.models import Difficulty


def _rubric(*criteria: tuple[str, str, str, float]) -> list[dict[str, Any]]:
    return [
        {"key": key, "name": name, "description": description, "weight": weight}
        for key, name, description, weight in criteria
    ]


DEFAULT_TYPES: list[dict[str, Any]] = [
    {
        "key": "dsa",
        "name": "DSA / coding",
        "description": "Solve algorithm problems out loud: approach, code, complexity, edge cases.",
        "duration_minutes": 45,
        "question_count": 2,
        "max_followups": 3,
        "difficulty": Difficulty.MEDIUM,
        "sort_order": 1,
        "rubric": _rubric(
            (
                "understanding",
                "Problem understanding",
                "Clarifies inputs, outputs and constraints before coding.",
                1,
            ),
            (
                "approach",
                "Approach",
                "Finds a sound approach and explains why, considering alternatives.",
                2,
            ),
            (
                "correctness",
                "Correctness",
                "Code or pseudo-code that works, including edge cases.",
                2,
            ),
            ("complexity", "Complexity", "States and justifies time and space complexity.", 1),
            ("communication", "Communication", "Thinks out loud clearly and responds to hints.", 1),
        ),
    },
    {
        "key": "system_design",
        "name": "System design",
        "description": "Design a system end to end: requirements, architecture, data, scale and trade-offs.",
        "duration_minutes": 45,
        "question_count": 1,
        "max_followups": 5,
        "difficulty": Difficulty.MEDIUM,
        "sort_order": 2,
        "rubric": _rubric(
            (
                "requirements",
                "Requirements",
                "Pins down functional and non-functional requirements and scale.",
                1,
            ),
            (
                "architecture",
                "High-level design",
                "A clear set of components and how requests flow through them.",
                2,
            ),
            (
                "data",
                "Data model & storage",
                "Sensible data model and storage choices for the access patterns.",
                1.5,
            ),
            (
                "scale",
                "Scalability & reliability",
                "Handles growth, failures and bottlenecks (caching, sharding, queues).",
                1.5,
            ),
            ("tradeoffs", "Trade-offs", "Names alternatives and justifies choices.", 1.5),
            ("communication", "Communication", "Structured, drives the discussion, checks in.", 1),
        ),
    },
    {
        "key": "behavioral",
        "name": "Behavioral",
        "description": "Stories from your experience, assessed with STAR and values like ownership and growth.",
        "duration_minutes": 30,
        "question_count": 4,
        "max_followups": 2,
        "difficulty": Difficulty.MEDIUM,
        "sort_order": 3,
        "rubric": _rubric(
            (
                "situation",
                "Situation & task",
                "Sets up the context and their own responsibility briefly.",
                1,
            ),
            ("action", "Action", "Specific actions *they* took, in enough detail.", 2),
            (
                "result",
                "Result",
                "Concrete, ideally measurable outcomes and what they learned.",
                1.5,
            ),
            (
                "growth_mindset",
                "Growth mindset",
                "Learns from feedback and failure; seeks to improve.",
                1,
            ),
            (
                "ownership",
                "Ownership",
                "Takes responsibility end to end, including for mistakes.",
                1,
            ),
            (
                "collaboration",
                "Collaboration",
                "Works well with others, handles disagreement constructively.",
                1,
            ),
        ),
    },
    {
        "key": "job_specific",
        "name": "Job-specific",
        "description": "Questions written from a real job description and your resume.",
        "duration_minutes": 30,
        "question_count": 4,
        "max_followups": 2,
        "difficulty": Difficulty.MEDIUM,
        "sort_order": 4,
        "rubric": _rubric(
            (
                "role_knowledge",
                "Role knowledge",
                "Understands what the role involves and its key technologies.",
                1.5,
            ),
            (
                "technical_depth",
                "Technical depth",
                "Accurate, deep answers on the job's core skills.",
                2,
            ),
            (
                "experience",
                "Relevant experience",
                "Backs answers with concrete experience from their background.",
                1.5,
            ),
            (
                "problem_solving",
                "Problem solving",
                "Reasons through unfamiliar problems methodically.",
                1,
            ),
            ("communication", "Communication", "Clear, concise and structured.", 1),
        ),
    },
]
