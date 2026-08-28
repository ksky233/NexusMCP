import { expect, test } from "vitest";

import { normalizeApiError } from "@/lib/api/api-error";

test.each([
  ["TimeoutError", "timeout", "request_timeout"],
  ["AbortError", "abort", "request_aborted"],
] as const)("classifies %s without parsing an error body", (domName, kind, code) => {
  const error = normalizeApiError(new DOMException("request stopped", domName));

  expect(error.kind).toBe(kind);
  expect(error.code).toBe(code);
});

test("rejects non-Problem Details server errors as protocol failures", () => {
  const response = new Response("gateway failed", {
    status: 502,
    headers: {
      "Content-Type": "text/plain",
      "X-Request-ID": "request-invalid-content-type",
    },
  });

  const error = normalizeApiError("gateway failed", response);

  expect(error.kind).toBe("protocol");
  expect(error.code).toBe("invalid_error_content_type");
  expect(error.requestId).toBe("request-invalid-content-type");
});
