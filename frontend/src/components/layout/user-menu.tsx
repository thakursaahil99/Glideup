"use client";

import { LayoutDashboard, LogOut, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { signOut } from "next-auth/react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Badge } from "@/components/ui/primitives";
import { hasPermission } from "@/lib/navigation";
import { humanize, initials } from "@/lib/utils";

export type MenuUser = {
  name?: string | null;
  email?: string | null;
  image?: string | null;
  roles: string[];
  permissions: string[];
};

export function Avatar({ user, className = "size-8" }: { user: MenuUser; className?: string }) {
  if (user.image) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- tiny remote avatar; optimisation not worth it
      <img
        src={user.image}
        alt=""
        className={`${className} rounded-full object-cover`}
        referrerPolicy="no-referrer"
      />
    );
  }
  return (
    <span
      aria-hidden
      className={`${className} inline-flex items-center justify-center rounded-full bg-primary-soft text-xs font-semibold text-primary`}
    >
      {initials(user.name, user.email)}
    </span>
  );
}

export function UserMenu({ user }: { user: MenuUser }) {
  const topRole = user.roles.find((r) => r !== "user");
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="rounded-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        aria-label="Account menu"
      >
        <Avatar user={user} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="flex flex-col gap-0.5">
          <span className="truncate font-medium">{user.name ?? "Your account"}</span>
          <span className="truncate text-xs text-muted-foreground">{user.email}</span>
          {topRole && (
            <Badge variant="sunrise" className="mt-1 w-fit">
              {humanize(topRole)}
            </Badge>
          )}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/dashboard">
            <LayoutDashboard /> Dashboard
          </Link>
        </DropdownMenuItem>
        {hasPermission(user.permissions, "admin:access") && (
          <DropdownMenuItem asChild>
            <Link href="/admin">
              <ShieldCheck /> Admin console
            </Link>
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => signOut({ redirectTo: "/" })}>
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
