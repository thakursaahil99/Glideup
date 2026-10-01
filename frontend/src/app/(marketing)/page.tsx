import {
  ArrowRight,
  BriefcaseBusiness,
  Code2,
  FileSearch,
  KanbanSquare,
  Lock,
  MessagesSquare,
  Mic,
  Scale,
  ShieldCheck,
  Target,
} from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/primitives";
import { JOURNEY } from "@/lib/navigation";

const FEATURES = [
  {
    icon: FileSearch,
    title: "Resume intelligence",
    body: "Upload a PDF and get a structured profile: skills, years per skill, experience and education — editable by you.",
  },
  {
    icon: BriefcaseBusiness,
    title: "Real jobs, official sources",
    body: "Openings from public ATS boards and job APIs, deduplicated and refreshed every six hours. No scraping, ever.",
  },
  {
    icon: Target,
    title: "Match score & skill gaps",
    body: "See how well you fit each role, which skills are missing, and what to learn first.",
  },
  {
    icon: MessagesSquare,
    title: "AI mock interviews",
    body: "Coding, system design, behavioral (STAR) and job-specific rounds that ask follow-ups like a real interviewer.",
  },
  {
    icon: Code2,
    title: "Coding & framework tests",
    body: "Solve problems in Python, Java, C++, C#, JavaScript and TypeScript, plus real React and FastAPI tasks — run in a sandbox.",
  },
  {
    icon: KanbanSquare,
    title: "Application tracker",
    body: "A simple board from saved to offer, with notes, contacts and reminders linked to your practice.",
  },
];

const PRINCIPLES = [
  {
    icon: ShieldCheck,
    title: "Official sources only",
    body: "Jobs come from public APIs. We link to the real apply page.",
  },
  { icon: Lock, title: "Your data stays yours", body: "Export or delete everything at any time." },
  {
    icon: Scale,
    title: "Original questions",
    body: "Every problem is written for GlideUp and validated in a sandbox.",
  },
];

function HeroPreview() {
  return (
    <div aria-hidden className="relative mx-auto w-full max-w-md">
      <div className="absolute -inset-6 -z-10 rounded-[2rem] bg-primary/10 blur-2xl" />
      <div className="rounded-2xl border bg-card p-5 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs text-muted-foreground">Senior Software Engineer</p>
            <p className="font-semibold">Contoso Cloud · Hyderabad · Hybrid</p>
          </div>
          <div className="flex size-14 shrink-0 flex-col items-center justify-center rounded-full border-4 border-primary/25 text-primary">
            <span className="text-base leading-none font-bold">82%</span>
            <span className="text-[9px] text-muted-foreground">match</span>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-1.5">
          {["Python", "FastAPI", "PostgreSQL", "Azure"].map((s) => (
            <Badge key={s}>{s}</Badge>
          ))}
          {["Kubernetes", "Kafka"].map((s) => (
            <Badge key={s} variant="sunrise">
              Gap · {s}
            </Badge>
          ))}
        </div>
        <div className="mt-5 space-y-2 rounded-xl bg-muted p-3 text-sm">
          <p className="flex gap-2">
            <span className="font-medium text-primary">AI</span>
            <span className="text-muted-foreground">
              Walk me through how you&apos;d design rate limiting for this API.
            </span>
          </p>
          <p className="flex gap-2">
            <span className="font-medium">You</span>
            <span className="text-muted-foreground">
              I&apos;d start with a token bucket per user in Redis…
            </span>
          </p>
        </div>
        <div className="mt-4 flex gap-2">
          <span className="inline-flex h-8 flex-1 items-center justify-center gap-1.5 rounded-md bg-sunrise text-xs font-medium text-sunrise-foreground">
            <Mic className="size-3.5" /> Practice this interview
          </span>
          <span className="inline-flex h-8 flex-1 items-center justify-center rounded-md border text-xs font-medium">
            Take a skill test
          </span>
        </div>
      </div>
    </div>
  );
}

export default function LandingPage() {
  return (
    <>
      <section className="relative overflow-hidden" style={{ background: "var(--sky-gradient)" }}>
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 py-16 sm:px-6 md:py-24 lg:grid-cols-2">
          <div>
            <Badge variant="outline" className="mb-5 bg-card/60">
              AI-powered · free & open-source stack
            </Badge>
            <h1 className="text-4xl font-semibold sm:text-5xl lg:text-6xl">
              Find jobs.
              <br />
              Practice interviews.
              <br />
              <span className="text-primary">Get hired.</span>
            </h1>
            <p className="mt-6 max-w-xl text-lg text-muted-foreground">
              GlideUp matches your resume to real jobs, shows your skill gaps, runs job-specific mock
              interviews and coding tests, and tracks every application — from job search to offer.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild size="lg" variant="sunrise">
                <Link href="/login">
                  Get started free <ArrowRight />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <Link href="#how-it-works">See how it works</Link>
              </Button>
            </div>
          </div>
          <HeroPreview />
        </div>
      </section>

      <section id="features" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-20 sm:px-6">
        <div className="max-w-2xl">
          <p className="text-sm font-medium text-primary">Everything in one place</p>
          <h2 className="mt-2 text-3xl font-semibold">From your resume to your offer letter</h2>
          <p className="mt-3 text-muted-foreground">
            Every feature connects to one journey, so practice is always tied to a real job you want.
          </p>
        </div>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="rounded-xl border bg-card p-6">
              <span className="inline-flex size-10 items-center justify-center rounded-lg bg-primary-soft text-primary">
                <Icon className="size-5" aria-hidden />
              </span>
              <h3 className="mt-4 font-semibold">{title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{body}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="how-it-works" className="scroll-mt-20 border-y bg-card/50">
        <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
          <p className="text-sm font-medium text-primary">How it works</p>
          <h2 className="mt-2 text-3xl font-semibold">Five steps, one flight path</h2>
          <ol className="mt-10 grid gap-6 md:grid-cols-5">
            {JOURNEY.map(({ title, body, icon: Icon }, index) => (
              <li key={title} className="relative">
                <div className="flex items-center gap-3 md:flex-col md:items-start">
                  <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-full border-2 border-primary bg-background text-sm font-semibold text-primary">
                    {index + 1}
                  </span>
                  <Icon className="size-5 text-muted-foreground md:hidden" aria-hidden />
                </div>
                <h3 className="mt-3 font-semibold">{title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
        <div className="grid gap-6 md:grid-cols-3">
          {PRINCIPLES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="flex gap-4">
              <Icon className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
              <div>
                <h3 className="font-semibold">{title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{body}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-16 flex flex-col items-start justify-between gap-6 rounded-2xl bg-primary px-8 py-10 text-primary-foreground md:flex-row md:items-center">
          <div>
            <h2 className="text-2xl font-semibold">Ready for take-off?</h2>
            <p className="mt-2 opacity-85">
              Sign in with Google and upload your resume. It takes two minutes.
            </p>
          </div>
          <Button asChild size="lg" variant="sunrise">
            <Link href="/login">
              Start now <ArrowRight />
            </Link>
          </Button>
        </div>
      </section>
    </>
  );
}
