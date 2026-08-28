import type {
  ListUpstreamsData,
  RegisterUpstreamRequest,
  UpdateUpstreamRequest,
  UpstreamDetailResponse,
  UpstreamPageResponse,
  UpstreamResponse,
} from "@/generated/api/types.gen";
import {
  disableUpstream,
  getUpstream,
  listUpstreams,
  registerUpstream,
  updateUpstream,
} from "@/generated/api/sdk.gen";
import { createRequestSignal } from "@/lib/api/client";

export type UpstreamListQuery = NonNullable<ListUpstreamsData["query"]>;

export async function fetchUpstreams(query: UpstreamListQuery): Promise<UpstreamPageResponse> {
  const result = await listUpstreams({ query, signal: createRequestSignal(), throwOnError: true });
  return result.data;
}

export async function fetchUpstream(upstreamId: string): Promise<UpstreamDetailResponse> {
  const result = await getUpstream({
    path: { upstream_service_id: upstreamId },
    signal: createRequestSignal(),
    throwOnError: true,
  });
  return result.data;
}

export async function createUpstream(body: RegisterUpstreamRequest): Promise<UpstreamResponse> {
  const result = await registerUpstream({
    body,
    signal: createRequestSignal(),
    throwOnError: true,
  });
  return result.data;
}

export async function saveUpstream(
  upstreamId: string,
  body: UpdateUpstreamRequest,
): Promise<UpstreamResponse> {
  const result = await updateUpstream({
    body,
    path: { upstream_service_id: upstreamId },
    signal: createRequestSignal(),
    throwOnError: true,
  });
  return result.data;
}

export async function deactivateUpstream(upstreamId: string): Promise<UpstreamResponse> {
  const result = await disableUpstream({
    path: { upstream_service_id: upstreamId },
    signal: createRequestSignal(),
    throwOnError: true,
  });
  return result.data;
}
