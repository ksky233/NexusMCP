import {
  getExecution,
  listAuditEvents,
  listExecutionAttempts,
  listExecutions,
} from "@/generated/api/sdk.gen";
import type {
  AuditEventPageResponse,
  ExecutionAttemptPageResponse,
  ExecutionPageResponse,
  ExecutionSummaryResponse,
  ListAuditEventsData,
  ListExecutionsData,
} from "@/generated/api/types.gen";
import { createRequestSignal } from "@/lib/api/client";

export type ExecutionListQuery = NonNullable<ListExecutionsData["query"]>;
export type AuditListQuery = NonNullable<ListAuditEventsData["query"]>;

export async function fetchExecutions(query: ExecutionListQuery): Promise<ExecutionPageResponse> {
  return (await listExecutions({ query, signal: createRequestSignal(), throwOnError: true })).data;
}

export async function fetchExecution(executionId: string): Promise<ExecutionSummaryResponse> {
  return (
    await getExecution({
      path: { execution_id: executionId },
      signal: createRequestSignal(),
      throwOnError: true,
    })
  ).data;
}

export async function fetchAttempts(executionId: string): Promise<ExecutionAttemptPageResponse> {
  return (
    await listExecutionAttempts({
      path: { execution_id: executionId },
      query: { offset: 0, limit: 100 },
      signal: createRequestSignal(),
      throwOnError: true,
    })
  ).data;
}

export async function fetchAudits(query: AuditListQuery): Promise<AuditEventPageResponse> {
  return (await listAuditEvents({ query, signal: createRequestSignal(), throwOnError: true })).data;
}
