import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";

import { createAppQueryClient } from "@/app/query-client";
import { ToolsetDetailPage } from "@/features/toolsets/pages/toolset-detail-page";
import { ToolsetsPage } from "@/features/toolsets/pages/toolsets-page";
import type { ToolPageResponse, ToolsetResponse } from "@/generated/api/types.gen";
import { server } from "@/test/mocks/server";

const toolset: ToolsetResponse = {
  id: "toolset-1",
  tenant_id: "tenant-a",
  slug: "operations",
  name: "Operations",
  description: "Operations agent tools",
  kind: "explicit",
  discovery_mode: "direct",
  status: "active",
  revision: 4,
  membership_digest: "a".repeat(64),
  endpoint_path: "/mcp/toolsets/operations",
  health: "healthy",
  tool_count: 1,
  available_tool_count: 1,
  serialized_schema_size: 512,
  grant_count: 1,
  principal_ids: ["operations-agent"],
  members: [
    {
      tool_id: "tool-a",
      canonical_name: "operations.get_incident",
      description: "Get an incident",
      availability: "available",
      published_tool_version_id: "tool-a-v1",
      serialized_schema_size: 512,
    },
  ],
  created_by: "admin-a",
  created_at: "2026-09-07T00:00:00Z",
  updated_at: "2026-09-07T00:00:00Z",
};

test("renders toolset list with endpoint and health diagnostics", async () => {
  server.use(
    http.get("/admin/toolsets", () =>
      HttpResponse.json({ items: [toolset], page: { offset: 0, limit: 10, total: 1 } }),
    ),
  );
  const queryClient = createAppQueryClient();
  const router = createMemoryRouter([{ path: "/toolsets", Component: ToolsetsPage }], {
    initialEntries: ["/toolsets"],
  });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );

  expect(await screen.findByRole("heading", { name: "工具集" })).toBeInTheDocument();
  expect(await screen.findByText("Operations")).toBeInTheDocument();
  expect(screen.getByText("健康")).toBeInTheDocument();
  expect(screen.getByText("1/1 · 1")).toBeInTheDocument();
  queryClient.clear();
});

test("renders aggregate editors and published member selection", async () => {
  server.use(
    http.get("/admin/toolsets/:id", () => HttpResponse.json(toolset)),
    http.get("/admin/tools", () =>
      HttpResponse.json({
        items: [
          {
            id: "tool-a",
            namespace: "operations",
            canonical_name: "operations.get_incident",
            owner: "platform-team",
            status: "active",
            latest_version_id: "tool-a-v1",
            latest_version: 1,
            display_name: "Get incident",
            description: "Get an incident",
            version_status: "published",
            visibility: "public",
            side_effect: "read_only",
            tags: ["operations"],
            created_at: "2026-09-07T00:00:00Z",
            updated_at: "2026-09-07T00:00:00Z",
          },
        ],
        page: { offset: 0, limit: 100, total: 1 },
      } satisfies ToolPageResponse),
    ),
  );
  const queryClient = createAppQueryClient();
  const router = createMemoryRouter(
    [{ path: "/toolsets/:toolsetId", Component: ToolsetDetailPage }],
    { initialEntries: ["/toolsets/toolset-1"] },
  );
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );

  expect(await screen.findByRole("heading", { name: "Operations" })).toBeInTheDocument();
  expect(screen.getByDisplayValue("operations-agent")).toBeInTheDocument();
  expect(screen.getByText("512 B")).toBeInTheDocument();
  expect(await screen.findByRole("checkbox", { name: /operations.get_incident/ })).toBeChecked();
  queryClient.clear();
});
