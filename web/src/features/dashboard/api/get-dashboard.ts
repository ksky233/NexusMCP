import type { DashboardResponse } from "@/generated/api/types.gen";
import { getDashboard } from "@/generated/api/sdk.gen";
import { createRequestSignal } from "@/lib/api/client";

export type DashboardSnapshot = {
  data: DashboardResponse;
  requestId?: string;
};

export async function fetchDashboard(): Promise<DashboardSnapshot> {
  const result = await getDashboard({
    throwOnError: true,
    signal: createRequestSignal(),
  });
  const requestId = result.response.headers.get("X-Request-ID") ?? undefined;
  return requestId ? { data: result.data, requestId } : { data: result.data };
}
