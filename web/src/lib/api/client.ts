import { client } from "@/generated/api/client.gen";
import { normalizeApiError } from "@/lib/api/api-error";

client.interceptors.error.use((error, response) => normalizeApiError(error, response));

export { client as adminApiClient };

export function createRequestSignal(timeoutMilliseconds = 10_000): AbortSignal {
  return AbortSignal.timeout(timeoutMilliseconds);
}
