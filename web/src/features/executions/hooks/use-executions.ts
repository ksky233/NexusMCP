import { useQuery } from "@tanstack/react-query";

import {
  fetchAttempts,
  fetchAudits,
  fetchExecution,
  fetchExecutions,
  type AuditListQuery,
  type ExecutionListQuery,
} from "@/features/executions/api/executions";

export const executionKeys = {
  all: ["executions"] as const,
  list: (query: ExecutionListQuery) => ["executions", "list", query] as const,
  detail: (id: string) => ["executions", "detail", id] as const,
  attempts: (id: string) => ["executions", "attempts", id] as const,
  audits: (query: AuditListQuery) => ["audit-events", query] as const,
};

export function useExecutions(query: ExecutionListQuery) {
  return useQuery({
    queryKey: executionKeys.list(query),
    queryFn: () => fetchExecutions(query),
    refetchInterval: 15_000,
  });
}

export function useExecution(id: string) {
  return useQuery({
    queryKey: executionKeys.detail(id),
    queryFn: () => fetchExecution(id),
    refetchInterval: 10_000,
  });
}

export function useExecutionAttempts(id: string) {
  return useQuery({
    queryKey: executionKeys.attempts(id),
    queryFn: () => fetchAttempts(id),
    refetchInterval: 10_000,
  });
}

export function useAuditEvents(query: AuditListQuery) {
  return useQuery({
    queryKey: executionKeys.audits(query),
    queryFn: () => fetchAudits(query),
    refetchInterval: 15_000,
  });
}
