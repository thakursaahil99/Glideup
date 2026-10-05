import type { Metadata } from "next";

import { InterviewReportView } from "@/components/interviews/interview-report";

export const metadata: Metadata = { title: "Interview report" };

export default async function InterviewReportPage({
  params,
}: PageProps<"/interviews/[interviewId]/report">) {
  const { interviewId } = await params;
  return <InterviewReportView interviewId={interviewId} />;
}
