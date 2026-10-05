"""The data each framework-test question type carries (stored on `Question.content`).

- **mcq**: options and the correct one (auto-graded, exact).
- **review**: a code snippet with planted issues; the user writes a review and the AI checks
  which planted issues they found.
- **viva**: a conceptual question with the key points a strong answer covers.
- **project**: a small task (a component, an endpoint) with requirements; graded by static
  checks (patterns that must appear) plus an AI review against each requirement.
"""

import re
from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

QuestionType = Literal["mcq", "review", "viva", "project"]
FRAMEWORK_TYPES: tuple[QuestionType, ...] = ("mcq", "review", "viva", "project")
Text300 = Annotated[str, Field(min_length=1, max_length=300)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MCQContent(_Model):
    options: list[Text300] = Field(min_length=2, max_length=6)
    answer: int = Field(ge=0)
    explanation: str = Field(default="", max_length=600)

    @model_validator(mode="after")
    def _answer_in_range(self) -> "MCQContent":
        if self.answer >= len(self.options):
            raise ValueError("answer must be the index of one of the options")
        return self


class Issue(_Model):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")
    description: str = Field(min_length=3, max_length=300)
    weight: int = Field(default=1, ge=1, le=3)


class ReviewContent(_Model):
    language: str = Field(max_length=20)
    code: str = Field(min_length=10, max_length=8000)
    issues: list[Issue] = Field(min_length=1, max_length=8)


class VivaContent(_Model):
    key_points: list[Text300] = Field(min_length=2, max_length=8)


class Requirement(_Model):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")
    description: str = Field(min_length=3, max_length=300)
    # A regex the solution must contain (checked without running anything). Optional.
    pattern: str | None = Field(default=None, max_length=200)
    weight: int = Field(default=1, ge=1, le=3)

    @field_validator("pattern")
    @classmethod
    def _compiles(cls, value: str | None) -> str | None:
        if value:
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError(f"pattern is not a valid regular expression: {exc}") from exc
        return value


class ProjectContent(_Model):
    language: str = Field(max_length=20)
    starter: str = Field(default="", max_length=8000)
    requirements: list[Requirement] = Field(min_length=1, max_length=10)


CONTENT_MODELS: dict[str, type[_Model]] = {
    "mcq": MCQContent,
    "review": ReviewContent,
    "viva": VivaContent,
    "project": ProjectContent,
}


def validate_content(question_type: str, content: object) -> dict[str, object]:
    model = CONTENT_MODELS.get(question_type)
    if model is None:
        raise ValueError(f"Unknown question type '{question_type}'")
    return model.model_validate(content).model_dump()


def public_content(question_type: str, content: dict[str, object]) -> dict[str, object]:
    """What a test-taker may see: never the answer, planted issues, key points or patterns."""
    if question_type == "mcq":
        return {"options": content["options"]}
    if question_type == "review":
        return {"language": content["language"], "code": content["code"]}
    if question_type == "project":
        requirements = cast(list[dict[str, Any]], content.get("requirements") or [])
        return {
            "language": content["language"],
            "starter": content.get("starter", ""),
            "requirements": [r["description"] for r in requirements],
        }
    return {}
