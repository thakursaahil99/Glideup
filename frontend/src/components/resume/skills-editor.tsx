"use client";

import { Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Badge, Input, NativeSelect } from "@/components/ui/primitives";
import { errorMessage } from "@/lib/api/client";
import { useSaveParsed } from "@/lib/api/hooks";
import { SKILL_CATEGORIES, type ParsedSkill, type Resume, type SkillCategory } from "@/lib/api/types";
import { humanize } from "@/lib/utils";

const CATEGORY_LABELS: Record<SkillCategory, string> = {
  language: "Languages",
  framework: "Frameworks & libraries",
  database: "Databases",
  cloud: "Cloud",
  devops: "DevOps & infrastructure",
  tool: "Tools",
  practice: "Practices",
  soft: "Soft skills",
  other: "Other",
};

export function groupSkills(skills: ParsedSkill[]) {
  const groups = new Map<SkillCategory, ParsedSkill[]>();
  for (const skill of skills) {
    const category = skill.category ?? "other";
    groups.set(category, [...(groups.get(category) ?? []), skill]);
  }
  return SKILL_CATEGORIES.filter((c) => groups.has(c)).map((c) => ({
    category: c,
    label: CATEGORY_LABELS[c],
    skills: groups.get(c)!,
  }));
}

function formatYears(years: number | null | undefined) {
  if (years === null || years === undefined) return null;
  return `${years % 1 === 0 ? years : years.toFixed(1)}y`;
}

function SkillsView({ skills }: { skills: ParsedSkill[] }) {
  if (!skills.length) {
    return <p className="text-sm text-muted-foreground">No skills found yet. Add them with Edit.</p>;
  }
  return (
    <div className="space-y-4">
      {groupSkills(skills).map((group) => (
        <div key={group.category}>
          <h4 className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            {group.label}
          </h4>
          <ul className="flex flex-wrap gap-1.5">
            {group.skills.map((skill) => (
              <li key={skill.name}>
                <Badge variant="default" className="gap-1.5 py-1 text-sm">
                  {skill.name}
                  {formatYears(skill.years) && (
                    <span className="text-xs font-normal text-muted-foreground">
                      {formatYears(skill.years)}
                    </span>
                  )}
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

type Row = { name: string; category: SkillCategory | ""; years: string };

function toRows(skills: ParsedSkill[]): Row[] {
  return skills.map((s) => ({ name: s.name, category: s.category ?? "", years: s.years?.toString() ?? "" }));
}

export function SkillsEditor({ resume }: { resume: Resume }) {
  const [editing, setEditing] = useState(false);
  const [rows, setRows] = useState<Row[]>([]);
  const save = useSaveParsed(resume.id);
  const parsed = resume.parsed;
  const skills = parsed?.skills ?? [];

  function startEditing() {
    setRows(toRows(skills));
    setEditing(true);
  }

  function update(index: number, patch: Partial<Row>) {
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function submit() {
    if (!parsed) return;
    const nextSkills = rows
      .filter((r) => r.name.trim())
      .map((r) => ({
        name: r.name.trim(),
        category: r.category || null,
        years: r.years === "" ? null : Number(r.years),
        level: null,
      }));
    save.mutate(
      { ...parsed, skills: nextSkills },
      {
        onSuccess: () => {
          toast.success("Skills saved");
          setEditing(false);
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  }

  if (!editing) {
    return (
      <div>
        <div className="mb-4 flex items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">
            {skills.length} skills{resume.user_edited_at ? " · edited by you" : ""}
          </p>
          <Button variant="outline" size="sm" onClick={startEditing} disabled={!parsed}>
            <Pencil /> Edit skills
          </Button>
        </div>
        <SkillsView skills={skills} />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Fix anything the parser got wrong. Years help us estimate your fit for each job.
      </p>
      <ul className="space-y-2">
        {rows.map((row, index) => (
          <li key={index} className="grid grid-cols-[1fr_auto] gap-2 sm:grid-cols-[1fr_11rem_6rem_auto]">
            <Input
              aria-label={`Skill ${index + 1} name`}
              value={row.name}
              maxLength={100}
              onChange={(e) => update(index, { name: e.target.value })}
            />
            <Button
              variant="ghost"
              size="icon"
              className="sm:order-last"
              aria-label={`Remove ${row.name || "skill"}`}
              onClick={() => setRows((current) => current.filter((_, i) => i !== index))}
            >
              <Trash2 />
            </Button>
            <NativeSelect
              aria-label={`Skill ${index + 1} category`}
              value={row.category}
              onChange={(e) => update(index, { category: e.target.value as SkillCategory | "" })}
            >
              <option value="">Category…</option>
              {SKILL_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {humanize(c)}
                </option>
              ))}
            </NativeSelect>
            <Input
              aria-label={`Skill ${index + 1} years`}
              type="number"
              min={0}
              max={60}
              step={0.5}
              placeholder="Years"
              value={row.years}
              onChange={(e) => update(index, { years: e.target.value })}
            />
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap justify-between gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setRows((current) => [...current, { name: "", category: "", years: "" }])}
        >
          <Plus /> Add skill
        </Button>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={() => setEditing(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={submit} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save skills"}
          </Button>
        </div>
      </div>
    </div>
  );
}
