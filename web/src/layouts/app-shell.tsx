import { Dialog } from "@base-ui/react/dialog";
import {
  Activity,
  Boxes,
  Braces,
  CheckCheck,
  Diamond,
  FileCheck2,
  FolderKanban,
  Gauge,
  Menu,
  Network,
  RotateCcw,
  Search,
  ShieldAlert,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useResetDemoWorkspace } from "@/features/demo/hooks/use-reset-demo-workspace";
import { asApiClientError } from "@/lib/api/api-error";
import { cn } from "@/lib/cn";
import { isPublicDemoMode } from "@/lib/runtime/public-demo";

const navigation = [
  { to: "/", label: "系统概览", icon: Gauge, end: true },
  { to: "/upstreams", label: "上游服务", icon: Network, end: false },
  { to: "/imports", label: "导入与审核", icon: Braces, end: false },
  { to: "/catalog", label: "工具目录", icon: Boxes, end: false },
  { to: "/toolsets", label: "工具集", icon: FolderKanban, end: false },
  { to: "/approvals", label: "审批管理", icon: CheckCheck, end: false },
  { to: "/executions", label: "执行与审计", icon: Activity, end: false },
  { to: "/search-lab", label: "检索实验", icon: Search, end: false },
  { to: "/evidence", label: "工程证据", icon: FileCheck2, end: false },
] as const;

function currentSection(pathname: string): string {
  return (
    navigation.find(({ to, end }) => (end ? pathname === to : pathname.startsWith(to)))?.label ??
    "页面不存在"
  );
}

export function AppShell() {
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const location = useLocation();
  const publicDemo = isPublicDemoMode();

  useEffect(() => {
    setMobileNavigationOpen(false);
  }, [location.pathname]);

  return (
    <div className="min-h-screen bg-canvas text-ink md:grid md:grid-cols-[256px_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-screen border-r border-slate/20 bg-paper md:flex md:flex-col">
        <SidebarContent />
      </aside>

      <Dialog.Root onOpenChange={setMobileNavigationOpen} open={mobileNavigationOpen}>
        <Dialog.Portal>
          <Dialog.Backdrop className="fixed inset-0 z-40 bg-ink/30 transition-opacity data-[ending-style]:opacity-0 data-[starting-style]:opacity-0 md:hidden" />
          <Dialog.Popup className="fixed inset-y-0 left-0 z-50 flex w-[min(86vw,280px)] flex-col border-r border-slate/25 bg-paper shadow-overlay transition-transform duration-200 data-[ending-style]:-translate-x-full data-[starting-style]:-translate-x-full md:hidden">
            <Dialog.Title className="sr-only">控制台导航</Dialog.Title>
            <Dialog.Close
              aria-label="关闭导航"
              className="absolute top-5 right-4 grid size-9 cursor-pointer place-items-center rounded-[4px] border border-slate/20 bg-paper text-slate outline-none hover:bg-mist focus-visible:ring-2 focus-visible:ring-slate/45"
            >
              <X aria-hidden="true" className="size-4" />
            </Dialog.Close>
            <SidebarContent onNavigate={() => setMobileNavigationOpen(false)} />
          </Dialog.Popup>
        </Dialog.Portal>
      </Dialog.Root>

      <div className="min-w-0">
        <header className="sticky top-0 z-30 border-b border-slate/20 bg-paper/95 backdrop-blur">
          <div className="flex min-h-16 items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
            <div className="flex min-w-0 items-center gap-3">
              <Button
                aria-label="打开导航"
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
            {publicDemo ? <PublicDemoControls /> : <LocalAdminStatus />}
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
        治理控制台
      </p>
      <nav aria-label="控制台导航" className="mt-3 space-y-1">
        {navigation.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            className={({ isActive }) =>
              cn(
                "flex min-h-10 items-center gap-3 rounded-[4px] px-3 py-2 text-sm font-normal tracking-[0.015em] text-slate transition-[background-color,color,box-shadow] duration-200 hover:bg-mist hover:text-ink",
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

      <div className="mt-auto border-t border-slate/20 pt-5">
        <p className="text-[10px] font-normal uppercase tracking-[0.16em] text-slate/40">
          运行边界
        </p>
        <p className="mt-2 text-xs leading-5 text-slate/58">
          {isPublicDemoMode()
            ? "公开访客共享 Demo Tenant 与 Principal，可随时恢复初始工作区。"
            : "固定本地租户与 Principal，后端始终是策略判定的唯一权威。"}
        </p>
      </div>
    </div>
  );
}

function LocalAdminStatus() {
  return (
    <div className="flex items-center gap-2 text-right text-[11px] font-normal tracking-[0.04em] text-slate/60">
      <ShieldAlert aria-hidden="true" className="size-3.5 shrink-0" />
      <span className="hidden sm:inline">本地开发管理员 · 非生产级身份认证</span>
      <span className="sm:hidden">本地管理员</span>
    </div>
  );
}

function PublicDemoControls() {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const resetWorkspace = useResetDemoWorkspace();
  const navigate = useNavigate();
  const errorMessage = resetWorkspace.error
    ? asApiClientError(resetWorkspace.error).message
    : undefined;

  async function handleReset() {
    try {
      await resetWorkspace.mutateAsync();
    } catch {
      return;
    }
    setConfirmOpen(false);
    await navigate("/");
  }

  return (
    <>
      <div className="flex items-center gap-2">
        <div className="hidden items-center gap-2 text-right text-[11px] font-normal tracking-[0.04em] text-slate/60 sm:flex">
          <ShieldAlert aria-hidden="true" className="size-3.5 shrink-0" />
          <span>公开演示身份 · public-demo-admin</span>
        </div>
        <Button
          aria-label="重置演示工作区"
          onClick={() => setConfirmOpen(true)}
          size="small"
          variant="secondary"
        >
          <RotateCcw aria-hidden="true" className="size-3.5" />
          <span className="hidden sm:inline">重置演示工作区</span>
          <span className="sm:hidden">重置</span>
        </Button>
      </div>
      <ConfirmDialog
        danger
        description="这会清空当前 Demo Tenant 的 Upstream、Import、Tool、Search Index、Execution 与 Audit，并恢复可以重新演示的空白工作区。"
        errorMessage={errorMessage}
        confirmLabel="确认重置"
        onConfirm={() => void handleReset()}
        onOpenChange={(open) => {
          setConfirmOpen(open);
          if (open) resetWorkspace.reset();
        }}
        open={confirmOpen}
        pending={resetWorkspace.isPending}
        title="恢复演示初始状态？"
      />
    </>
  );
}
