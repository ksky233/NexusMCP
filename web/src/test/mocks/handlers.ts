import type {
  DashboardResponse,
  ToolSearchIndexStatusResponse,
  ToolSearchReindexJobPageResponse,
} from "@/generated/api/types.gen";
import { http, HttpResponse } from "msw";

export const dashboardFixture: DashboardResponse = {
  active_upstreams: 3,
  published_tools: 8,
  pending_reviews: 2,
  pending_approvals: 1,
  failed_executions: 0,
  unknown_executions: 1,
  search_projection: {
    published_tools: 8,
    indexed_tools: 7,
    pending_tools: 1,
    coverage_percent: 87.5,
    embedding_model: "Qwen/Qwen3-Embedding-8B",
    embedding_dimensions: 2048,
    latest_indexed_at: "2026-08-28T09:00:00Z",
  },
};

export const handlers = [
  http.get("/admin/dashboard", () =>
    HttpResponse.json(dashboardFixture, {
      headers: { "X-Request-ID": "request-dashboard-test" },
    }),
  ),
  http.get("/admin/tool-search/index-status", () =>
    HttpResponse.json({
      published_count: 0,
      current_count: 0,
      missing_count: 0,
      stale_count: 0,
      embedding_model: "Qwen/Qwen3-Embedding-8B",
      embedding_dimensions: 2048,
      embedding_available: true,
      items: [],
      page: { offset: 0, limit: 100, total: 0 },
    } satisfies ToolSearchIndexStatusResponse),
  ),
  http.get("/admin/tool-search/reindex-jobs", () =>
    HttpResponse.json({
      items: [],
      page: { offset: 0, limit: 5, total: 0 },
    } satisfies ToolSearchReindexJobPageResponse),
  ),
];
