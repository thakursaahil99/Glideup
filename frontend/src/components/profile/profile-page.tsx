"use client";

import { ExternalLink, FileText, MoreHorizontal, RotateCw, Star, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { SkillsCard } from "@/components/profile/skills-card";
import { ProfileForm } from "@/components/profile/profile-form";
import { ParseStatus } from "@/components/resume/parse-status";
import { ResumeDetails } from "@/components/resume/resume-details";
import { ResumeDropzone } from "@/components/resume/resume-dropzone";
import { SkillsEditor } from "@/components/resume/skills-editor";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Badge, Skeleton } from "@/components/ui/primitives";
import { errorMessage } from "@/lib/api/client";
import { useActiveResume, useProfile, useResumeAction, useResumes } from "@/lib/api/hooks";
import type { ResumeSummary } from "@/lib/api/types";
import { formatDate } from "@/lib/utils";

function ResumeHistory() {
  const resumes = useResumes();
  const activate = useResumeAction("activate");
  const reparse = useResumeAction("reparse");
  const remove = useResumeAction("delete");
  const [toDelete, setToDelete] = useState<ResumeSummary | null>(null);

  if (!resumes.data || resumes.data.length < 1) return null;
  const onError = (e: unknown) => toast.error(errorMessage(e));

  return (
    <Card>
      <CardHeader>
        <CardTitle>All resumes</CardTitle>
        <CardDescription>The active resume is used for job matching.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="divide-y">
          {resumes.data.map((r) => (
            <li key={r.id} className="flex items-center gap-3 py-3">
              <FileText className="size-5 shrink-0 text-muted-foreground" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{r.original_filename}</p>
                <p className="text-xs text-muted-foreground">
                  {formatDate(r.created_at)} · {r.page_count ?? "?"} page{r.page_count === 1 ? "" : "s"} ·{" "}
                  {r.status}
                </p>
              </div>
              {r.is_active && <Badge variant="success">Active</Badge>}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${r.original_filename}`}>
                    <MoreHorizontal />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem asChild>
                    <a href={`/api/backend/resumes/${r.id}/file`} target="_blank" rel="noreferrer">
                      <ExternalLink /> View PDF
                    </a>
                  </DropdownMenuItem>
                  {!r.is_active && (
                    <DropdownMenuItem onSelect={() => activate.mutate(r.id, { onError })}>
                      <Star /> Make active
                    </DropdownMenuItem>
                  )}
                  {r.status !== "parsing" && (
                    <DropdownMenuItem
                      onSelect={() =>
                        reparse.mutate(r.id, {
                          onError,
                          onSuccess: () => toast.success("Re-parsing started"),
                        })
                      }
                    >
                      <RotateCw /> Parse again
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem onSelect={() => setToDelete(r)} className="text-destructive">
                    <Trash2 /> Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </li>
          ))}
        </ul>
      </CardContent>
      {toDelete && (
        <Dialog open onOpenChange={(open) => !open && setToDelete(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Delete this resume?</DialogTitle>
              <DialogDescription>
                <span className="font-medium text-foreground">{toDelete.original_filename}</span> and its
                parsed data will be permanently deleted.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline">Cancel</Button>
              </DialogClose>
              <Button
                variant="destructive"
                disabled={remove.isPending}
                onClick={() =>
                  remove.mutate(toDelete.id, {
                    onError,
                    onSuccess: () => {
                      toast.success("Resume deleted");
                      setToDelete(null);
                    },
                  })
                }
              >
                Delete resume
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </Card>
  );
}

export function ProfilePage() {
  const profile = useProfile();
  const resume = useActiveResume();

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Profile" description="Your resume, skills and job preferences." />
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <div className="space-y-6">
          <Card>
            <CardHeader className="flex-row items-start justify-between gap-4">
              <div>
                <CardTitle>Resume & skills</CardTitle>
                <CardDescription>
                  {resume.data ? resume.data.original_filename : "Upload a PDF to get started"}
                </CardDescription>
              </div>
              {resume.data && (
                <Button variant="outline" size="sm" asChild>
                  <a href={`/api/backend/resumes/${resume.data.id}/file`} target="_blank" rel="noreferrer">
                    <ExternalLink /> View PDF
                  </a>
                </Button>
              )}
            </CardHeader>
            <CardContent className="space-y-6">
              {resume.isPending ? (
                <Skeleton className="h-48 w-full" />
              ) : resume.isError ? (
                <ErrorState error={resume.error} onRetry={() => resume.refetch()} />
              ) : !resume.data ? (
                <>
                  <EmptyState
                    icon={<FileText className="size-5" aria-hidden />}
                    title="No resume yet"
                    body="Upload your resume and we'll pull out your skills and experience."
                  />
                  <ResumeDropzone />
                </>
              ) : (
                <>
                  {resume.data.status !== "parsed" && <ParseStatus resume={resume.data} />}
                  {resume.data.status === "parsed" && (
                    <>
                      {resume.data.parsed_by?.startsWith("mock") && <ParseStatus resume={resume.data} />}
                      <SkillsEditor
                        key={resume.data.id + (resume.data.user_edited_at ?? "")}
                        resume={resume.data}
                      />
                      {resume.data.parsed && <ResumeDetails parsed={resume.data.parsed} />}
                    </>
                  )}
                  <details className="rounded-xl border p-4">
                    <summary className="cursor-pointer text-sm font-medium">Upload a newer resume</summary>
                    <div className="mt-4">
                      <ResumeDropzone compact />
                    </div>
                  </details>
                </>
              )}
            </CardContent>
          </Card>
          <ResumeHistory />
          <SkillsCard />
        </div>

        <Card className="h-fit">
          <CardHeader>
            <CardTitle>Preferences</CardTitle>
            <CardDescription>Used to rank jobs for you.</CardDescription>
          </CardHeader>
          <CardContent>
            {profile.data ? (
              <ProfileForm key={profile.dataUpdatedAt} profile={profile.data} />
            ) : profile.isError ? (
              <ErrorState error={profile.error} onRetry={() => profile.refetch()} />
            ) : (
              <Skeleton className="h-96 w-full" />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
