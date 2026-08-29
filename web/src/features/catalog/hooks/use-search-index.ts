import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchToolSearchIndexStatus,
  fetchToolSearchReindexJobs,
  startToolSearchReindexJob,
} from "@/features/catalog/api/search-index";
import type { CreateToolSearchReindexJobRequest } from "@/generated/api/types.gen";

export const searchIndexKeys = {
  status: ["tool-search-index", "status"] as const,
  jobs: ["tool-search-index", "jobs"] as const,
};

export function useSearchIndexStatus() {
  return useQuery({
    queryKey: searchIndexKeys.status,
    queryFn: fetchToolSearchIndexStatus,
  });
}

export function useSearchIndexJobs() {
  return useQuery({
    queryKey: searchIndexKeys.jobs,
    queryFn: fetchToolSearchReindexJobs,
    refetchInterval: (query) => {
      const jobs = query.state.data?.items ?? [];
      return jobs.some((job) => job.status === "pending" || job.status === "running")
        ? 1_000
        : false;
    },
  });
}

export function useStartSearchIndexJob() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateToolSearchReindexJobRequest) => startToolSearchReindexJob(body),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: searchIndexKeys.jobs }),
        client.invalidateQueries({ queryKey: searchIndexKeys.status }),
      ]);
    },
  });
}
