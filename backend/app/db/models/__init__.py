"""Import every model here so Alembic and `Base.metadata` see the full schema."""

from app.db.models.audit import AuditLog
from app.db.models.coding import (
    GenerationStatus,
    Language,
    Question,
    QuestionGeneration,
    QuestionStatus,
    QuestionTemplate,
    Submission,
    TestCase,
    Verdict,
)
from app.db.models.interview import (
    Difficulty,
    Interview,
    InterviewMessage,
    InterviewReport,
    InterviewStatus,
    InterviewType,
    ReportStatus,
)
from app.db.models.jobs import (
    ATS,
    Company,
    ExperienceLevel,
    IngestionRun,
    Job,
    JobSource,
    RunStatus,
    SavedJob,
    WorkMode,
)
from app.db.models.llm import LLMUsage
from app.db.models.matching import JobMatch, MatchAnalysisStatus
from app.db.models.portfolio import AnalysisStatus, PortfolioAnalysis, PortfolioKind
from app.db.models.profile import Profile, RemotePreference
from app.db.models.prompts import PromptTemplate, PromptTemplateVersion
from app.db.models.resume import EMBEDDING_DIMENSIONS, Resume, ResumeSkill, ResumeStatus
from app.db.models.user import RefreshToken, Role, User, UserRole, UserStatus

__all__ = [
    "ATS",
    "EMBEDDING_DIMENSIONS",
    "AnalysisStatus",
    "AuditLog",
    "Company",
    "Difficulty",
    "ExperienceLevel",
    "GenerationStatus",
    "IngestionRun",
    "Interview",
    "InterviewMessage",
    "InterviewReport",
    "InterviewStatus",
    "InterviewType",
    "Job",
    "JobMatch",
    "JobSource",
    "LLMUsage",
    "Language",
    "MatchAnalysisStatus",
    "PortfolioAnalysis",
    "PortfolioKind",
    "Profile",
    "PromptTemplate",
    "PromptTemplateVersion",
    "Question",
    "QuestionGeneration",
    "QuestionStatus",
    "QuestionTemplate",
    "RefreshToken",
    "RemotePreference",
    "ReportStatus",
    "Resume",
    "ResumeSkill",
    "ResumeStatus",
    "Role",
    "RunStatus",
    "SavedJob",
    "Submission",
    "TestCase",
    "User",
    "UserRole",
    "UserStatus",
    "Verdict",
    "WorkMode",
]
