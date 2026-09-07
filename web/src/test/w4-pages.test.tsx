import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";

import { createAppQueryClient } from "@/app/query-client";
import { EvidencePage } from "@/features/evidence/pages/evidence-page";
import { SearchIndexPanel } from "@/features/catalog/parts/search-index-panel";
import { SearchLabPage } from "@/features/search-lab/pages/search-lab-page";
import type { SearchLabResponse } from "@/generated/api/types.gen";
import { server } from "@/test/mocks/server";

function renderWithQuery(element: React.ReactElement) {
  const queryClient = createAppQueryClient();
  render(<QueryClientProvider client={queryClient}>{element}</QueryClientProvider>);
  return queryClient;
}

test("compares live lexical and hybrid governed candidates", async () => {
  server.use(
    http.get("/admin/search/tools", ({ request }) => {
      const mode = new URL(request.url).searchParams.get("retrieval_mode") as "lexical" | "hybrid";
      return HttpResponse.json(searchResponse(mode));
    }),
  );
  const user = userEvent.setup();
  const queryClient = renderWithQuery(<SearchLabPage />);

  await user.type(screen.getByLabelText("自然语言查询"), "find a coworker");
  await user.click(screen.getByRole("button", { name: "对比检索" }));

  expect(await screen.findByText("Lexical FTS")).toBeInTheDocument();
  expect(screen.getByText("Hybrid RRF")).toBeInTheDocument();
  expect(await screen.findAllByText("directory.get_employee")).toHaveLength(2);
  expect(screen.getByText("RRF 分数")).toBeInTheDocument();
  expect(screen.getByText("Vector 排名")).toBeInTheDocument();
  expect(screen.getByText("Vector Cosine")).toBeInTheDocument();
  expect(screen.getByText("0.820000")).toBeInTheDocument();
  expect(screen.getByText("Qwen/Qwen3-Embedding-8B@2048")).toBeInTheDocument();
  queryClient.clear();
});

test("renders tracked engineering snapshots with explicit limitations", () => {
  render(<EvidencePage />);

  expect(screen.getByRole("heading", { name: "证据中心" })).toBeInTheDocument();
  expect(screen.getByText("Gateway 基准测试")).toBeInTheDocument();
  expect(screen.getByText("这些证据不代表什么")).toBeInTheDocument();
  expect(screen.getByText("Toolset 发布面")).toBeInTheDocument();
  expect(screen.getByText("24")).toBeInTheDocument();
});

test("starts a missing-only search index job and refreshes persisted status", async () => {
  let indexed = false;
  server.use(
    http.get("/admin/tool-search/index-status", () =>
      HttpResponse.json({
        published_count: 1,
        current_count: indexed ? 1 : 0,
        missing_count: indexed ? 0 : 1,
        stale_count: 0,
        embedding_model: "Qwen/Qwen3-Embedding-8B",
        embedding_dimensions: 2048,
        embedding_available: true,
        items: [
          {
            tool_id: "00000000-0000-0000-0000-000000000101",
            tool_version_id: "00000000-0000-0000-0000-000000000201",
            canonical_name: "directory.get_employee",
            state: indexed ? "current" : "missing",
            indexed_at: indexed ? "2026-08-29T03:00:00Z" : null,
          },
        ],
        page: { offset: 0, limit: 100, total: 1 },
      }),
    ),
    http.get("/admin/tool-search/reindex-jobs", () =>
      HttpResponse.json({ items: [], page: { offset: 0, limit: 5, total: 0 } }),
    ),
    http.post("/admin/tool-search/reindex-jobs", async ({ request }) => {
      expect(await request.json()).toEqual({ force: false, batch_size: 16 });
      indexed = true;
      return HttpResponse.json(
        {
          id: "00000000-0000-0000-0000-000000000901",
          tenant_id: "00000000-0000-0000-0000-000000000001",
          requested_by: "local-admin",
          status: "succeeded",
          force: false,
          batch_size: 16,
          embedding_model: "Qwen/Qwen3-Embedding-8B",
          embedding_dimensions: 2048,
          published_count: 1,
          current_count: 0,
          pending_count: 1,
          embedded_count: 1,
          batch_count: 1,
          error_code: null,
          created_at: "2026-08-29T03:00:00Z",
          started_at: "2026-08-29T03:00:00Z",
          finished_at: "2026-08-29T03:00:01Z",
        },
        { status: 202 },
      );
    }),
  );
  const user = userEvent.setup();
  const queryClient = renderWithQuery(<SearchIndexPanel />);

  await user.click(await screen.findByRole("button", { name: "更新检索索引 (1)" }));
  await user.click(screen.getByRole("button", { name: "开始更新" }));

  await waitFor(() => {
    expect(screen.getByRole("button", { name: "更新检索索引" })).toBeDisabled();
  });
  queryClient.clear();
});

function searchResponse(mode: "lexical" | "hybrid"): SearchLabResponse {
  return {
    retrieval_mode: mode,
    index_version: mode === "hybrid" ? "Qwen/Qwen3-Embedding-8B@2048" : null,
    hits: [
      {
        position: 1,
        tool_id: "00000000-0000-0000-0000-000000000101",
        tool_version_id: `00000000-0000-0000-0000-00000000020${mode === "hybrid" ? "2" : "1"}`,
        canonical_name: "directory.get_employee",
        display_name: "Get employee",
        description: "Get one employee and contact information.",
        version: 1,
        visibility: "public",
        side_effect: "read_only",
        owner: "people-platform",
        tags: ["directory"],
        rank: mode === "hybrid" ? 0.032786 : 0.75,
        score_kind: mode === "hybrid" ? "rrf" : "fts",
        lexical_rank: mode === "hybrid" ? null : 1,
        lexical_score: mode === "hybrid" ? null : 0.75,
        vector_rank: mode === "hybrid" ? 1 : null,
        vector_cosine_similarity: mode === "hybrid" ? 0.82 : null,
        rrf_score: mode === "hybrid" ? 0.032786 : null,
        input_schema: { type: "object", properties: { employee_id: { type: "string" } } },
        output_schema: null,
      },
    ],
  };
}
