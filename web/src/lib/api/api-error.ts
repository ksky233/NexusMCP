import { zProblemDetails } from "@/generated/api/zod.gen";
import { ZodError } from "zod";

export type ApiErrorKind = "problem" | "network" | "timeout" | "abort" | "protocol" | "unknown";

export class ApiClientError extends Error {
  readonly kind: ApiErrorKind;
  readonly code: string;
  readonly status: number | undefined;
  readonly requestId: string | undefined;

  constructor(options: {
    kind: ApiErrorKind;
    code: string;
    message: string;
    status?: number;
    requestId?: string;
    cause?: unknown;
  }) {
    super(options.message, { cause: options.cause });
    this.name = "ApiClientError";
    this.kind = options.kind;
    this.code = options.code;
    this.status = options.status;
    this.requestId = options.requestId;
  }
}

export function normalizeApiError(error: unknown, response?: Response): ApiClientError {
  if (error instanceof ApiClientError) {
    return error;
  }
  if (error instanceof ZodError) {
    return new ApiClientError({
      kind: "protocol",
      code: "invalid_response_schema",
      message: "The server returned data that did not match the Admin API contract.",
      requestId: response?.headers.get("X-Request-ID") ?? undefined,
      cause: error,
    });
  }
  if (error instanceof DOMException && error.name === "TimeoutError") {
    return new ApiClientError({
      kind: "timeout",
      code: "request_timeout",
      message: "The Admin API did not respond before the request timed out.",
      cause: error,
    });
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return new ApiClientError({
      kind: "abort",
      code: "request_aborted",
      message: "The Admin API request was cancelled.",
      cause: error,
    });
  }
  if (response) {
    const contentType = response.headers.get("Content-Type")?.toLowerCase() ?? "";
    const requestId = response.headers.get("X-Request-ID") ?? undefined;
    if (!contentType.includes("application/problem+json")) {
      return new ApiClientError({
        kind: "protocol",
        code: "invalid_error_content_type",
        message: "The server returned an unsupported error response.",
        status: response.status,
        requestId,
        cause: error,
      });
    }
    const problem = zProblemDetails.safeParse(error);
    if (problem.success) {
      return new ApiClientError({
        kind: "problem",
        code: problem.data.code,
        message: problem.data.detail,
        status: problem.data.status,
        requestId: problem.data.request_id ?? requestId,
        cause: error,
      });
    }
    return new ApiClientError({
      kind: "protocol",
      code: "invalid_problem_details",
      message: "The server returned malformed Problem Details.",
      status: response.status,
      requestId,
      cause: error,
    });
  }
  if (error instanceof TypeError) {
    return new ApiClientError({
      kind: "network",
      code: "network_error",
      message: "The Admin API could not be reached.",
      cause: error,
    });
  }
  return new ApiClientError({
    kind: "unknown",
    code: "unknown_client_error",
    message: "The Admin API request failed unexpectedly.",
    cause: error,
  });
}

export function asApiClientError(error: unknown): ApiClientError {
  return error instanceof ApiClientError ? error : normalizeApiError(error);
}
