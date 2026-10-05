import type { Metadata } from "next";

import { InterviewRoom } from "@/components/interviews/interview-room";

export const metadata: Metadata = { title: "Interview" };

export default async function InterviewPage({ params }: PageProps<"/interviews/[interviewId]">) {
  const { interviewId } = await params;
  return <InterviewRoom interviewId={interviewId} />;
}
