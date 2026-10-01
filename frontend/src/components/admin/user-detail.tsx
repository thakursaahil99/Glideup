"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Eye } from "lucide-react";
import Link from "next/link";

import { Avatar } from "@/components/layout/user-menu";
import { ParseStatus } from "@/components/resume/parse-status";
import { ResumeDetails } from "@/components/resume/resume-details";
import { groupSkills } from "@/components/resume/skills-editor";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, Skeleton } from "@/components/ui/primitives";
import { api, unwrap } from "@/lib/api/client";
import { formatDate, formatDateTime, humanize } from "@/lib/utils";

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm">{value || "—"}</dd>
    </div>
  );
}

/** Links are validated server-side to plain http(s) URLs before they are stored. */
function ExternalLink({ href }: { href: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className="break-all text-primary underline-offset-2 hover:underline"
    >
      {href.replace(/^https?:\/\/(www\.)?/, "")}
    </a>
  );
}

export function AdminUserDetail({ userId }: { userId: string }) {
  const query = useQuery({
    queryKey: ["admin", "user", userId],
    queryFn: () =>
      unwrap(api.GET("/api/v1/admin/users/{user_id}", { params: { path: { user_id: userId } } })),
    staleTime: 60_000, // every fetch is an audited view; don't refetch needlessly
  });

  return (
    <div className="mx-auto max-w-5xl">
      <Button asChild variant="ghost" size="sm" className="mb-4">
        <Link href="/admin/users">
          <ArrowLeft /> All users
        </Link>
      </Button>

      {query.isError ? (
        <Card>
          <ErrorState error={query.error} onRetry={() => query.refetch()} />
        </Card>
      ) : !query.data ? (
        <Skeleton className="h-96 w-full" />
      ) : (
        (() => {
          const { user, profile, resumes, active_resume: resume, llm_calls, suspended_reason } = query.data;
          return (
            <div className="space-y-6">
              <div className="flex flex-wrap items-center gap-4">
                <Avatar user={{ ...user, image: user.avatar_url, permissions: [] }} className="size-14" />
                <div className="min-w-0 flex-1">
                  <h1 className="truncate text-2xl font-semibold">{user.name ?? user.email}</h1>
                  <p className="text-muted-foreground">{user.email}</p>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {user.roles.map((r) => (
                    <Badge key={r} variant={r === "user" ? "muted" : "default"}>
                      {humanize(r)}
                    </Badge>
                  ))}
                  <Badge variant={user.status === "active" ? "success" : "destructive"}>
                    {humanize(user.status)}
                  </Badge>
                </div>
              </div>
              <p className="flex items-center gap-2 text-xs text-muted-foreground">
                <Eye className="size-3.5" aria-hidden /> This view of personal data was recorded in the audit
                log.
              </p>

              <div className="grid gap-6 lg:grid-cols-[20rem_1fr]">
                <Card className="h-fit">
                  <CardHeader>
                    <CardTitle>Account & profile</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <dl className="grid gap-4">
                      <Field label="Joined" value={formatDate(user.created_at)} />
                      <Field label="Last sign-in" value={formatDateTime(user.last_login_at)} />
                      {suspended_reason && <Field label="Suspension reason" value={suspended_reason} />}
                      <Field label="Headline" value={profile?.headline} />
                      <Field
                        label="Experience"
                        value={profile?.years_experience != null ? `${profile.years_experience} years` : null}
                      />
                      <Field
                        label="Portfolio"
                        value={profile?.portfolio_url && <ExternalLink href={profile.portfolio_url} />}
                      />
                      <Field
                        label="LinkedIn"
                        value={profile?.linkedin_url && <ExternalLink href={profile.linkedin_url} />}
                      />
                      <Field
                        label="GitHub"
                        value={profile?.github_url && <ExternalLink href={profile.github_url} />}
                      />
                      <Field label="Target roles" value={profile?.target_roles.join(", ")} />
                      <Field label="Locations" value={profile?.preferred_locations.join(", ")} />
                      <Field
                        label="Work style"
                        value={profile ? humanize(profile.remote_preference) : null}
                      />
                      <Field
                        label="Onboarding"
                        value={profile?.onboarding_completed ? "Completed" : "Not finished"}
                      />
                      <Field label="AI calls (all time)" value={llm_calls.toLocaleString()} />
                    </dl>
                  </CardContent>
                </Card>

                <div className="space-y-6">
                  <Card>
                    <CardHeader>
                      <CardTitle>Active resume</CardTitle>
                      <CardDescription>
                        {resume
                          ? `${resume.original_filename} · parsed by ${resume.parsed_by ?? "—"}`
                          : "No resume uploaded"}
                      </CardDescription>
                    </CardHeader>
                    {resume && (
                      <CardContent className="space-y-6">
                        {resume.status !== "parsed" && <ParseStatus resume={resume} />}
                        {groupSkills(resume.parsed?.skills ?? []).map((group) => (
                          <div key={group.category}>
                            <h4 className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                              {group.label}
                            </h4>
                            <div className="flex flex-wrap gap-1.5">
                              {group.skills.map((s) => (
                                <Badge key={s.name}>
                                  {s.name}
                                  {s.years != null && (
                                    <span className="text-muted-foreground">{s.years}y</span>
                                  )}
                                </Badge>
                              ))}
                            </div>
                          </div>
                        ))}
                        {resume.parsed && <ResumeDetails parsed={resume.parsed} />}
                      </CardContent>
                    )}
                  </Card>

                  {resumes.length > 0 && (
                    <Card>
                      <CardHeader>
                        <CardTitle>Resume history</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <ul className="divide-y text-sm">
                          {resumes.map((r) => (
                            <li key={r.id} className="flex items-center justify-between gap-3 py-2">
                              <span className="truncate">{r.original_filename}</span>
                              <span className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
                                {formatDate(r.created_at)}
                                <Badge variant={r.status === "failed" ? "destructive" : "muted"}>
                                  {r.status}
                                </Badge>
                                {r.is_active && <Badge variant="success">active</Badge>}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </CardContent>
                    </Card>
                  )}
                </div>
              </div>
            </div>
          );
        })()
      )}
    </div>
  );
}
