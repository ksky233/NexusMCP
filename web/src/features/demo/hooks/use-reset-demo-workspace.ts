import { useMutation, useQueryClient } from "@tanstack/react-query";

import { resetPublicDemoWorkspace } from "@/features/demo/api/reset-demo-workspace";

export function useResetDemoWorkspace() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: resetPublicDemoWorkspace,
    onSuccess: async () => {
      await queryClient.resetQueries();
    },
  });
}
