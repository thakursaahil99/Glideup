import Link from "next/link";

import { LogoMark } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main id="main" className="flex min-h-dvh flex-col items-center justify-center gap-4 px-4 text-center">
      <LogoMark className="size-12" />
      <h1 className="text-3xl font-semibold">Off the flight path</h1>
      <p className="max-w-sm text-muted-foreground">
        We couldn&apos;t find that page. It may have moved, or you may not have access.
      </p>
      <Button asChild>
        <Link href="/">Back to GlideUp</Link>
      </Button>
    </main>
  );
}
