"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/primitives";
import { TagInput } from "@/components/ui/tag-input";
import { errorMessage } from "@/lib/api/client";
import { useUpdateProfile } from "@/lib/api/hooks";
import type { Profile, RemotePreference } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const REMOTE_OPTIONS: { value: RemotePreference; label: string }[] = [
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
  { value: "onsite", label: "On-site" },
  { value: "any", label: "Open to all" },
];

const LINK_FIELDS = [
  { key: "portfolio_url", label: "Portfolio", placeholder: "yourname.dev" },
  { key: "linkedin_url", label: "LinkedIn", placeholder: "linkedin.com/in/yourname" },
  { key: "github_url", label: "GitHub", placeholder: "github.com/yourname" },
] as const;

type LinkKey = (typeof LINK_FIELDS)[number]["key"];

export function ProfileForm({
  profile,
  submitLabel = "Save profile",
  completeOnboarding = false,
  onSaved,
}: {
  profile: Profile;
  submitLabel?: string;
  completeOnboarding?: boolean;
  onSaved?: (profile: Profile) => void;
}) {
  const [name, setName] = useState(profile.name ?? "");
  const [headline, setHeadline] = useState(profile.headline ?? "");
  const [years, setYears] = useState(profile.years_experience?.toString() ?? "");
  const [roles, setRoles] = useState(profile.target_roles);
  const [locations, setLocations] = useState(profile.preferred_locations);
  const [remote, setRemote] = useState<RemotePreference>(profile.remote_preference);
  const [bio, setBio] = useState(profile.bio ?? "");
  const [links, setLinks] = useState<Record<LinkKey, string>>({
    portfolio_url: profile.portfolio_url ?? "",
    linkedin_url: profile.linkedin_url ?? "",
    github_url: profile.github_url ?? "",
  });
  const update = useUpdateProfile();

  function submit(event: FormEvent) {
    event.preventDefault();
    update.mutate(
      {
        name: name || null,
        headline: headline || null,
        bio: bio || null,
        years_experience: years === "" ? null : Number(years),
        portfolio_url: links.portfolio_url || null,
        linkedin_url: links.linkedin_url || null,
        github_url: links.github_url || null,
        target_roles: roles,
        preferred_locations: locations,
        remote_preference: remote,
        complete_onboarding: completeOnboarding,
      },
      {
        onSuccess: (saved) => {
          toast.success("Profile saved");
          onSaved?.(saved);
        },
        onError: (e) => toast.error(errorMessage(e)),
      },
    );
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="grid gap-5 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="name">Full name</Label>
          <Input
            id="name"
            value={name}
            maxLength={200}
            onChange={(e) => setName(e.target.value)}
            autoComplete="name"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="years">Years of experience</Label>
          <Input
            id="years"
            type="number"
            min={0}
            max={60}
            step={0.5}
            value={years}
            onChange={(e) => setYears(e.target.value)}
          />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="headline">Headline</Label>
        <Input
          id="headline"
          value={headline}
          maxLength={200}
          placeholder="e.g. Senior Full-Stack Engineer"
          onChange={(e) => setHeadline(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="roles">Target roles</Label>
        <TagInput
          id="roles"
          label="Add a target role"
          value={roles}
          onChange={setRoles}
          placeholder="Type a role and press Enter"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="locations">Preferred locations</Label>
        <TagInput
          id="locations"
          label="Add a location"
          value={locations}
          onChange={setLocations}
          placeholder="e.g. Bengaluru, Remote (India)"
        />
      </div>
      <fieldset className="space-y-1.5">
        <legend className="text-sm font-medium">Work style</legend>
        <div className="mt-1.5 flex flex-wrap gap-2">
          {REMOTE_OPTIONS.map((option) => (
            <label
              key={option.value}
              className={cn(
                "cursor-pointer rounded-lg border px-3 py-2 text-sm transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring",
                remote === option.value ? "border-primary bg-primary-soft text-primary" : "hover:bg-accent",
              )}
            >
              <input
                type="radio"
                name="remote"
                value={option.value}
                checked={remote === option.value}
                onChange={() => setRemote(option.value)}
                className="sr-only"
              />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset className="space-y-1.5">
        <legend className="text-sm font-medium">Links (optional)</legend>
        <p className="text-xs text-muted-foreground">
          Recruiters see these next to your resume. We fill them in from your resume when we can.
        </p>
        <div className="mt-1.5 grid gap-3 sm:grid-cols-3">
          {LINK_FIELDS.map((field) => (
            <div key={field.key} className="space-y-1.5">
              <Label htmlFor={field.key}>{field.label}</Label>
              <Input
                id={field.key}
                inputMode="url"
                autoComplete="url"
                maxLength={300}
                value={links[field.key]}
                placeholder={field.placeholder}
                onChange={(e) => setLinks((current) => ({ ...current, [field.key]: e.target.value }))}
              />
            </div>
          ))}
        </div>
      </fieldset>
      <div className="space-y-1.5">
        <Label htmlFor="bio">About you (optional)</Label>
        <Textarea
          id="bio"
          value={bio}
          maxLength={2000}
          onChange={(e) => setBio(e.target.value)}
          placeholder="What kind of work energises you? Anything recruiters should know?"
        />
      </div>
      <Button type="submit" disabled={update.isPending}>
        {update.isPending ? "Saving…" : submitLabel}
      </Button>
    </form>
  );
}
