import type { components } from "./schema";

type Schemas = components["schemas"];

export type Me = Schemas["MeResponse"];
export type TokenResponse = Schemas["TokenResponse"];
export type UserSummary = Schemas["UserSummary"];
export type UserStatus = UserSummary["status"];
export type AdminOverview = Schemas["AdminOverview"];
export type AuditLog = Schemas["AuditLogOut"];
export type RoleInfo = Schemas["RoleOut"];
export type RoleName = Schemas["SetRoleRequest"]["role"];
export type Page<T> = { items: T[]; total: number; page: number; page_size: number };
export type ErrorEnvelope = Schemas["ErrorResponse"];

export const ROLE_NAMES: RoleName[] = ["super_admin", "admin", "content_editor", "support", "user"];

export type Profile = Schemas["ProfileOut"];
export type ProfileUpdate = Schemas["ProfileUpdate"];
export type RemotePreference = Profile["remote_preference"];
export type Resume = Schemas["ResumeOut"];
export type ResumeSummary = Schemas["ResumeSummary"];
export type ResumeStatus = Resume["status"];
export type ParsedResume = Schemas["ParsedResume"];
export type ParsedSkill = Schemas["ParsedSkill"];
export type SkillCategory = NonNullable<ParsedSkill["category"]>;
export type AdminUserDetail = Schemas["AdminUserDetail"];

export const SKILL_CATEGORIES: SkillCategory[] = [
  "language",
  "framework",
  "database",
  "cloud",
  "devops",
  "tool",
  "practice",
  "soft",
  "other",
];

export type JobCard = Schemas["JobCard"];
export type JobDetail = Schemas["JobDetail"];
export type JobSearchResponse = Schemas["JobSearchResponse"];
export type SavedJob = Schemas["SavedJobOut"];
export type WorkMode = JobCard["work_mode"];
export type ExperienceLevel = JobCard["experience_level"];
export type JobSource = Schemas["JobSourceOut"];
export type IngestionRun = Schemas["IngestionRunOut"];
export type Company = Schemas["CompanyOut"];
export type AdminJob = Schemas["AdminJobOut"];
export type CompanyImportResult = Schemas["CompanyImportResult"];

export const WORK_MODES: { value: WorkMode; label: string }[] = [
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
  { value: "onsite", label: "On-site" },
];

export const EXPERIENCE_LEVELS: { value: ExperienceLevel; label: string }[] = [
  { value: "internship", label: "Internship" },
  { value: "entry", label: "Entry level" },
  { value: "mid", label: "Mid level" },
  { value: "senior", label: "Senior" },
  { value: "staff", label: "Staff / Principal" },
  { value: "manager", label: "Manager / Director" },
];

export type MatchSummary = Schemas["MatchSummary"];
export type MatchDetail = Schemas["MatchDetail"];
export type MatchAnalysis = Schemas["AnalysisOut"];
export type SkillGapAnalysis = Schemas["SkillGapAnalysis"];
export type RecommendedJob = Schemas["RecommendedJob"];
export type RecommendationsResponse = Schemas["RecommendationsResponse"];
export type EmbeddingStatus = Schemas["EmbeddingStatus"];

export type InterviewType = Schemas["InterviewTypeOut"];
export type InterviewState = Schemas["InterviewState"];
export type InterviewDetail = Schemas["InterviewDetail"];
export type InterviewMessage = Schemas["InterviewMessageOut"];
export type InterviewSummary = Schemas["InterviewSummary"];
export type InterviewReport = Schemas["ReportOut"];
export type ReportResult = Schemas["ReportResult"];
export type Difficulty = InterviewType["difficulty"];
export type InterviewTypeAdmin = Schemas["InterviewTypeAdmin"];
export type InterviewTypeUpdate = Schemas["InterviewTypeUpdate"];
export type RubricCriterion = Schemas["RubricCriterion"];
export type AdminInterview = Schemas["AdminInterviewOut"];
export type PromptSummary = Schemas["PromptSummary"];
export type PromptDetail = Schemas["PromptDetail"];
export type PromptVersion = Schemas["PromptVersionOut"];
export type PromptTestResult = Schemas["PromptTestResult"];

export const DIFFICULTIES: { value: Difficulty; label: string }[] = [
  { value: "easy", label: "Easy" },
  { value: "medium", label: "Medium" },
  { value: "hard", label: "Hard" },
];

export type CodeLanguage = Schemas["LanguageOut"];
export type ProblemSummary = Schemas["ProblemSummary"];
export type ProblemDetail = Schemas["ProblemDetail"];
export type RunResult = Schemas["RunResultOut"];
export type CaseResult = Schemas["CaseResultOut"];
export type Submission = Schemas["SubmissionOut"];
export type SubmissionDetail = Schemas["SubmissionDetail"];
export type Verdict = Submission["verdict"];
export type LanguageAdmin = Schemas["LanguageAdmin"];
export type QuestionAdminSummary = Schemas["QuestionAdminSummary"];
export type QuestionAdminDetail = Schemas["QuestionAdminDetail"];
export type QuestionIn = Schemas["QuestionIn"];
export type GenerationItem = Schemas["GenerationOut"];

export const VERDICT_LABELS: Record<Verdict, string> = {
  queued: "Queued",
  running: "Running",
  accepted: "Accepted",
  wrong_answer: "Wrong answer",
  compile_error: "Compile error",
  runtime_error: "Runtime error",
  time_limit: "Time limit exceeded",
  memory_limit: "Memory limit exceeded",
  sandbox_error: "Sandbox unavailable",
};

export type FrameworkSummary = Schemas["FrameworkOut"];
export type FrameworkAttempt = Schemas["AttemptOut"];
export type AttemptQuestion = Schemas["AttemptQuestion"];
export type SkillsOverview = Schemas["SkillsOverview"];

export type Application = Schemas["ApplicationOut"];
export type ApplicationStatus = Application["status"];
export type Reminder = Schemas["ReminderOut"];
export type DashboardData = Schemas["DashboardOut"];
export type UserReport = Schemas["UserReportOut"];
export type AdminUserReport = Schemas["AdminUserReportOut"];
export type ReportKind = UserReport["kind"];

export const APPLICATION_COLUMNS: { status: ApplicationStatus; label: string }[] = [
  { status: "saved", label: "Saved" },
  { status: "applied", label: "Applied" },
  { status: "screening", label: "Screening" },
  { status: "interviewing", label: "Interviewing" },
  { status: "offer", label: "Offer" },
  { status: "rejected", label: "Rejected" },
  { status: "withdrawn", label: "Withdrawn" },
];
