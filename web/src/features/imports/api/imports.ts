import {
  directPublishImportedOperation,
  getOpenApiImport,
  getToolBinding,
  getToolVersion,
  listOpenApiImports,
  listReviewOperations,
  publishToolVersion,
  reviewImportedOperation,
  submitOpenApiImport,
  submitToolVersionReview,
} from "@/generated/api/sdk.gen";
import type {
  DirectPublishOperationResponse,
  ImportDetailResponse,
  ImportJobPageResponse,
  ListOpenApiImportsData,
  ListReviewOperationsData,
  PublishToolRequest,
  ReviewOperationPageResponse,
  ReviewOperationRequest,
  ReviewOperationResponse,
  SubmitImportRequest,
  SubmitImportResponse,
  ToolBindingDetailResponse,
  ToolVersionDetailResponse,
} from "@/generated/api/types.gen";
import { createRequestSignal } from "@/lib/api/client";

export type ImportListQuery = NonNullable<ListOpenApiImportsData["query"]>;
export type ReviewListQuery = NonNullable<ListReviewOperationsData["query"]>;

export async function fetchImports(query: ImportListQuery): Promise<ImportJobPageResponse> {
  return (await listOpenApiImports({ query, signal: createRequestSignal(), throwOnError: true }))
    .data;
}

export async function startImport(body: SubmitImportRequest): Promise<SubmitImportResponse> {
  return (await submitOpenApiImport({ body, signal: createRequestSignal(), throwOnError: true }))
    .data;
}

export async function fetchImport(importId: string): Promise<ImportDetailResponse> {
  return (
    await getOpenApiImport({
      path: { import_job_id: importId },
      signal: createRequestSignal(),
      throwOnError: true,
    })
  ).data;
}

export async function fetchReviewQueue(
  query: ReviewListQuery,
): Promise<ReviewOperationPageResponse> {
  return (await listReviewOperations({ query, signal: createRequestSignal(), throwOnError: true }))
    .data;
}

export async function acceptOperation(
  operationId: string,
  body: ReviewOperationRequest,
): Promise<ReviewOperationResponse> {
  return (
    await reviewImportedOperation({
      body,
      path: { operation_id: operationId },
      signal: createRequestSignal(),
      throwOnError: true,
    })
  ).data;
}

export async function directPublishOperation(
  operationId: string,
  body: ReviewOperationRequest,
): Promise<DirectPublishOperationResponse> {
  return (
    await directPublishImportedOperation({
      body,
      path: { operation_id: operationId },
      signal: createRequestSignal(),
      throwOnError: true,
    })
  ).data;
}

export async function fetchToolVersion(versionId: string): Promise<ToolVersionDetailResponse> {
  return (
    await getToolVersion({
      path: { tool_version_id: versionId },
      signal: createRequestSignal(),
      throwOnError: true,
    })
  ).data;
}

export async function fetchBinding(bindingId: string): Promise<ToolBindingDetailResponse> {
  return (
    await getToolBinding({
      path: { tool_binding_id: bindingId },
      signal: createRequestSignal(),
      throwOnError: true,
    })
  ).data;
}

export async function submitVersion(versionId: string): Promise<void> {
  await submitToolVersionReview({
    path: { tool_version_id: versionId },
    signal: createRequestSignal(),
    throwOnError: true,
  });
}

export async function publishVersion(
  toolId: string,
  versionId: string,
  body: PublishToolRequest,
): Promise<void> {
  await publishToolVersion({
    body,
    path: { tool_id: toolId, tool_version_id: versionId },
    signal: createRequestSignal(),
    throwOnError: true,
  });
}
