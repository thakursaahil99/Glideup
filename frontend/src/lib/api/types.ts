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
