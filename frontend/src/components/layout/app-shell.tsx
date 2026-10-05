"use client";

import { ArrowLeft, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Logo } from "@/components/brand/logo";
import { AnnouncementBanner } from "@/components/layout/announcement-banner";
import { SiteFooter } from "@/components/layout/site-footer";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { type MenuUser, UserMenu } from "@/components/layout/user-menu";
import { Badge } from "@/components/ui/primitives";
import { ADMIN_NAV, APP_NAV, hasPermission, isActive, type NavItem, visibleNav } from "@/lib/navigation";
import { cn } from "@/lib/utils";

type Variant = "app" | "admin";

function NavLink({ item, pathname }: { item: NavItem; pathname: string }) {
  const Icon = item.icon;
  if (item.phase) {
    return (
      <span
        aria-disabled
        title={`Coming in phase ${item.phase}`}
        className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground/70"
      >
        <Icon className="size-4" aria-hidden />
        <span className="flex-1 truncate">{item.label}</span>
        <Badge variant="muted" className="text-[10px]">
          Soon
        </Badge>
      </span>
    );
  }
  const active = isActive(pathname, item.href);
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
        active
          ? "bg-primary-soft text-primary"
          : "text-muted-foreground hover:bg-accent hover:text-foreground",
      )}
    >
      <Icon className="size-4" aria-hidden />
      <span className="truncate">{item.label}</span>
    </Link>
  );
}

export function AppShell({
  variant,
  user,
  children,
}: {
  variant: Variant;
  user: MenuUser;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const items = visibleNav(variant === "admin" ? ADMIN_NAV : APP_NAV, user.permissions);
  const mobileItems = items.slice(0, 5);
  const canAdmin = hasPermission(user.permissions, "admin:access");

  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 flex-col border-r bg-card/50 lg:flex">
        <div className="flex h-16 items-center gap-2 px-5">
          <Link href={variant === "admin" ? "/admin" : "/dashboard"} aria-label="GlideUp home">
            <Logo />
          </Link>
          {variant === "admin" && <Badge variant="sunrise">Admin</Badge>}
        </div>
        <nav
          aria-label={variant === "admin" ? "Admin" : "App"}
          className="flex-1 space-y-0.5 overflow-y-auto px-3 py-2"
        >
          {items.map((item) => (
            <NavLink key={item.href} item={item} pathname={pathname} />
          ))}
        </nav>
        <div className="border-t p-3">
          {variant === "admin" ? (
            <Link
              href="/dashboard"
              className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <ArrowLeft className="size-4" aria-hidden /> Back to app
            </Link>
          ) : (
            canAdmin && (
              <Link
                href="/admin"
                className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                <ShieldCheck className="size-4" aria-hidden /> Admin console
              </Link>
            )
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-4 border-b bg-background/80 px-4 backdrop-blur sm:px-6">
          <Link
            href={variant === "admin" ? "/admin" : "/dashboard"}
            className="lg:hidden"
            aria-label="GlideUp home"
          >
            <Logo />
          </Link>
          <div className="hidden lg:block" />
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <UserMenu user={user} />
          </div>
        </header>

        <AnnouncementBanner />
        <main id="main" className="flex-1 px-4 py-6 pb-24 sm:px-6 lg:px-8 lg:pb-8">
          {children}
        </main>
        <div className="hidden lg:block">
          <SiteFooter compact />
        </div>
      </div>

      {/* Mobile bottom navigation (PWA-style) */}
      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
      >
        <ul className="mx-auto flex max-w-md justify-around">
          {mobileItems.map((item) => {
            const Icon = item.icon;
            const active = isActive(pathname, item.href);
            if (item.phase) {
              return (
                <li key={item.href}>
                  <span
                    aria-disabled
                    title={`Coming in phase ${item.phase}`}
                    className="flex min-w-16 flex-col items-center gap-1 px-2 py-2 text-[11px] font-medium text-muted-foreground/50"
                  >
                    <Icon className="size-5" aria-hidden />
                    {item.label}
                  </span>
                </li>
              );
            }
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex min-w-16 flex-col items-center gap-1 px-2 py-2 text-[11px] font-medium",
                    active ? "text-primary" : "text-muted-foreground",
                  )}
                >
                  <Icon className="size-5" aria-hidden />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
