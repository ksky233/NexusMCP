import {
  Activity,
  Boxes,
  Braces,
  CheckCheck,
  Gauge,
  Network,
  Search,
  ShieldAlert,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import { cn } from "@/lib/cn";

const navigation = [
  { to: "/", label: "Dashboard", icon: Gauge, end: true },
  { to: "/upstreams", label: "Upstreams", icon: Network, end: false },
  { to: "/imports", label: "Imports & Review", icon: Braces, end: false },
  { to: "/catalog", label: "Tool Catalog", icon: Boxes, end: false },
  { to: "/approvals", label: "Approvals", icon: CheckCheck, end: false },
  { to: "/executions", label: "Executions & Audit", icon: Activity, end: false },
  { to: "/search-lab", label: "Search Lab", icon: Search, end: false },
] as const;

export function AppShell() {
  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-30 border-b border-warning-line bg-warning-soft/95 px-4 py-2 backdrop-blur md:px-7">
        <div className="mx-auto flex max-w-[1600px] items-center justify-center gap-2 text-center text-xs font-semibold text-warning-ink">
          <ShieldAlert aria-hidden="true" className="size-4 shrink-0" />
          <span>Local Development Admin · Not Production Authentication</span>
        </div>
      </header>

      <div className="mx-auto grid min-h-[calc(100vh-37px)] max-w-[1600px] md:grid-cols-[248px_1fr]">
        <aside className="border-b border-line bg-sidebar px-4 py-5 text-white md:border-r md:border-b-0 md:px-5 md:py-7">
          <div className="flex items-center gap-3 px-2">
            <span className="grid size-10 place-items-center rounded-xl bg-accent text-sm font-black shadow-glow">
              NX
            </span>
            <div>
              <p className="font-semibold tracking-tight">NexusMCP</p>
              <p className="text-xs text-sidebar-muted">Control Plane</p>
            </div>
          </div>

          <nav aria-label="Control plane" className="mt-6 grid grid-cols-2 gap-1.5 md:grid-cols-1">
            {navigation.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                className={({ isActive }) =>
                  cn(
                    "flex min-h-10 items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-sidebar-muted transition-colors hover:bg-white/8 hover:text-white",
                    isActive && "bg-white/12 text-white shadow-inset",
                  )
                }
                end={end}
                key={to}
                to={to}
              >
                <Icon aria-hidden="true" className="size-4 shrink-0" />
                <span>{label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="mt-8 hidden rounded-xl border border-white/10 bg-white/5 p-4 md:block">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-sidebar-muted">
              Runtime boundary
            </p>
            <p className="mt-2 text-sm leading-6 text-white/85">
              Fixed local tenant and principal. Backend remains the only policy authority.
            </p>
          </div>
        </aside>

        <main className="min-w-0 px-4 py-6 sm:px-6 lg:px-10 lg:py-9">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
