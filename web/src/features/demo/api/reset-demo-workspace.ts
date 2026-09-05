import { resetDemoWorkspace } from "@/generated/api/sdk.gen";
import type { DemoWorkspaceResetResponse } from "@/generated/api/types.gen";
import { createRequestSignal } from "@/lib/api/client";

export async function resetPublicDemoWorkspace(): Promise<DemoWorkspaceResetResponse> {
  const result = await resetDemoWorkspace({
    signal: createRequestSignal(30_000),
    throwOnError: true,
  });
  return result.data;
}
