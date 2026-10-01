"use client";

import { ArrowRight, Check } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ProfileForm } from "@/components/profile/profile-form";
import { ParseStatus } from "@/components/resume/parse-status";
import { ResumeDropzone } from "@/components/resume/resume-dropzone";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/primitives";
import { useActiveResume, useProfile } from "@/lib/api/hooks";
import { cn } from "@/lib/utils";

const STEPS = ["Upload resume", "Your preferences"] as const;

export function OnboardingFlow() {
  const router = useRouter();
  const [step, setStep] = useState<0 | 1>(0);
  const resume = useActiveResume();
  const profile = useProfile();

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold sm:text-3xl">Let&apos;s set up your flight plan</h1>
      <p className="mt-1 text-muted-foreground">Two quick steps. You can change everything later.</p>

      <ol className="mt-6 flex gap-4" aria-label="Progress">
        {STEPS.map((label, index) => (
          <li
            key={label}
            className="flex items-center gap-2 text-sm"
            aria-current={step === index ? "step" : undefined}
          >
            <span
              className={cn(
                "inline-flex size-7 items-center justify-center rounded-full border-2 text-xs font-semibold",
                index < step && "border-primary bg-primary text-primary-foreground",
                index === step && "border-primary text-primary",
                index > step && "border-muted-foreground/30 text-muted-foreground",
              )}
            >
              {index < step ? <Check className="size-3.5" /> : index + 1}
            </span>
            <span className={index === step ? "font-medium" : "text-muted-foreground"}>{label}</span>
          </li>
        ))}
      </ol>

      {step === 0 && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Upload your resume</CardTitle>
            <CardDescription>
              We extract your skills and experience to match you with jobs. Your file stays private to you.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {resume.isPending ? (
              <Skeleton className="h-40 w-full" />
            ) : resume.isError ? (
              <ErrorState error={resume.error} onRetry={() => resume.refetch()} />
            ) : (
              <>
                {resume.data && (
                  <div className="rounded-xl border p-4">
                    <p className="mb-3 text-sm font-medium">{resume.data.original_filename}</p>
                    <ParseStatus resume={resume.data} />
                  </div>
                )}
                <ResumeDropzone compact={Boolean(resume.data)} />
              </>
            )}
            <div className="flex justify-end">
              <Button onClick={() => setStep(1)} disabled={!resume.data}>
                Continue <ArrowRight />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === 1 && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>What are you looking for?</CardTitle>
            <CardDescription>
              We pre-filled what we could from your resume. These preferences shape your job matches.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {profile.data ? (
              <ProfileForm
                // Remount once parsing finishes so prefilled values (headline, years) appear.
                key={`${resume.data?.status}`}
                profile={profile.data}
                completeOnboarding
                submitLabel="Finish setup"
                onSaved={() => router.push("/dashboard")}
              />
            ) : profile.isError ? (
              <ErrorState error={profile.error} onRetry={() => profile.refetch()} />
            ) : (
              <Skeleton className="h-96 w-full" />
            )}
            <Button variant="ghost" className="mt-2" onClick={() => setStep(0)}>
              Back
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
