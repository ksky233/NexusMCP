import { useQuery } from "@tanstack/react-query";

import { fetchDashboard } from "@/features/dashboard/api/get-dashboard";
import { ApiClientError } from "@/lib/api/api-error";

export const dashboardQueryKey = ["dashboard"] as const;

export function useDashboardQuery() {
  return useQuery({
    queryKey: dashboardQueryKey,
    queryFn: fetchDashboard,
    retry: (failureCount, error) =>
      failureCount < 1 && error instanceof ApiClientError && error.kind === "network",
    refetchInterval: 30_000,
  });
}
