import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { PublicConfig } from "@/lib/api/types";

export function usePublicConfig() {
  return useQuery({
    queryKey: ["config", "public"],
    queryFn: () => api<PublicConfig>("/config/public", { auth: false }),
    staleTime: 5 * 60_000,
  });
}
