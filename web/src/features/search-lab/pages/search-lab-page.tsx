import { Search } from "lucide-react";
import { useState } from "react";

import retrievalSnapshot from "../../../../../evals/tool_search/results/2026-08-27_siliconflow_qwen3_embedding_8b.json";
import { PageHeader } from "@/components/common/page-header";
import { InlineError, LoadingState } from "@/components/common/query-state";
import { Button } from "@/components/ui/button";
import { FieldLabel, Input, Select } from "@/components/ui/form-controls";
import { StatusPill } from "@/components/ui/status-pill";
import {
  useSearchComparison,
  type SearchComparisonInput,
} from "@/features/search-lab/hooks/use-search-comparison";
import type { SearchLabHitResponse, ToolSideEffect } from "@/generated/api/types.gen";
import { humanize } from "@/lib/display";

export function SearchLabPage() {
  const [text, setText] = useState("");
  const [namespace, setNamespace] = useState("");
  const [sideEffect, setSideEffect] = useState<ToolSideEffect | "">("");
  const [limit, setLimit] = useState(5);
  const [input, setInput] = useState<SearchComparisonInput | null>(null);
  const comparison = useSearchComparison(input);

  return (
    <section className="page-enter">
      <PageHeader
        description="对比受治理的 PostgreSQL FTS 与 Hybrid RRF 候选结果。候选检索不等于 Agent 的最终 Tool 选择。"
        eyebrow="检索评估"
        title="检索实验室"
      />
      <form
        className="panel p-6 sm:p-7"
        onSubmit={(event) => {
          event.preventDefault();
          if (!text.trim()) return;
          setInput({
            text: text.trim(),
            namespace: namespace.trim() || undefined,
            sideEffect: sideEffect || undefined,
            limit,
          });
        }}
      >
        <div className="grid gap-5 lg:grid-cols-[2fr_1fr_1fr_120px]">
          <div>
            <FieldLabel htmlFor="search-query">自然语言查询</FieldLabel>
            <Input
              id="search-query"
              maxLength={500}
              onChange={(event) => setText(event.currentTarget.value)}
              placeholder="查找一位同事及其联系方式"
              required
              value={text}
            />
          </div>
          <div>
            <FieldLabel htmlFor="search-namespace">Namespace</FieldLabel>
            <Input
              id="search-namespace"
              onChange={(event) => setNamespace(event.currentTarget.value)}
              placeholder="全部 Namespace"
              value={namespace}
            />
          </div>
          <div>
            <FieldLabel htmlFor="search-side-effect">副作用</FieldLabel>
            <Select
              id="search-side-effect"
              onChange={(event) => setSideEffect(event.currentTarget.value as ToolSideEffect | "")}
              value={sideEffect}
            >
              <option value="">全部</option>
              <option value="read_only">只读</option>
              <option value="idempotent_write">幂等写</option>
              <option value="non_idempotent_write">非幂等写</option>
              <option value="unknown">未知</option>
            </Select>
          </div>
          <div>
            <FieldLabel htmlFor="search-limit">Top K</FieldLabel>
            <Select
              id="search-limit"
              onChange={(event) => setLimit(Number(event.currentTarget.value))}
              value={limit}
            >
              {[3, 5, 10].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </Select>
          </div>
        </div>
        <div className="mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-slate/20 pt-5">
          <p className="max-w-2xl text-xs leading-5 text-slate/55">
            Hybrid 会调用当前配置的 Embedding Provider。结果在展示前仍会经过租户、可见性与 Policy
            过滤。
          </p>
          <Button
            disabled={!text.trim() || comparison.lexical.isFetching || comparison.hybrid.isFetching}
            type="submit"
          >
            <Search aria-hidden="true" className="size-4" /> 对比检索
          </Button>
        </div>
      </form>

      {input ? (
        <div className="mt-6 grid gap-5 xl:grid-cols-2">
          <SearchResultColumn mode="Lexical FTS" query={comparison.lexical} />
          <SearchResultColumn mode="Hybrid RRF" query={comparison.hybrid} />
        </div>
      ) : (
        <div className="mt-6 border border-dashed border-slate/25 bg-paper p-8 text-center text-sm text-slate/60">
          提交查询后，可并排比较两种检索策略。
        </div>
      )}

      <RetrievalSnapshot />
    </section>
  );
}

function SearchResultColumn({
  mode,
  query,
}: {
  mode: string;
  query: ReturnType<typeof useSearchComparison>["lexical"];
}) {
  return (
    <article className="panel min-h-72 p-6 sm:p-7">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="component-label">实时结果</p>
          <h2 className="mt-3 text-xl font-light text-ink">{mode}</h2>
        </div>
        {query.data ? (
          <StatusPill tone={query.data.retrieval_mode === "hybrid" ? "active" : "review"}>
            {query.data.hits.length} 个候选
          </StatusPill>
        ) : null}
      </div>
      {query.isPending || query.isFetching ? (
        <div className="mt-5">
          <LoadingState label={`正在执行 ${mode} 检索…`} />
        </div>
      ) : null}
      {query.error ? (
        <div className="mt-5">
          <InlineError error={query.error} />
        </div>
      ) : null}
      {query.data?.hits.length === 0 ? (
        <p className="mt-7 text-sm text-slate/60">未返回符合治理约束的候选 Tool。</p>
      ) : null}
      {query.data?.hits.map((hit) => (
        <CandidateCard hit={hit} key={hit.tool_version_id} />
      ))}
      {query.data?.index_version ? (
        <p className="mt-5 break-all border-t border-slate/12 pt-4 font-mono text-[11px] text-slate/50">
          {query.data.index_version}
        </p>
      ) : null}
    </article>
  );
}

function CandidateCard({ hit }: { hit: SearchLabHitResponse }) {
  const [schemaOpen, setSchemaOpen] = useState(false);
  return (
    <div className="mt-5 border-t border-slate/20 pt-5">
      <div className="flex items-start gap-4">
        <span className="grid size-7 shrink-0 place-items-center border border-slate/25 font-mono text-xs text-slate">
          {hit.position}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="break-all text-sm font-normal text-ink">{hit.canonical_name}</h3>
              <p className="mt-1 text-xs text-slate/55">{hit.display_name}</p>
            </div>
            <span className="font-mono text-[11px] text-slate/50">
              {hit.score_kind === "rrf" ? "RRF" : "FTS"} {hit.rank.toFixed(6)}
            </span>
          </div>
          <p className="mt-3 text-sm leading-6 text-slate/65">{hit.description}</p>
          <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate/55">
            <span>{humanize(hit.visibility)}</span>
            <span>·</span>
            <span>{humanize(hit.side_effect)}</span>
          </div>
          {hit.score_kind === "rrf" ? (
            <dl className="mt-4 grid grid-cols-2 gap-x-5 gap-y-3 border border-slate/25 bg-canvas p-4 text-xs sm:grid-cols-4">
              <Diagnostic label="RRF 分数" value={formatScore(hit.rrf_score)} />
              <Diagnostic label="Vector 排名" value={formatRank(hit.vector_rank)} />
              <Diagnostic label="Vector Cosine" value={formatScore(hit.vector_cosine_similarity)} />
              <Diagnostic label="Lexical 排名" value={formatRank(hit.lexical_rank)} />
            </dl>
          ) : (
            <dl className="mt-4 grid grid-cols-2 gap-5 border border-slate/25 bg-canvas p-4 text-xs">
              <Diagnostic label="Lexical 排名" value={formatRank(hit.lexical_rank)} />
              <Diagnostic label="FTS 分数" value={formatScore(hit.lexical_score)} />
            </dl>
          )}
          <button
            className="mt-3 text-xs text-slate underline underline-offset-4 hover:text-ink"
            onClick={() => setSchemaOpen((value) => !value)}
            type="button"
          >
            {schemaOpen ? "收起 Input Schema" : "查看 Input Schema"}
          </button>
          {schemaOpen ? (
            <pre className="mt-3 max-h-72 overflow-auto border border-slate/25 bg-canvas p-4 font-mono text-[11px] leading-5 text-slate">
              {JSON.stringify(hit.input_schema, null, 2)}
            </pre>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Diagnostic({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="component-label">{label}</dt>
      <dd className="mt-2 font-mono text-[11px] text-ink">{value}</dd>
    </div>
  );
}

function formatRank(value: number | null): string {
  return value === null ? "未命中" : `#${value}`;
}

function formatScore(value: number | null): string {
  return value === null ? "—" : value.toFixed(6);
}

function RetrievalSnapshot() {
  const metrics = retrievalSnapshot.metrics;
  return (
    <section className="mt-10">
      <div className="hairline-divider mb-10" />
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="eyebrow">已保存的工程证据 · 2026-08-27</p>
          <h2 className="page-title">硅基流动检索快照</h2>
          <p className="page-description">
            24 条人工标注查询、8 个 Demo Tool、精确余弦向量检索，RRF k=60。
          </p>
        </div>
        <StatusPill tone="neutral">非在线 SLO</StatusPill>
      </div>
      <div className="mt-7 grid gap-4 md:grid-cols-3">
        {(["lexical", "vector", "hybrid"] as const).map((strategy) => (
          <article className="panel p-6" key={strategy}>
            <p className="component-label">{strategy}</p>
            <p className="mt-5 text-3xl font-light text-ink">
              {(metrics[strategy].top_1_accuracy * 100).toFixed(2)}%
            </p>
            <p className="mt-1 text-xs text-slate/55">Top-1 准确率</p>
            <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-slate/12 pt-5 text-sm">
              <div>
                <dt className="text-[10px] uppercase tracking-wider text-slate/45">Hit@3</dt>
                <dd className="mt-1">{(metrics[strategy].hit_at_3 * 100).toFixed(2)}%</dd>
              </div>
              <div>
                <dt className="text-[10px] uppercase tracking-wider text-slate/45">p95</dt>
                <dd className="mt-1">{metrics[strategy].latency_p95_ms.toFixed(2)} ms</dd>
              </div>
            </dl>
          </article>
        ))}
      </div>
      <p className="mt-5 border border-wine/25 bg-wine/5 p-4 text-xs leading-6 text-wine">
        已知缺口：由于尚未实现置信度阈值，Vector/Hybrid 的 No-Match 准确率为 0%。返回最近候选
        并不能证明正确的 Tool 一定存在。
      </p>
    </section>
  );
}
