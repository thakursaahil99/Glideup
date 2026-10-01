import { cn } from "@/lib/utils";

/**
 * GlideUp mark: a paraglider canopy tilted upward (a nod to Glide in Bir), with
 * lines converging on a sunrise-orange pilot. Original artwork; scales from 16px up.
 */
export function LogoMark({ className, title }: { className?: string; title?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={cn("size-8", className)}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      {/* canopy */}
      <path
        d="M3.5 15.5C8 8.5 17 4.5 28.5 5.5"
        fill="none"
        stroke="var(--primary)"
        strokeWidth="3.2"
        strokeLinecap="round"
      />
      {/* suspension lines */}
      <path
        d="M6.5 13.5L15.5 23M16 8.2L15.5 23M26 6L15.5 23"
        fill="none"
        stroke="var(--primary)"
        strokeOpacity="0.55"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
      {/* pilot */}
      <circle cx="15.5" cy="24.5" r="2.6" fill="var(--sunrise)" />
    </svg>
  );
}

export function Logo({ className, showMark = true }: { className?: string; showMark?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-semibold tracking-tight", className)}>
      {showMark && <LogoMark className="size-7" />}
      <span className="text-lg leading-none">
        Glide<span className="text-primary">Up</span>
      </span>
    </span>
  );
}
