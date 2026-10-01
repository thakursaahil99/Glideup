import {
  Bot,
  BriefcaseBusiness,
  ClipboardList,
  Code2,
  Flag,
  FileText,
  Gauge,
  HeartPulse,
  KanbanSquare,
  LayoutDashboard,
  LibraryBig,
  type LucideIcon,
  Megaphone,
  MessagesSquare,
  MessageSquareWarning,
  ScrollText,
  Settings2,
  Sparkles,
  UserRound,
  Users,
} from "lucide-react";

export type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  /** Permission the backend enforces for this area; the UI only mirrors it. */
  permission?: string;
  /** Build phase that ships this screen. Items with a phase are shown as "coming soon". */
  phase?: number;
};

export const APP_NAV: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Profile", href: "/profile", icon: UserRound },
  { label: "Jobs", href: "/jobs", icon: BriefcaseBusiness, phase: 3 },
  { label: "Interviews", href: "/interviews", icon: MessagesSquare, phase: 5 },
  { label: "Tests", href: "/tests", icon: Code2, phase: 6 },
  { label: "Tracker", href: "/tracker", icon: KanbanSquare, phase: 8 },
];

export const ADMIN_NAV: NavItem[] = [
  { label: "Overview", href: "/admin", icon: Gauge, permission: "admin:access" },
  { label: "Users", href: "/admin/users", icon: Users, permission: "users:read" },
  {
    label: "Jobs & Sources",
    href: "/admin/jobs",
    icon: BriefcaseBusiness,
    permission: "jobs:manage",
    phase: 3,
  },
  {
    label: "Question Bank",
    href: "/admin/questions",
    icon: LibraryBig,
    permission: "questions:manage",
    phase: 6,
  },
  {
    label: "AI Generation Queue",
    href: "/admin/generation",
    icon: Sparkles,
    permission: "questions:manage",
    phase: 6,
  },
  {
    label: "Interviews",
    href: "/admin/interviews",
    icon: MessagesSquare,
    permission: "interviews:manage",
    phase: 5,
  },
  {
    label: "Prompt Templates",
    href: "/admin/prompts",
    icon: FileText,
    permission: "prompts:manage",
    phase: 5,
  },
  { label: "AI / LLM Settings", href: "/admin/llm", icon: Bot, permission: "llm:manage", phase: 9 },
  { label: "Feature Flags", href: "/admin/flags", icon: Flag, permission: "flags:manage", phase: 9 },
  { label: "Site Content", href: "/admin/content", icon: Settings2, permission: "content:manage", phase: 10 },
  {
    label: "Announcements",
    href: "/admin/announcements",
    icon: Megaphone,
    permission: "announcements:manage",
    phase: 9,
  },
  {
    label: "User Reports",
    href: "/admin/reports",
    icon: MessageSquareWarning,
    permission: "reports:read",
    phase: 8,
  },
  { label: "System Health", href: "/admin/health", icon: HeartPulse, permission: "system:read", phase: 9 },
  { label: "Audit Logs", href: "/admin/audit-logs", icon: ScrollText, permission: "audit:read" },
];

export const JOURNEY = [
  { title: "Upload your resume", body: "We extract your skills and experience.", icon: FileText },
  { title: "See matching jobs", body: "Real openings, ranked by fit.", icon: BriefcaseBusiness },
  { title: "Close skill gaps", body: "Know exactly what's missing.", icon: ClipboardList },
  {
    title: "Practice the interview",
    body: "Job-specific mock interviews and coding tests.",
    icon: MessagesSquare,
  },
  { title: "Apply and track", body: "From application to offer.", icon: KanbanSquare },
] as const;

export function hasPermission(permissions: readonly string[] | undefined, permission?: string) {
  return !permission || Boolean(permissions?.includes(permission));
}

export function visibleNav(items: NavItem[], permissions: readonly string[] | undefined) {
  return items.filter((item) => hasPermission(permissions, item.permission));
}

export function isActive(pathname: string, href: string) {
  if (href === "/admin" || href === "/dashboard") return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}
