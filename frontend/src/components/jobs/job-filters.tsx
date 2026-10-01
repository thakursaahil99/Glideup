"use client";

import { Check, X } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { LocationFilters } from "@/components/jobs/location-filters";
import { Label, NativeSelect } from "@/components/ui/primitives";
import { TagInput } from "@/components/ui/tag-input";
import { activeFilterCount, EMPTY_FILTERS, type JobFilters } from "@/lib/api/jobs";
import { EXPERIENCE_LEVELS, WORK_MODES } from "@/lib/api/types";
import { cn } from "@/lib/utils";

type Facets = Record<string, Record<string, number>>;

function Chip({
  selected,
  onClick,
  children,
  count,
}: {
  selected: boolean;
  onClick: () => void;
  children: ReactNode;
  count?: number;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors",
        selected ? "border-primary bg-primary-soft text-primary" : "hover:bg-accent",
      )}
    >
      {selected && <Check className="size-3.5" aria-hidden />}
      {children}
      {count !== undefined && <span className="text-xs text-muted-foreground tabular-nums">{count}</span>}
    </button>
  );
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

export function JobFiltersPanel({
  filters,
  facets,
  onChange,
}: {
  filters: JobFilters;
  facets: Facets | undefined;
  onChange: (next: JobFilters) => void;
}) {
  const set = (patch: Partial<JobFilters>) => onChange({ ...filters, ...patch });
  const topCompanies = Object.entries(facets?.company ?? {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12);
  const topSkills = Object.entries(facets?.skills ?? {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Filters</h2>
        {activeFilterCount(filters) > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onChange({ ...EMPTY_FILTERS, q: filters.q, sort: filters.sort })}
          >
            <X /> Clear
          </Button>
        )}
      </div>

      <LocationFilters filters={filters} facets={facets} onChange={onChange} />

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Work style</legend>
        <div className="flex flex-wrap gap-2">
          {WORK_MODES.map((m) => (
            <Chip
              key={m.value}
              selected={filters.modes.includes(m.value)}
              count={facets?.work_mode?.[m.value]}
              onClick={() => set({ modes: toggle(filters.modes, m.value) })}
            >
              {m.label}
            </Chip>
          ))}
        </div>
      </fieldset>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Experience</legend>
        <div className="flex flex-wrap gap-2">
          {EXPERIENCE_LEVELS.map((l) => (
            <Chip
              key={l.value}
              selected={filters.levels.includes(l.value)}
              count={facets?.experience_level?.[l.value]}
              onClick={() => set({ levels: toggle(filters.levels, l.value) })}
            >
              {l.label}
            </Chip>
          ))}
        </div>
      </fieldset>

      <div className="space-y-1.5">
        <Label htmlFor="days">Date posted</Label>
        <NativeSelect
          id="days"
          value={filters.days ?? ""}
          onChange={(e) => set({ days: e.target.value ? Number(e.target.value) : null })}
        >
          <option value="">Any time</option>
          <option value="1">Last 24 hours</option>
          <option value="3">Last 3 days</option>
          <option value="7">Last week</option>
          <option value="30">Last month</option>
        </NativeSelect>
      </div>

      <div className="space-y-2">
        <Label htmlFor="skills">Skills (all must match)</Label>
        <TagInput
          id="skills"
          label="Add a skill filter"
          value={filters.skills}
          onChange={(skills) => set({ skills })}
          placeholder="e.g. Python, React"
          max={10}
        />
        {topSkills.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {topSkills
              .filter(([name]) => !filters.skills.includes(name))
              .slice(0, 8)
              .map(([name, count]) => (
                <Chip
                  key={name}
                  selected={false}
                  count={count}
                  onClick={() => set({ skills: [...filters.skills, name] })}
                >
                  {name}
                </Chip>
              ))}
          </div>
        )}
      </div>

      {topCompanies.length > 0 && (
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium">Company</legend>
          <div className="flex flex-wrap gap-2">
            {[...new Set([...filters.companies, ...topCompanies.map(([c]) => c)])].map((company) => (
              <Chip
                key={company}
                selected={filters.companies.includes(company)}
                count={facets?.company?.[company]}
                onClick={() => set({ companies: toggle(filters.companies, company) })}
              >
                {company}
              </Chip>
            ))}
          </div>
        </fieldset>
      )}
    </div>
  );
}
