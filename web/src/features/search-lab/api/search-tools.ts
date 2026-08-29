import { searchTools } from "@/generated/api/sdk.gen";
import type { SearchLabResponse, SearchToolsData } from "@/generated/api/types.gen";
import { createRequestSignal } from "@/lib/api/client";

export type SearchToolsQuery = SearchToolsData["query"];

export async function fetchSearchCandidates(query: SearchToolsQuery): Promise<SearchLabResponse> {
  return (await searchTools({ query, signal: createRequestSignal(60_000), throwOnError: true }))
    .data;
}
