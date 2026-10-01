import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { cn } from "@/lib/utils";

export function SiteFooter({ compact = false }: { compact?: boolean }) {
  return (
    <footer className={cn("border-t", compact ? "py-4" : "py-10")}>
      <div
        className={cn(
          "mx-auto flex max-w-6xl flex-col gap-4 px-4 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6",
        )}
      >
        {!compact && <Logo className="text-foreground" />}
        <p>
          Built by{" "}
          <Link href="/about" className="font-medium text-foreground underline-offset-4 hover:underline">
            Sahil Thakur
          </Link>
        </p>
        {!compact && (
          <nav aria-label="Footer" className="flex gap-5">
            <Link href="/about" className="hover:text-foreground">
              About
            </Link>
            <Link href="/login" className="hover:text-foreground">
              Sign in
            </Link>
          </nav>
        )}
      </div>
    </footer>
  );
}
