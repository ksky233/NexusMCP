import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";

import { createAppQueryClient } from "@/app/query-client";
import { DashboardPage } from "@/features/dashboard/pages/dashboard-page";
import { dashboardFixture } from "@/test/mocks/handlers";
import { server } from "@/test/mocks/server";

function renderDashboard() {
  const queryClient = createAppQueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <DashboardPage />
    </QueryClientProvider>,
  );
  return queryClient;
}

test("renders the generated-contract dashboard and request id", async () => {
  const queryClient = renderDashboard();

  expect(await screen.findByRole("heading", { name: "系统概览" })).toBeInTheDocument();
  expect(screen.getAllByText("8")).toHaveLength(2);
  expect(screen.getByText("已索引 87.50%")).toBeInTheDocument();
  expect(screen.getByText("request-dashboard-test")).toBeInTheDocument();
  queryClient.clear();
});

test("renders Problem Details without exposing an unsafe response", async () => {
  server.use(
    http.get("/admin/dashboard", () =>
      HttpResponse.json(
        {
          type: "urn:nexusmcp:error:embedding_unavailable",
          title: "Request rejected",
          status: 503,
          detail: "The embedding provider is unavailable.",
          code: "embedding_unavailable",
          request_id: "request-problem-test",
        },
        {
          status: 503,
          headers: { "Content-Type": "application/problem+json" },
        },
      ),
    ),
  );
  const queryClient = renderDashboard();

  expect(await screen.findByText("当前页面加载失败")).toBeInTheDocument();
  expect(screen.getByText("The embedding provider is unavailable.")).toBeInTheDocument();
  expect(screen.getByText("Request ID：request-problem-test")).toBeInTheDocument();
  queryClient.clear();
});

test("renders an empty state when the governed catalog is new", async () => {
  server.use(
    http.get("/admin/dashboard", () =>
      HttpResponse.json({
        ...dashboardFixture,
        active_upstreams: 0,
        published_tools: 0,
        pending_reviews: 0,
        pending_approvals: 0,
        failed_executions: 0,
        unknown_executions: 0,
        search_projection: {
          ...dashboardFixture.search_projection,
          published_tools: 0,
          indexed_tools: 0,
          pending_tools: 0,
          coverage_percent: 100,
          latest_indexed_at: null,
        },
      }),
    ),
  );
  const queryClient = renderDashboard();

  expect(await screen.findByText("暂无治理资源")).toBeInTheDocument();
  queryClient.clear();
});

test("rejects a successful response that drifts from the generated schema", async () => {
  server.use(
    http.get("/admin/dashboard", () =>
      HttpResponse.json({
        ...dashboardFixture,
        active_upstreams: "three",
      }),
    ),
  );
  const queryClient = renderDashboard();

  expect(await screen.findByText("invalid_response_schema")).toBeInTheDocument();
  expect(screen.getByText("服务端响应不符合 Admin API Contract。")).toBeInTheDocument();
  queryClient.clear();
});

test("classifies an unreachable Admin API as a network error", async () => {
  server.use(http.get("/admin/dashboard", () => HttpResponse.error()));
  const queryClient = renderDashboard();

  expect(await screen.findByText("network_error", {}, { timeout: 3_000 })).toBeInTheDocument();
  expect(screen.getByText("无法连接 Admin API。")).toBeInTheDocument();
  queryClient.clear();
});
