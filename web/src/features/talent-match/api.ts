import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { Application, CandidateMatchItem, CandidateMatchList, JobMatchItem } from "@/lib/api/types";

export interface MatchFilters {
  min_score?: number;
  skills?: string[];
  location?: string;
  min_experience?: number;
  education?: string;
  availability?: string;
  max_salary?: number;
  remote_preference?: string;
  status?: "active" | "new" | "shortlisted" | "dismissed" | "all";
  sort?: "score" | "experience" | "active" | "recent";
}

export const matchKeys = {
  all: ["matches"] as const,
  list: (jobId: string, f: MatchFilters) => ["matches", jobId, f] as const,
  mine: ["matches", "me"] as const,
};

export function useJobMatches(jobId: string | undefined, filters: MatchFilters) {
  return useQuery({
    queryKey: matchKeys.list(jobId ?? "", filters),
    enabled: !!jobId,
    placeholderData: (previous) => previous,
    queryFn: () => {
      const { skills, ...rest } = filters;
      const repeated = (skills ?? []).map((s) => `skills=${encodeURIComponent(s)}`).join("&");
      const path = `/matching/jobs/${jobId}/candidates${repeated ? `?${repeated}` : ""}`;
      return api<CandidateMatchList>(path, { query: { ...rest, limit: 100 } });
    },
  });
}

export function useMatchDecision(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ candidateId, action }: { candidateId: string; action: "shortlist" | "reject" | "restore" }) =>
      api<CandidateMatchItem>(`/matching/jobs/${jobId}/candidates/${candidateId}/${action}`, { method: "POST" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: matchKeys.all });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useMyJobMatches() {
  return useQuery({ queryKey: matchKeys.mine, queryFn: () => api<JobMatchItem[]>("/matching/me/jobs", { query: { limit: 50 } }) });
}

export function useApply() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => api<Application>("/applications", { method: "POST", body: { job_id: jobId } }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: matchKeys.mine });
      void queryClient.invalidateQueries({ queryKey: ["applications"] });
    },
  });
}
