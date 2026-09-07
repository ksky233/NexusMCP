import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
  const publishedTools: ToolPageResponse["items"] = [
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
      upstream_service_id: "upstream-operations",
      upstream_name: "operations-api",
      upstream_namespace: "operations",
      created_at: "2026-09-07T00:00:00Z",
      updated_at: "2026-09-07T00:00:00Z",
    },
    {
      id: "tool-b",
      namespace: "customers",
      canonical_name: "customers.get_customer",
      owner: "customer-team",
      status: "active",
      latest_version_id: "tool-b-v1",
      latest_version: 1,
      display_name: "Get customer",
      description: "Get one customer",
      version_status: "published",
      visibility: "internal",
      side_effect: "read_only",
      tags: ["customers"],
      upstream_service_id: "upstream-customers",
      upstream_name: "customer-api",
      upstream_namespace: "crm",
      created_at: "2026-09-07T00:00:00Z",
      updated_at: "2026-09-07T00:00:00Z",
    },
  ];
  server.use(
    http.get("/admin/toolsets/:id", () => HttpResponse.json(toolset)),
    http.get("/admin/upstreams", () =>
      HttpResponse.json({
        items: [
          {
            id: "upstream-operations",
            tenant_id: "tenant-a",
            namespace: "operations",
            name: "operations-api",
            description: null,
            owner: "platform-team",
            service_type: "http",
            transport_type: "http",
            endpoint: "https://operations.example.test",
            auth_scheme: null,
            config: {},
            status: "active",
          },
          {
            id: "upstream-customers",
            tenant_id: "tenant-a",
            namespace: "crm",
            name: "customer-api",
            description: null,
            owner: "customer-team",
            service_type: "http",
            transport_type: "http",
            endpoint: "https://customers.example.test",
            auth_scheme: null,
            config: {},
            status: "active",
          },
        ],
        page: { offset: 0, limit: 100, total: 2 },
      }),
    ),
    http.get("/admin/tools", ({ request }) => {
      const q = new URL(request.url).searchParams.get("q")?.toLowerCase();
      const items = q
        ? publishedTools.filter((tool) =>
            `${tool.canonical_name} ${tool.display_name} ${tool.description}`
              .toLowerCase()
              .includes(q),
          )
        : publishedTools;
      return HttpResponse.json({
        items,
        page: { offset: 0, limit: 100, total: items.length },
      } satisfies ToolPageResponse);
    }),
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
  expect(screen.getByText("operations.operations-api", { selector: "p" })).toBeInTheDocument();
  expect(screen.getByText("crm.customer-api", { selector: "p" })).toBeInTheDocument();

  const user = userEvent.setup();
  await user.type(screen.getByRole("searchbox", { name: "搜索 Tool" }), "customer");
  expect(await screen.findByText("customers.get_customer")).toBeInTheDocument();
  await waitFor(() =>
    expect(
      screen.queryByText("operations.operations-api", { selector: "p" }),
    ).not.toBeInTheDocument(),
  );
  queryClient.clear();
});
