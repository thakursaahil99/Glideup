import { Badge } from "@/components/ui/primitives";
import type { MatchSummary } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type Tone = "success" | "default" | "sunrise" | "muted";

export function matchTone(score: number): Tone {
  if (score >= 75) return "success";
  if (score >= 55) return "default";
  if (score >= 35) return "sunrise";
  return "muted";
}

const RING_COLOR: Record<Tone, string> = {
  success: "var(--success)",
  default: "var(--primary)",
  sunrise: "var(--sunrise)",
  muted: "var(--muted-foreground)",
};

/** Compact "82% match" pill for job cards. */
export function MatchBadge({ match, className }: { match: MatchSummary; className?: string }) {
  const skills = match.total_skills ? ` · ${match.matched_skills}/${match.total_skills} skills` : "";
  return (
    <Badge
      variant={matchTone(match.score)}
      className={className}
      title={`${match.label}${skills}${match.partial ? " (based on skills only for now)" : ""}`}
    >
      {match.score}% match{match.partial && "*"}
    </Badge>
  );
}

/** Large circular score for the job page. */
export function ScoreRing({ score, size = 96 }: { score: number; size?: number }) {
  const stroke = 8;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const tone = matchTone(score);
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${score}% match`}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--muted)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={RING_COLOR[tone]}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - score / 100)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <span
        aria-hidden
        className={cn("absolute inset-0 flex items-center justify-center text-2xl font-semibold")}
      >
        {score}%
      </span>
    </div>
  );
}
