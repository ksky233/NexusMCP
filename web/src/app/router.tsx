import { createBrowserRouter } from "react-router-dom";

import { NotFoundPage } from "@/components/common/not-found-page";
import { AppShell } from "@/layouts/app-shell";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: AppShell,
    HydrateFallback: DashboardRouteFallback,
    children: [
      {
        index: true,
        HydrateFallback: DashboardRouteFallback,
        lazy: async () => {
          const { DashboardPage } = await import("@/features/dashboard/pages/dashboard-page");
          return { Component: DashboardPage };
        },
      },
      {
        path: "upstreams",
        lazy: async () => {
          const { UpstreamsPage } = await import("@/features/upstreams/pages/upstreams-page");
          return { Component: UpstreamsPage };
        },
      },
      {
        path: "upstreams/:upstreamId",
        lazy: async () => {
          const { UpstreamDetailPage } =
            await import("@/features/upstreams/pages/upstream-detail-page");
          return { Component: UpstreamDetailPage };
        },
      },
      {
        path: "imports",
        lazy: async () => {
          const { ImportsPage } = await import("@/features/imports/pages/imports-page");
          return { Component: ImportsPage };
        },
      },
      {
        path: "imports/:importId",
        lazy: async () => {
          const { ImportDetailPage } = await import("@/features/imports/pages/import-detail-page");
          return { Component: ImportDetailPage };
        },
      },
      {
        path: "catalog",
        lazy: async () => {
          const { CatalogPage } = await import("@/features/catalog/pages/catalog-page");
          return { Component: CatalogPage };
        },
      },
      {
        path: "catalog/:toolId",
        lazy: async () => {
          const { ToolDetailPage } = await import("@/features/catalog/pages/tool-detail-page");
          return { Component: ToolDetailPage };
        },
      },
      {
        path: "toolsets",
        lazy: async () => {
          const { ToolsetsPage } = await import("@/features/toolsets/pages/toolsets-page");
          return { Component: ToolsetsPage };
        },
      },
      {
        path: "toolsets/:toolsetId",
        lazy: async () => {
          const { ToolsetDetailPage } =
            await import("@/features/toolsets/pages/toolset-detail-page");
          return { Component: ToolsetDetailPage };
        },
      },
      {
        path: "approvals",
        lazy: async () => {
          const { ApprovalsPage } = await import("@/features/approvals/pages/approvals-page");
          return { Component: ApprovalsPage };
        },
      },
      {
        path: "executions",
        lazy: async () => {
          const { ExecutionsPage } = await import("@/features/executions/pages/executions-page");
          return { Component: ExecutionsPage };
        },
      },
      {
        path: "executions/:executionId",
        lazy: async () => {
          const { ExecutionDetailPage } =
            await import("@/features/executions/pages/execution-detail-page");
          return { Component: ExecutionDetailPage };
        },
      },
      {
        path: "search-lab",
        lazy: async () => {
          const { SearchLabPage } = await import("@/features/search-lab/pages/search-lab-page");
          return { Component: SearchLabPage };
        },
      },
      {
        path: "evidence",
        lazy: async () => {
          const { EvidencePage } = await import("@/features/evidence/pages/evidence-page");
          return { Component: EvidencePage };
        },
      },
      { path: "*", Component: NotFoundPage },
    ],
  },
]);

function DashboardRouteFallback() {
  return (
    <div className="state-panel" role="status">
      正在加载系统概览模块…
    </div>
  );
}
