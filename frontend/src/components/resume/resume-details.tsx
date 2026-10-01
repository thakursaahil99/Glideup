import { Award, BriefcaseBusiness, ExternalLink, GraduationCap } from "lucide-react";

import type { ParsedResume } from "@/lib/api/types";

function period(start?: string | null, end?: string | null) {
  if (!start && !end) return null;
  return `${start ?? "?"} – ${end ?? "Present"}`;
}

/** Read-only view of what the parser extracted (experience, education, links). */
export function ResumeDetails({ parsed }: { parsed: ParsedResume }) {
  return (
    <div className="space-y-6">
      {parsed.summary && <p className="text-sm text-muted-foreground">{parsed.summary}</p>}

      {parsed.experience?.length ? (
        <section>
          <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <BriefcaseBusiness className="size-4 text-muted-foreground" aria-hidden /> Experience
          </h4>
          <ol className="space-y-4 border-l pl-4">
            {parsed.experience.map((job, i) => (
              <li key={`${job.company}-${i}`} className="relative">
                <span className="absolute top-1.5 -left-[21px] size-2.5 rounded-full border-2 border-primary bg-background" />
                <p className="font-medium">
                  {job.title} <span className="font-normal text-muted-foreground">· {job.company}</span>
                </p>
                {period(job.start, job.end) && (
                  <p className="text-xs text-muted-foreground">
                    {period(job.start, job.end)}
                    {job.location ? ` · ${job.location}` : ""}
                  </p>
                )}
                {job.highlights?.length ? (
                  <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-sm text-muted-foreground">
                    {job.highlights.map((h, j) => (
                      <li key={j}>{h}</li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {parsed.education?.length ? (
        <section>
          <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <GraduationCap className="size-4 text-muted-foreground" aria-hidden /> Education
          </h4>
          <ul className="space-y-1 text-sm">
            {parsed.education.map((e, i) => (
              <li key={i}>
                {e.degree}{" "}
                <span className="text-muted-foreground">
                  · {e.institution}
                  {e.year ? ` · ${e.year}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {parsed.certifications?.length ? (
        <section>
          <h4 className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <Award className="size-4 text-muted-foreground" aria-hidden /> Certifications
          </h4>
          <ul className="list-disc space-y-0.5 pl-5 text-sm">
            {parsed.certifications.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {parsed.links?.length ? (
        <section className="flex flex-wrap gap-3 text-sm">
          {parsed.links.map((link) => (
            <a
              key={link}
              href={link}
              target="_blank"
              rel="noreferrer noopener nofollow"
              className="inline-flex items-center gap-1 text-primary hover:underline"
            >
              {link.replace(/^https?:\/\/(www\.)?/, "")} <ExternalLink className="size-3" aria-hidden />
            </a>
          ))}
        </section>
      ) : null}
    </div>
  );
}
