import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { expect, test } from "vitest";

import { createAppQueryClient } from "@/app/query-client";
import { ApprovalsPage } from "@/features/approvals/pages/approvals-page";
import { ToolDetailPage } from "@/features/catalog/pages/tool-detail-page";
import { ExecutionsPage } from "@/features/executions/pages/executions-page";
import { ImportDetailPage } from "@/features/imports/pages/import-detail-page";
import { UpstreamsPage } from "@/features/upstreams/pages/upstreams-page";
import type {
  ApprovalPageResponse,
  ApprovalResponse,
  ExecutionPageResponse,
  ImportDetailResponse,
  ToolBindingDetailResponse,
  ToolDetailResponse,
  ToolVersionPageResponse,
  UpstreamPageResponse,
} from "@/generated/api/types.gen";
import { server } from "@/test/mocks/server";

const now = "2026-08-28T09:00:00Z";
const upstreamId = "00000000-0000-0000-0000-000000000401";
const toolId = "00000000-0000-0000-0000-000000000101";
const versionId = "00000000-0000-0000-0000-000000000201";
const bindingId = "00000000-0000-0000-0000-000000000301";

function renderRoute(element: ReactElement, route: string, path = route) {
  const queryClient = createAppQueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route element={element} path={path} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return queryClient;
}

test("renders the governed upstream registry", async () => {
  const response = {
    items: [
      {
        id: upstreamId,
        tenant_id: "00000000-0000-0000-0000-000000000001",
        namespace: "directory",
        name: "employee-api",
        description: "Employee directory",
        owner: "people-platform",
        service_type: "http",
        transport_type: "http",
        endpoint: "http://127.0.0.1:9001",
        auth_scheme: "none",
        config: {},
        status: "active",
      },
    ],
    page: { offset: 0, limit: 10, total: 1 },
  } satisfies UpstreamPageResponse;
  server.use(http.get("/admin/upstreams", () => HttpResponse.json(response)));
  const queryClient = renderRoute(<UpstreamsPage />, "/upstreams");

  expect(await screen.findByText("directory.employee-api")).toBeInTheDocument();
  expect(screen.getByText("people-platform")).toBeInTheDocument();
  queryClient.clear();
});

test("recovers the reviewed import workflow after a page reload", async () => {
  const detail = {
    job: {
      id: "00000000-0000-0000-0000-000000000501",
      upstream_service_id: upstreamId,
      source_ref: "employee_directory/openapi.json",
      source_digest: "3".repeat(64),
      openapi_version: "3.1.0",
      status: "completed",
      error_summary: null,
      created_at: now,
      started_at: now,
      completed_at: now,
    },
    operations: [
      {
        id: "00000000-0000-0000-0000-000000000601",
        operation_key: "GET /employees/{employee_id}",
        operation_id: "getEmployee",
        method: "GET",
        path: "/employees/{employee_id}",
        generated_tool_name: "directory.get_employee",
        conflict_status: "none",
        review_status: "accepted",
        draft_tool_version_id: versionId,
        draft_tool_binding_id: bindingId,
      },
    ],
  } satisfies ImportDetailResponse;
  server.use(
    http.get("/admin/openapi/imports/:id", () => HttpResponse.json(detail)),
    http.get("/admin/tool-versions/:id", () => HttpResponse.json(toolVersion("review"))),
    http.get("/admin/tool-bindings/:id", () => HttpResponse.json(toolBinding())),
  );
  const queryClient = renderRoute(<ImportDetailPage />, "/imports/import-1", "/imports/:importId");

  expect(await screen.findByRole("button", { name: "Publish version" })).toBeInTheDocument();
  expect(screen.getByText("getEmployee")).toBeInTheDocument();
  queryClient.clear();
});

test("renders catalog version schemas and its unique binding", async () => {
  const tool = {
    id: toolId,
    tenant_id: "00000000-0000-0000-0000-000000000001",
    namespace: "directory",
    canonical_name: "directory.get_employee",
    owner: "people-platform",
    status: "active",
    created_at: now,
    updated_at: now,
  } satisfies ToolDetailResponse;
  const versions = {
    items: [toolVersion("published")],
    page: { offset: 0, limit: 100, total: 1 },
  } satisfies ToolVersionPageResponse;
  server.use(
    http.get("/admin/tools/:id", () => HttpResponse.json(tool)),
    http.get("/admin/tools/:id/versions", () => HttpResponse.json(versions)),
    http.get("/admin/tool-versions/:id/binding", () => HttpResponse.json(toolBinding())),
  );
  const queryClient = renderRoute(<ToolDetailPage />, "/catalog/tool-1", "/catalog/:toolId");

  expect(await screen.findByText("directory.get_employee")).toBeInTheDocument();
  expect(await screen.findByText("HTTP binding")).toBeInTheDocument();
  expect(screen.getByText("Get employee")).toBeInTheDocument();
  queryClient.clear();
});

test("requires confirmation before persisting an approval decision", async () => {
  let approved = false;
  const listResponse = (): ApprovalPageResponse => ({
    items: [
      {
        id: "00000000-0000-0000-0000-000000000701",
        principal_id: "employee-agent",
        tool_id: toolId,
        tool_version_id: versionId,
        canonical_name: "directory.get_employee",
        arguments_digest: "4".repeat(64),
        policy_version: "policy-v1",
        has_idempotency_key: false,
        status: approved ? "approved" : "pending",
        requested_at: now,
        expires_at: "2026-08-28T10:00:00Z",
        decided_by: approved ? "local-admin" : null,
        decided_at: approved ? now : null,
        consumed_at: null,
      },
    ],
    page: { offset: 0, limit: 10, total: 1 },
  });
  server.use(
    http.get("/admin/approvals", () => HttpResponse.json(listResponse())),
    http.post("/admin/approvals/:id/approve", () => {
      approved = true;
      return HttpResponse.json(approvalDecision());
    }),
  );
  const user = userEvent.setup();
  const queryClient = renderRoute(<ApprovalsPage />, "/approvals");

  await user.click(await screen.findByRole("button", { name: "Approve directory.get_employee" }));
  expect(
    screen.getByRole("dialog", { name: "Approve directory.get_employee?" }),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Approve request" }));
  await waitFor(() => {
    expect(
      screen.queryByRole("button", { name: "Approve directory.get_employee" }),
    ).not.toBeInTheDocument();
  });
  queryClient.clear();
});

test("renders execution evidence without payload fields", async () => {
  const response = {
    items: [executionSummary()],
    page: { offset: 0, limit: 10, total: 1 },
  } satisfies ExecutionPageResponse;
  server.use(
    http.get("/admin/executions", () => HttpResponse.json(response)),
    http.get("/admin/audit-events", () =>
      HttpResponse.json({ items: [], page: { offset: 0, limit: 10, total: 0 } }),
    ),
  );
  const queryClient = renderRoute(<ExecutionsPage />, "/executions");

  expect(await screen.findByText("directory.get_employee")).toBeInTheDocument();
  expect(screen.queryByText(/arguments/i)).not.toBeInTheDocument();
  expect(screen.getAllByText("Succeeded")).toHaveLength(2);
  queryClient.clear();
});

function toolVersion(status: string): ToolVersionPageResponse["items"][number] {
  return {
    id: versionId,
    tool_id: toolId,
    version: 1,
    display_name: "Get employee",
    description: "Get one employee by id.",
    input_schema: { type: "object", properties: {} },
    output_schema: null,
    schema_digest: "1".repeat(64),
    tags: ["directory"],
    side_effect: "read_only",
    visibility: "public",
    status,
    created_by: "reviewer",
    created_at: now,
    reviewed_at: now,
    published_at: status === "published" ? now : null,
    retired_at: null,
  };
}

function toolBinding(): ToolBindingDetailResponse {
  return {
    id: bindingId,
    tool_version_id: versionId,
    upstream_service_id: upstreamId,
    imported_operation_id: null,
    binding_type: "http",
    binding_config: { method: "GET", path_template: "/employees/{employee_id}" },
    binding_digest: "2".repeat(64),
    status: "published",
    created_at: now,
    updated_at: now,
    published_at: now,
  };
}

function approvalDecision(): ApprovalResponse {
  return {
    id: "00000000-0000-0000-0000-000000000701",
    tenant_id: "00000000-0000-0000-0000-000000000001",
    principal_id: "employee-agent",
    tool_id: toolId,
    tool_version_id: versionId,
    arguments_digest: "4".repeat(64),
    policy_version: "policy-v1",
    idempotency_key: null,
    status: "approved",
    requested_at: now,
    expires_at: "2026-08-28T10:00:00Z",
    decided_by: "local-admin",
    decided_at: now,
    consumed_at: null,
  };
}

function executionSummary(): ExecutionPageResponse["items"][number] {
  return {
    id: "00000000-0000-0000-0000-000000000901",
    request_id: "request-w3",
    trace_id: "a".repeat(32),
    principal_id: "employee-agent",
    tool_id: toolId,
    tool_version_id: versionId,
    tool_binding_id: bindingId,
    canonical_name: "directory.get_employee",
    policy_version: "policy-v1",
    policy_reason_code: "read_only_allowed",
    side_effect: "read_only",
    status: "succeeded",
    has_idempotency_key: false,
    planned_at: now,
    started_at: now,
    finished_at: now,
    error_code: null,
    error_category: null,
    attempt_count: 1,
  };
}
