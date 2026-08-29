import {
  createToolSearchReindexJob,
  getToolSearchIndexStatus,
  listToolSearchReindexJobs,
} from "@/generated/api/sdk.gen";
import type {
  CreateToolSearchReindexJobRequest,
  ToolSearchIndexStatusResponse,
  ToolSearchReindexJobPageResponse,
  ToolSearchReindexJobResponse,
} from "@/generated/api/types.gen";
import { createRequestSignal } from "@/lib/api/client";

export async function fetchToolSearchIndexStatus(): Promise<ToolSearchIndexStatusResponse> {
  return (
    await getToolSearchIndexStatus({
      query: { offset: 0, limit: 100 },
      signal: createRequestSignal(),
      throwOnError: true,
    })
  ).data;
}

export async function fetchToolSearchReindexJobs(): Promise<ToolSearchReindexJobPageResponse> {
  return (
    await listToolSearchReindexJobs({
      query: { offset: 0, limit: 5 },
      signal: createRequestSignal(),
      throwOnError: true,
    })
  ).data;
}

export async function startToolSearchReindexJob(
  body: CreateToolSearchReindexJobRequest,
): Promise<ToolSearchReindexJobResponse> {
  return (
    await createToolSearchReindexJob({
      body,
      signal: createRequestSignal(),
      throwOnError: true,
    })
  ).data;
}
