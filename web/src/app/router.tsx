import { createBrowserRouter } from "react-router-dom";

import { PlaceholderPage } from "@/components/common/placeholder-page";
import { NotFoundPage } from "@/components/common/not-found-page";
import { DashboardPage } from "@/features/dashboard/pages/dashboard-page";
import { AppShell } from "@/layouts/app-shell";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: AppShell,
    children: [
      { index: true, Component: DashboardPage },
      {
        path: "upstreams",
        element: (
          <PlaceholderPage
            eyebrow="Registry"
            title="Upstreams"
            description="HTTP/OpenAPI upstream registration and lifecycle arrive in W3."
          />
        ),
      },
      {
        path: "imports",
        element: (
          <PlaceholderPage
            eyebrow="OpenAPI"
            title="Imports & Review"
            description="Import jobs, conflicts, review and publish workflows arrive in W3."
          />
        ),
      },
      {
        path: "catalog",
        element: (
          <PlaceholderPage
            eyebrow="Catalog"
            title="Tool Catalog"
            description="Tool identity, version history and binding inspection arrive in W3."
          />
        ),
      },
      {
        path: "approvals",
        element: (
          <PlaceholderPage
            eyebrow="Governance"
            title="Approvals"
            description="Pending decisions and protected confirmation interactions arrive in W3."
          />
        ),
      },
      {
        path: "executions",
        element: (
          <PlaceholderPage
            eyebrow="Operations"
            title="Executions & Audit"
            description="Execution attempts, trace filters and audit timelines arrive in W3."
          />
        ),
      },
      {
        path: "search-lab",
        element: (
          <PlaceholderPage
            eyebrow="Retrieval"
            title="Search Lab"
            description="Lexical and Hybrid retrieval comparison is planned for W4."
          />
        ),
      },
      { path: "*", Component: NotFoundPage },
    ],
  },
]);
