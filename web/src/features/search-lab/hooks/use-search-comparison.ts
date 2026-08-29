import { useQuery } from "@tanstack/react-query";

import { fetchSearchCandidates } from "@/features/search-lab/api/search-tools";
import type { ToolSideEffect } from "@/generated/api/types.gen";

export type SearchComparisonInput = {
  text: string;
  namespace?: string;
  sideEffect?: ToolSideEffect;
  limit: number;
};

export function useSearchComparison(input: SearchComparisonInput | null) {
  const common = input
    ? {
        q: input.text,
        limit: input.limit,
        namespace: input.namespace,
        side_effect: input.sideEffect,
      }
    : null;
  const lexical = useQuery({
    queryKey: ["search-lab", "lexical", input],
    queryFn: () => fetchSearchCandidates({ ...common!, retrieval_mode: "lexical" }),
    enabled: Boolean(input),
    retry: false,
  });
  const hybrid = useQuery({
    queryKey: ["search-lab", "hybrid", input],
    queryFn: () => fetchSearchCandidates({ ...common!, retrieval_mode: "hybrid" }),
    enabled: Boolean(input),
    retry: false,
  });
  return { lexical, hybrid };
}
