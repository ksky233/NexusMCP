import { Dialog } from "@base-ui/react/dialog";
import {
  Activity,
  Boxes,
  Braces,
  CheckCheck,
  Diamond,
  Gauge,
  Menu,
  Network,
  Search,
  ShieldAlert,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { Button } from "@/components/ui/button";
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

function currentSection(pathname: string): string {
  return (
    navigation.find(({ to, end }) => (end ? pathname === to : pathname.startsWith(to)))?.label ??
    "Not found"
  );
}

export function AppShell() {
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setMobileNavigationOpen(false);
  }, [location.pathname]);

  return (
    <div className="min-h-screen bg-canvas text-ink md:grid md:grid-cols-[256px_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-screen border-r border-slate/18 bg-paper md:flex md:flex-col">
        <SidebarContent />
      </aside>

      <Dialog.Root onOpenChange={setMobileNavigationOpen} open={mobileNavigationOpen}>
        <Dialog.Portal>
          <Dialog.Backdrop className="fixed inset-0 z-40 bg-ink/30 transition-opacity data-[ending-style]:opacity-0 data-[starting-style]:opacity-0 md:hidden" />
          <Dialog.Popup className="fixed inset-y-0 left-0 z-50 flex w-[min(86vw,280px)] flex-col border-r border-slate/25 bg-paper shadow-overlay transition-transform duration-200 data-[ending-style]:-translate-x-full data-[starting-style]:-translate-x-full md:hidden">
            <Dialog.Title className="sr-only">Control plane navigation</Dialog.Title>
            <Dialog.Close
              aria-label="Close navigation"
              className="absolute top-5 right-4 grid size-9 cursor-pointer place-items-center rounded-[3px] border border-slate/20 bg-paper text-slate outline-none hover:bg-mist focus-visible:ring-2 focus-visible:ring-slate/45"
            >
              <X aria-hidden="true" className="size-4" />
            </Dialog.Close>
            <SidebarContent onNavigate={() => setMobileNavigationOpen(false)} />
          </Dialog.Popup>
        </Dialog.Portal>
      </Dialog.Root>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 border-b border-slate/15 bg-paper/95 backdrop-blur">
          <div className="flex min-h-16 items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
            <div className="flex min-w-0 items-center gap-3">
              <Button
                aria-label="Open navigation"
                className="md:hidden"
                onClick={() => setMobileNavigationOpen(true)}
                size="icon"
                variant="ghost"
              >
                <Menu aria-hidden="true" className="size-5" />
              </Button>
              <span className="truncate text-xs font-normal tracking-[0.08em] text-slate/55">
                {currentSection(location.pathname)}
              </span>
            </div>
            <div className="flex items-center gap-2 text-right text-[11px] font-normal tracking-[0.04em] text-slate/60">
              <ShieldAlert aria-hidden="true" className="size-3.5 shrink-0" />
              <span className="hidden sm:inline">
                Local Development Admin · Not Production Authentication
              </span>
              <span className="sm:hidden">Local Admin</span>
            </div>
          </div>
        </header>

        <main className="min-w-0 px-4 py-8 sm:px-6 lg:px-8 lg:py-10 xl:px-10">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col px-6 py-7">
      <div className="flex items-center gap-3">
        <Diamond aria-hidden="true" className="size-5 stroke-[1.5] text-ink" />
        <div>
          <p className="text-lg font-light tracking-[0.1em] text-ink">NexusMCP</p>
          <p className="mt-0.5 text-[10px] font-normal uppercase tracking-[0.18em] text-slate/45">
            Control Plane
          </p>
        </div>
      </div>

      <p className="mt-10 px-3 text-[10px] font-normal uppercase tracking-[0.18em] text-slate/40">
        Governance
      </p>
      <nav aria-label="Control plane" className="mt-3 space-y-1">
        {navigation.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            className={({ isActive }) =>
              cn(
                "flex min-h-10 items-center gap-3 rounded-[3px] px-3 py-2 text-sm font-normal tracking-[0.015em] text-slate transition-[background-color,color,box-shadow] duration-200 hover:bg-mist hover:text-ink",
                isActive && "bg-mist/95 text-ink shadow-[inset_2px_0_0_#393e46]",
              )
            }
            end={end}
            key={to}
            onClick={onNavigate}
            to={to}
          >
            <Icon aria-hidden="true" className="size-4 shrink-0 stroke-[1.5]" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto border-t border-slate/15 pt-5">
        <p className="text-[10px] font-normal uppercase tracking-[0.16em] text-slate/40">
          Runtime boundary
        </p>
        <p className="mt-2 text-xs leading-5 text-slate/58">
          Fixed local tenant and principal. Backend remains the only policy authority.
        </p>
      </div>
    </div>
  );
}
