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
      message: "服务端响应不符合 Admin API Contract。",
      requestId: response?.headers.get("X-Request-ID") ?? undefined,
      cause: error,
    });
  }
  if (error instanceof DOMException && error.name === "TimeoutError") {
    return new ApiClientError({
      kind: "timeout",
      code: "request_timeout",
      message: "Admin API 未在超时时间内响应。",
      cause: error,
    });
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return new ApiClientError({
      kind: "abort",
      code: "request_aborted",
      message: "Admin API 请求已取消。",
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
        message: "服务端返回了不受支持的错误响应格式。",
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
      message: "服务端返回的 Problem Details 格式无效。",
      status: response.status,
      requestId,
      cause: error,
    });
  }
  if (error instanceof TypeError) {
    return new ApiClientError({
      kind: "network",
      code: "network_error",
      message: "无法连接 Admin API。",
      cause: error,
    });
  }
  return new ApiClientError({
    kind: "unknown",
    code: "unknown_client_error",
    message: "Admin API 请求发生未知异常。",
    cause: error,
  });
}

export function asApiClientError(error: unknown): ApiClientError {
  return error instanceof ApiClientError ? error : normalizeApiError(error);
}
