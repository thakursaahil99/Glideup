import { AppShell } from "@/components/layout/app-shell";
import { requireUser } from "@/lib/session";

export default async function AppLayout({ children }: LayoutProps<"/">) {
  const user = await requireUser("/dashboard");
  return (
    <AppShell variant="app" user={user}>
      {children}
    </AppShell>
  );
}
