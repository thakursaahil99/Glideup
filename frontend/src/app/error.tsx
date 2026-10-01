"use client";

import { RotateCw } from "lucide-react";

import { LogoMark } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main id="main" className="flex min-h-dvh flex-col items-center justify-center gap-4 px-4 text-center">
      <LogoMark className="size-12" />
      <h1 className="text-3xl font-semibold">Turbulence</h1>
      <p className="max-w-sm text-muted-foreground">
        Something went wrong on our side.{error.digest ? ` Reference: ${error.digest}.` : ""}
      </p>
      <Button onClick={reset}>
        <RotateCw /> Try again
      </Button>
    </main>
  );
}
