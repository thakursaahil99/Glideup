"use client";

import { Globe2, MapPin } from "lucide-react";

import { Label, NativeSelect } from "@/components/ui/primitives";
import type { JobFilters, RemoteFilter } from "@/lib/api/jobs";
import { cn } from "@/lib/utils";

type Facets = Record<string, Record<string, number>>;

const regionNames =
  typeof Intl.DisplayNames === "function" ? new Intl.DisplayNames(["en"], { type: "region" }) : null;
const number = new Intl.NumberFormat("en");

export function countryName(code: string): string {
  try {
    return regionNames?.of(code) ?? code;
  } catch {
    return code;
  }
}

/** Facet values sorted by count, keeping a selected value visible even if its count is 0. */
export function facetOptions(values: Record<string, number> | undefined, selected?: string) {
  const entries = Object.entries(values ?? {}).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  if (selected && !entries.some(([value]) => value === selected)) entries.unshift([selected, 0]);
  return entries;
}

type Scope = "all" | "india" | "international";

function currentScope(filters: JobFilters): Scope {
  if (filters.region === "international") return "international";
  if (filters.region === "india" || (filters.countries.length === 1 && filters.countries[0] === "IN"))
    return "india";
  return "all";
}

const NO_PLACE: Pick<JobFilters, "countries" | "states" | "cities" | "region"> = {
  countries: [],
  states: [],
  cities: [],
  region: null,
};

export function LocationFilters({
  filters,
  facets,
  onChange,
}: {
  filters: JobFilters;
  facets: Facets | undefined;
  onChange: (next: JobFilters) => void;
}) {
  const scope = currentScope(filters);
  const country = filters.countries[0] ?? "";
  const state = filters.states[0] ?? "";
  const city = filters.cities[0] ?? "";

  function setScope(next: Scope) {
    const base = { ...filters, ...NO_PLACE, location: "" };
    if (next === "india") onChange({ ...base, countries: ["IN"] });
    else if (next === "international")
      onChange({
        ...base,
        region: "international",
        remote: filters.remote === "india" ? null : filters.remote,
      });
    else onChange(base);
  }

  const countryOptions = facetOptions(facets?.countries, country || undefined).filter(
    ([code]) => scope !== "international" || code !== "IN",
  );
  const stateOptions = facetOptions(facets?.states, state || undefined);
  const cityOptions = facetOptions(facets?.cities, city || undefined);
  const showStates = Boolean(country) && stateOptions.length > 0;
  const showCities = Boolean(country) && cityOptions.length > 0;

  const remoteOptions: { value: RemoteFilter | null; label: string }[] = [
    { value: null, label: "Any" },
    { value: "india", label: "Remote - India" },
    { value: "worldwide", label: "Remote - Worldwide" },
  ];

  return (
    <div className="space-y-4">
      <div
        role="radiogroup"
        aria-label="Where"
        className="grid grid-cols-3 rounded-lg border bg-card p-0.5 text-sm"
      >
        {(
          [
            ["all", "All"],
            ["india", "India"],
            ["international", "International"],
          ] as [Scope, string][]
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={scope === value}
            onClick={() => setScope(value)}
            className={cn(
              "rounded-md px-2 py-1.5 font-medium transition-colors",
              scope === value
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="country" className="flex items-center gap-1.5">
          <Globe2 className="size-3.5 text-muted-foreground" aria-hidden /> Country
        </Label>
        <NativeSelect
          id="country"
          value={country}
          onChange={(e) => {
            const code = e.target.value;
            onChange({
              ...filters,
              location: "",
              countries: code ? [code] : [],
              states: [],
              cities: [],
              region: code ? null : filters.region,
            });
          }}
        >
          <option value="">{scope === "international" ? "Any country outside India" : "Any country"}</option>
          {countryOptions.map(([code, count]) => (
            <option key={code} value={code}>
              {countryName(code)} ({number.format(count)})
            </option>
          ))}
        </NativeSelect>
      </div>

      {showStates && (
        <div className="space-y-1.5">
          <Label htmlFor="state">{country === "IN" ? "State / UT" : "State / region"}</Label>
          <NativeSelect
            id="state"
            value={state}
            onChange={(e) =>
              onChange({ ...filters, states: e.target.value ? [e.target.value] : [], cities: [] })
            }
          >
            <option value="">Any state</option>
            {stateOptions.map(([name, count]) => (
              <option key={name} value={name}>
                {name} ({number.format(count)})
              </option>
            ))}
          </NativeSelect>
        </div>
      )}

      {showCities && (
        <div className="space-y-1.5">
          <Label htmlFor="city" className="flex items-center gap-1.5">
            <MapPin className="size-3.5 text-muted-foreground" aria-hidden /> City
          </Label>
          <NativeSelect
            id="city"
            value={city}
            onChange={(e) => onChange({ ...filters, cities: e.target.value ? [e.target.value] : [] })}
          >
            <option value="">Any city</option>
            {cityOptions.map(([name, count]) => (
              <option key={name} value={name}>
                {name} ({number.format(count)})
              </option>
            ))}
          </NativeSelect>
        </div>
      )}

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Remote</legend>
        <div className="flex flex-wrap gap-2">
          {remoteOptions.map((option) => {
            const selected = filters.remote === option.value;
            const disabled = option.value === "india" && scope === "international";
            return (
              <label
                key={option.label}
                className={cn(
                  "cursor-pointer rounded-full border px-3 py-1 text-sm transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
                  selected ? "border-primary bg-primary-soft text-primary" : "hover:bg-accent",
                  disabled && "pointer-events-none opacity-40",
                )}
              >
                <input
                  type="radio"
                  name="remote"
                  className="sr-only"
                  checked={selected}
                  disabled={disabled}
                  onChange={() => onChange({ ...filters, remote: option.value })}
                />
                {option.label}
              </label>
            );
          })}
        </div>
      </fieldset>
    </div>
  );
}

export function remoteLabel(job: { work_mode: string; remote_scope?: string | null; countries?: string[] }) {
  if (job.work_mode !== "remote") return null;
  if (job.remote_scope === "worldwide" || !job.countries?.length) return "Remote · Worldwide";
  return `Remote · ${job.countries.map(countryName).join(", ")}`;
}
