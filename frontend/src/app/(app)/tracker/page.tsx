import type { Metadata } from "next";

import { TrackerBoard } from "@/components/tracker/tracker-board";

export const metadata: Metadata = { title: "Application tracker" };

export default function TrackerPage() {
  return <TrackerBoard />;
}
