"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, MoreHorizontal, Search, ShieldCheck, UserCheck, UserX } from "lucide-react";
import Link from "next/link";
import { useSession } from "next-auth/react";
import { useState } from "react";
import { toast } from "sonner";

import { Pagination } from "@/components/admin/pagination";
import { Avatar } from "@/components/layout/user-menu";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Badge, Input, Label, NativeSelect, Skeleton, Textarea } from "@/components/ui/primitives";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, errorMessage, unwrap } from "@/lib/api/client";
import { ROLE_NAMES, type RoleName, type UserStatus, type UserSummary } from "@/lib/api/types";
import { downloadCsv } from "@/lib/csv";
import { useDebouncedValue } from "@/lib/hooks";
import { formatDate, formatDateTime, humanize } from "@/lib/utils";

const PAGE_SIZE = 20;
const ADMIN_ROLES: RoleName[] = ["admin", "super_admin"];

type Action = { kind: "role" | "status"; user: UserSummary } | null;

function StatusBadge({ status }: { status: UserStatus }) {
  return status === "active" ? (
    <Badge variant="success">Active</Badge>
  ) : (
    <Badge variant="destructive">Suspended</Badge>
  );
}

export function UsersAdmin() {
  const { data: session } = useSession();
  const permissions = session?.user?.permissions ?? [];
  const canWrite = permissions.includes("users:write");
  const canAssign = permissions.includes("roles:assign");
  const canAssignAdmin = permissions.includes("roles:assign_admin");

  const [search, setSearch] = useState("");
  const [role, setRole] = useState<RoleName | "">("");
  const [status, setStatus] = useState<UserStatus | "">("");
  const [page, setPage] = useState(1);
  const [action, setAction] = useState<Action>(null);
  const debouncedSearch = useDebouncedValue(search.trim());

  const filters = {
    search: debouncedSearch || undefined,
    role: role || undefined,
    status: status || undefined,
  };
  const query = useQuery({
    queryKey: ["admin", "users", filters, page],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/users", { params: { query: { ...filters, page, page_size: PAGE_SIZE } } }),
      ),
    placeholderData: keepPreviousData,
  });

  const resetPage =
    <T,>(setter: (v: T) => void) =>
    (value: T) => {
      setter(value);
      setPage(1);
    };

  function exportCsv() {
    const items = query.data?.items ?? [];
    downloadCsv(
      `glideup-users-page-${page}.csv`,
      ["id", "email", "name", "roles", "status", "last_login_at", "created_at"],
      items.map((u) => [u.id, u.email, u.name, u.roles.join(" "), u.status, u.last_login_at, u.created_at]),
    );
  }

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Users"
        description="Search people, change roles and suspend accounts. Every change is audited."
        actions={
          <Button variant="outline" size="sm" onClick={exportCsv} disabled={!query.data?.items.length}>
            <Download /> Export CSV
          </Button>
        }
      />

      <Card>
        <div className="flex flex-col gap-3 border-b p-4 md:flex-row">
          <div className="relative flex-1">
            <Search
              aria-hidden
              className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              type="search"
              placeholder="Search by name or email"
              aria-label="Search users"
              value={search}
              onChange={(e) => resetPage(setSearch)(e.target.value)}
              className="pl-9"
            />
          </div>
          <NativeSelect
            aria-label="Filter by role"
            value={role}
            onChange={(e) => resetPage(setRole)(e.target.value as RoleName | "")}
            className="md:w-48"
          >
            <option value="">All roles</option>
            {ROLE_NAMES.map((r) => (
              <option key={r} value={r}>
                {humanize(r)}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect
            aria-label="Filter by status"
            value={status}
            onChange={(e) => resetPage(setStatus)(e.target.value as UserStatus | "")}
            className="md:w-40"
          >
            <option value="">Any status</option>
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
          </NativeSelect>
        </div>

        {query.isError ? (
          <ErrorState error={query.error} onRetry={() => query.refetch()} />
        ) : query.isPending ? (
          <div className="space-y-3 p-4">
            {Array.from({ length: 6 }, (_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : query.data.items.length === 0 ? (
          <EmptyState title="No users found" body="Try a different search or clear the filters." />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="hidden md:table-cell">Last sign-in</TableHead>
                  <TableHead className="hidden lg:table-cell">Joined</TableHead>
                  <TableHead className="w-12">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.data.items.map((user) => {
                  const isSelf = user.id === session?.user?.id;
                  const showActions = !isSelf && (canWrite || canAssign);
                  return (
                    <TableRow key={user.id}>
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <Avatar user={{ ...user, image: user.avatar_url, permissions: [] }} />
                          <div className="min-w-0">
                            <Link
                              href={`/admin/users/${user.id}`}
                              className="block truncate font-medium hover:text-primary hover:underline"
                            >
                              {user.name ?? user.email}{" "}
                              {isSelf && <span className="text-xs text-muted-foreground">(you)</span>}
                            </Link>
                            <p className="truncate text-xs text-muted-foreground">{user.email}</p>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {user.roles.map((r) => (
                            <Badge key={r} variant={r === "user" ? "muted" : "default"}>
                              {humanize(r)}
                            </Badge>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={user.status} />
                      </TableCell>
                      <TableCell className="hidden text-muted-foreground md:table-cell">
                        {formatDateTime(user.last_login_at)}
                      </TableCell>
                      <TableCell className="hidden text-muted-foreground lg:table-cell">
                        {formatDate(user.created_at)}
                      </TableCell>
                      <TableCell>
                        {showActions && (
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${user.email}`}>
                                <MoreHorizontal />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              {canAssign && (
                                <DropdownMenuItem onSelect={() => setAction({ kind: "role", user })}>
                                  <ShieldCheck /> Change role…
                                </DropdownMenuItem>
                              )}
                              {canWrite && (
                                <DropdownMenuItem onSelect={() => setAction({ kind: "status", user })}>
                                  {user.status === "active" ? <UserX /> : <UserCheck />}
                                  {user.status === "active" ? "Suspend…" : "Unsuspend…"}
                                </DropdownMenuItem>
                              )}
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            <Pagination page={page} pageSize={PAGE_SIZE} total={query.data.total} onPageChange={setPage} />
          </>
        )}
      </Card>

      {action?.kind === "role" && (
        <ChangeRoleDialog
          user={action.user}
          roles={canAssignAdmin ? ROLE_NAMES : ROLE_NAMES.filter((r) => !ADMIN_ROLES.includes(r))}
          onClose={() => setAction(null)}
        />
      )}
      {action?.kind === "status" && <StatusDialog user={action.user} onClose={() => setAction(null)} />}
    </div>
  );
}

function useInvalidateUsers() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: ["admin"] });
}

function ChangeRoleDialog({
  user,
  roles,
  onClose,
}: {
  user: UserSummary;
  roles: RoleName[];
  onClose: () => void;
}) {
  const current = (user.roles.find((r) => r !== "user") ?? "user") as RoleName;
  const [role, setRole] = useState<RoleName>(roles.includes(current) ? current : "user");
  const invalidate = useInvalidateUsers();
  const mutation = useMutation({
    mutationFn: () =>
      unwrap(
        api.PUT("/api/v1/admin/users/{user_id}/role", {
          params: { path: { user_id: user.id } },
          body: { role },
        }),
      ),
    onSuccess: () => {
      toast.success(`${user.email} is now ${humanize(role)}`);
      invalidate();
      onClose();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Change role</DialogTitle>
          <DialogDescription>
            Set the role for <span className="font-medium text-foreground">{user.email}</span>. The change
            applies immediately and is recorded in the audit log.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="role">Role</Label>
          <NativeSelect id="role" value={role} onChange={(e) => setRole(e.target.value as RoleName)}>
            {roles.map((r) => (
              <option key={r} value={r}>
                {humanize(r)}
              </option>
            ))}
          </NativeSelect>
          {ADMIN_ROLES.includes(role) && (
            <p className="text-xs text-warning">This grants administrative access to GlideUp.</p>
          )}
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || user.roles.join() === role}
          >
            {mutation.isPending ? "Saving…" : "Save role"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function StatusDialog({ user, onClose }: { user: UserSummary; onClose: () => void }) {
  const suspending = user.status === "active";
  const [reason, setReason] = useState("");
  const invalidate = useInvalidateUsers();
  const mutation = useMutation({
    mutationFn: () =>
      unwrap(
        api.PUT("/api/v1/admin/users/{user_id}/status", {
          params: { path: { user_id: user.id } },
          body: {
            status: suspending ? "suspended" : "active",
            reason: suspending ? reason.trim() || null : null,
          },
        }),
      ),
    onSuccess: () => {
      toast.success(suspending ? `${user.email} suspended` : `${user.email} reactivated`);
      invalidate();
      onClose();
    },
    onError: (error) => toast.error(errorMessage(error)),
  });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{suspending ? "Suspend this account?" : "Reactivate this account?"}</DialogTitle>
          <DialogDescription>
            {suspending ? (
              <>
                <span className="font-medium text-foreground">{user.email}</span> will be signed out
                everywhere and can&apos;t sign in until reactivated.
              </>
            ) : (
              <>
                <span className="font-medium text-foreground">{user.email}</span> will be able to sign in
                again.
              </>
            )}
          </DialogDescription>
        </DialogHeader>
        {suspending && (
          <div className="space-y-1.5">
            <Label htmlFor="reason">Reason (internal)</Label>
            <Textarea
              id="reason"
              value={reason}
              maxLength={500}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Spam reports from several users"
            />
          </div>
        )}
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button
            variant={suspending ? "destructive" : "default"}
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Saving…" : suspending ? "Suspend account" : "Reactivate"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
