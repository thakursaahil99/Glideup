"use client";

import { Flag } from "lucide-react";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label, NativeSelect, Textarea } from "@/components/ui/primitives";
import { errorMessage } from "@/lib/api/client";
import { useReportProblem } from "@/lib/api/tracker";
import type { ReportKind } from "@/lib/api/types";

const KINDS: { value: ReportKind; label: string }[] = [
  { value: "broken_job_link", label: "Broken or expired job link" },
  { value: "wrong_question", label: "Wrong question or test case" },
  { value: "bad_ai_feedback", label: "Unhelpful or wrong AI feedback" },
  { value: "other", label: "Something else" },
];

/** Lets users flag a problem; it lands in Admin → User Reports. */
export function ReportProblem({
  kind,
  targetType,
  targetId,
}: {
  kind: ReportKind;
  targetType?: string;
  targetId?: string;
}) {
  const pathname = usePathname();
  const report = useReportProblem();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<ReportKind>(kind);
  const [message, setMessage] = useState("");
  return (
    <>
      <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => setOpen(true)}>
        <Flag /> Report a problem
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Report a problem</DialogTitle>
            <DialogDescription>Our team reviews every report. You&apos;ll see our reply under your reports.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="r-kind">What&apos;s wrong?</Label>
            <NativeSelect id="r-kind" value={selected} onChange={(e) => setSelected(e.target.value as ReportKind)}>
              {KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="r-message">Details</Label>
            <Textarea id="r-message" value={message} onChange={(e) => setMessage(e.target.value)} maxLength={3000} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              disabled={message.trim().length < 5 || report.isPending}
              onClick={() =>
                report.mutate(
                  { kind: selected, message, target_type: targetType, target_id: targetId, page_url: pathname },
                  {
                    onSuccess: () => {
                      toast.success("Thanks, we'll take a look.");
                      setOpen(false);
                      setMessage("");
                    },
                    onError: (e) => toast.error(errorMessage(e)),
                  },
                )
              }
            >
              Send report
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
