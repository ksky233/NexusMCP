import benchmarkSnapshot from "../../../../../benchmarks/results/2026-08-27_local_postgresql18.json";
import failureCases from "../../../../../evals/reliability/failure_injection_cases.json";
import protocolMatrix from "../../../../../evals/protocol/compatibility_matrix.json";
import securityCases from "../../../../../evals/security/security_cases.json";
import toolsetCases from "../../../../../evals/toolsets/toolset_cases.json";
import retrievalSnapshot from "../../../../../evals/tool_search/results/2026-08-27_siliconflow_qwen3_embedding_8b.json";
import { PageHeader } from "@/components/common/page-header";
import {
  Table,
  TableBody,
  TableCell,
  TableFrame,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/data-table";
import { StatusPill } from "@/components/ui/status-pill";
import { humanize } from "@/lib/display";

export function EvidencePage() {
  return (
    <section className="page-enter">
      <PageHeader
        description="集中展示可追踪、可复现的检索、性能、安全、协议与故障行为快照。"
        eyebrow="工程证据"
        title="证据中心"
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <EvidenceMetric
          label="检索查询"
          value={retrievalSnapshot.dataset.case_count}
          note="人工标注"
        />
        <EvidenceMetric label="安全用例" value={securityCases.cases.length} note="Golden 回归" />
        <EvidenceMetric
          label="协议用例"
          value={protocolMatrix.cases.length}
          note="Modern + Legacy"
        />
        <EvidenceMetric label="故障用例" value={failureCases.cases.length} note="边界故障注入" />
        <EvidenceMetric label="Toolset 用例" value={toolsetCases.cases.length} note="发布面边界" />
      </div>

      <section className="mt-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="component-label">本地 PostgreSQL 18 快照</p>
            <h2 className="mt-3 text-xl font-normal text-ink">Gateway 基准测试</h2>
          </div>
          <StatusPill tone="neutral">并发 1 · 非生产 SLO</StatusPill>
        </div>
        <TableFrame className="mt-5">
          <Table>
            <TableHead>
              <tr>
                <TableHeaderCell>场景</TableHeaderCell>
                <TableHeaderCell>p50</TableHeaderCell>
                <TableHeaderCell>p95</TableHeaderCell>
                <TableHeaderCell>吞吐量</TableHeaderCell>
                <TableHeaderCell>错误率</TableHeaderCell>
              </tr>
            </TableHead>
            <TableBody>
              {benchmarkSnapshot.scenarios.map((scenario) => (
                <TableRow key={scenario.scenario}>
                  <TableCell className="text-ink">{humanize(scenario.scenario)}</TableCell>
                  <TableCell>{scenario.latency_p50_ms.toFixed(2)} ms</TableCell>
                  <TableCell>{scenario.latency_p95_ms.toFixed(2)} ms</TableCell>
                  <TableCell>{scenario.throughput_ops_per_second.toFixed(2)} ops/s</TableCell>
                  <TableCell>{(scenario.error_rate * 100).toFixed(2)}%</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableFrame>
        <p className="mt-4 text-xs leading-6 text-slate/55">
          可复现的本地基线，不代表生产容量。环境：{benchmarkSnapshot.environment.postgresql}
          ；每个场景 执行 {benchmarkSnapshot.environment.iterations_per_scenario} 次。
        </p>
      </section>

      <div className="mt-10 grid gap-5 xl:grid-cols-2">
        <EvidenceList
          title="安全回归"
          label="安全"
          items={securityCases.cases
            .slice(0, 8)
            .map((item) => ({ id: item.id, category: item.category, expected: item.expected }))}
        />
        <EvidenceList
          title="Toolset 发布面"
          label="Scope · Search · Audit"
          items={toolsetCases.cases
            .slice(0, 8)
            .map((item) => ({ id: item.id, category: item.category, expected: item.expected }))}
        />
        <EvidenceList
          title="协议兼容性"
          label={`${protocolMatrix.modern_version} + ${protocolMatrix.legacy_version}`}
          items={protocolMatrix.cases
            .slice(0, 8)
            .map((item) => ({ id: item.id, category: item.era, expected: item.expected }))}
        />
        <EvidenceList
          title="故障注入"
          label="可靠性"
          items={failureCases.cases
            .slice(0, 8)
            .map((item) => ({ id: item.id, category: item.component, expected: item.expected }))}
        />
        <article className="panel p-6 sm:p-7">
          <p className="component-label">剩余风险</p>
          <h2 className="mt-3 text-xl font-normal text-ink">这些证据不代表什么</h2>
          <ul className="mt-5 space-y-3 text-sm leading-6 text-slate/68">
            <li>• 尚无多区域或多 Worker 的生产容量证明。</li>
            <li>• 尚未接入生产级 OIDC、Vault/KMS 或浏览器端 Admin IAM。</li>
            <li>• 尚未实现 Hybrid No-Match 置信度阈值。</li>
            <li>• 基准测试使用本地 Docker/ASGI，且并发数为 1。</li>
            <li>• 付费硅基流动调用只保存为快照，不进入常规 CI。</li>
          </ul>
        </article>
      </div>

      <article className="panel mt-5 p-6 sm:p-7">
        <p className="component-label">检索结论</p>
        <ul className="mt-5 grid gap-3 text-sm leading-6 text-slate/68 lg:grid-cols-2">
          {retrievalSnapshot.findings.map((finding) => (
            <li className="border-l-2 border-slate/25 pl-4" key={finding}>
              {translateFinding(finding)}
            </li>
          ))}
        </ul>
      </article>
    </section>
  );
}

const findingTranslations: Record<string, string> = {
  "Vector and Hybrid recovered every positive case within Top-3.":
    "Vector 与 Hybrid 在 Top-3 内召回了全部正例。",
  "Hybrid matched Vector on this small dataset because lexical results either agreed or were empty.":
    "在当前小型数据集上，Hybrid 与 Vector 表现相同，因为词法检索结果要么一致、要么为空。",
  "The cross-language contact query ranked directory.search_employees before directory.get_employee.":
    "跨语言联系方式查询将 directory.search_employees 排在 directory.get_employee 之前。",
  "Exact Vector and Hybrid returned nearest tools for both No-Match cases because no confidence threshold exists.":
    "由于缺少置信度阈值，Exact Vector 与 Hybrid 在两个 No-Match 用例中仍返回了最近的 Tool。",
  "No forbidden filter candidate or cross-tenant candidate leaked in the regression evidence.":
    "回归证据中没有出现受禁止筛选候选或跨租户候选泄漏。",
};

function translateFinding(finding: string): string {
  return findingTranslations[finding] ?? finding;
}

function EvidenceMetric({ label, value, note }: { label: string; value: number; note: string }) {
  return (
    <article className="panel p-6">
      <p className="component-label">{label}</p>
      <p className="mt-6 text-3xl font-light text-ink">{value}</p>
      <p className="mt-2 text-xs text-slate/50">{note}</p>
    </article>
  );
}

function EvidenceList({
  title,
  label,
  items,
}: {
  title: string;
  label: string;
  items: Array<{ id: string; category: string; expected: string }>;
}) {
  return (
    <article className="panel p-6 sm:p-7">
      <p className="component-label">{label}</p>
      <h2 className="mt-3 text-xl font-light text-ink">{title}</h2>
      <div className="mt-5 divide-y divide-slate/12">
        {items.map((item) => (
          <div className="py-3 first:pt-0" key={item.id}>
            <div className="flex items-start justify-between gap-3">
              <p className="font-mono text-xs text-ink">{item.id}</p>
              <StatusPill tone="neutral">{humanize(item.category)}</StatusPill>
            </div>
            <p className="mt-2 text-xs leading-5 text-slate/60">{humanize(item.expected)}</p>
          </div>
        ))}
      </div>
    </article>
  );
}
