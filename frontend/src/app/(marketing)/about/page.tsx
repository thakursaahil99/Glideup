import { ExternalLink } from "lucide-react";
import type { Metadata } from "next";

import { LogoMark } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "About" };

// TODO(Sahil): replace the placeholder URLs. Phase 10 moves this content into
// admin-editable site settings.
const LINKS = [
  { label: "GitHub", href: "https://github.com/your-username" },
  { label: "LinkedIn", href: "https://www.linkedin.com/in/your-profile" },
  { label: "Glide in Bir", href: "https://example.com/glide-in-bir" },
];

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6">
      <LogoMark className="size-12" />
      <h1 className="mt-6 text-4xl font-semibold">Built by Sahil Thakur</h1>
      <div className="mt-6 space-y-4 text-lg text-muted-foreground">
        <p>
          I&apos;m a full-stack developer with ten years of experience building products end to end — from
          database schemas and APIs to the interfaces people use every day.
        </p>
        <p>
          GlideUp started as the tool I wanted for my own job search: one place to find real roles, see
          honestly where I stand, and practice for the exact interview in front of me.
        </p>
        <p>
          The name and the paraglider in the logo come from <em>Glide in Bir</em>, my paragliding booking site
          in Bir Billing, India. Both projects are about the same thing: a good launch, steady practice, and
          going up.
        </p>
      </div>
      <div className="mt-10 flex flex-wrap gap-3">
        {LINKS.map((link) => (
          <Button key={link.label} asChild variant="outline">
            <a href={link.href} target="_blank" rel="noreferrer noopener">
              {link.label} <ExternalLink />
            </a>
          </Button>
        ))}
      </div>
    </div>
  );
}
