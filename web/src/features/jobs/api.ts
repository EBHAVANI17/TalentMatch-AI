import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { Application, Job, JobCreate, JobUpdate } from "@/lib/api/types";

export type JobAction = "publish" | "pause" | "close" | "archive";

export interface JobFilters {
  status?: string;
  q?: string;
  department?: string;
  workplace_type?: string;
}

export const jobKeys = {
  all: ["jobs"] as const,
  list: (filters: JobFilters) => ["jobs", "list", filters] as const,
  detail: (id: string) => ["jobs", "detail", id] as const,
  applicants: (id: string) => ["jobs", "applicants", id] as const,
};

export function useJobs(filters: JobFilters) {
  return useQuery({
    queryKey: jobKeys.list(filters),
    queryFn: () => api<Job[]>("/jobs", { query: { ...filters, status: filters.status ?? "all" } }),
    placeholderData: (previous) => previous,
  });
}

export function useJob(id: string | undefined) {
  return useQuery({ queryKey: jobKeys.detail(id ?? ""), queryFn: () => api<Job>(`/jobs/${id}`), enabled: !!id });
}

export function useJobApplicants(id: string | undefined) {
  return useQuery({
    queryKey: jobKeys.applicants(id ?? ""),
    queryFn: () => api<Application[]>("/applications", { query: { job_id: id } }),
    enabled: !!id,
  });
}

function useInvalidateJobs() {
  const queryClient = useQueryClient();
  return (job?: Job) => {
    void queryClient.invalidateQueries({ queryKey: jobKeys.all });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    if (job) queryClient.setQueryData(jobKeys.detail(job.id), job);
  };
}

export function useCreateJob() {
  const invalidate = useInvalidateJobs();
  return useMutation({
    mutationFn: (payload: JobCreate) => api<Job>("/jobs", { method: "POST", body: payload }),
    onSuccess: invalidate,
  });
}

export function useUpdateJob(id: string) {
  const invalidate = useInvalidateJobs();
  return useMutation({
    mutationFn: (payload: JobUpdate) => api<Job>(`/jobs/${id}`, { method: "PATCH", body: payload }),
    onSuccess: invalidate,
  });
}

export function useJobAction(id: string) {
  const invalidate = useInvalidateJobs();
  return useMutation({
    mutationFn: (action: JobAction) => api<Job>(`/jobs/${id}/${action}`, { method: "POST" }),
    onSuccess: invalidate,
  });
}

export function useDuplicateJob(id: string) {
  const invalidate = useInvalidateJobs();
  return useMutation({
    mutationFn: () => api<Job>(`/jobs/${id}/duplicate`, { method: "POST" }),
    onSuccess: invalidate,
  });
}

export function useMoveApplication(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ applicationId, stage }: { applicationId: string; stage: string }) =>
      api<Application>(`/applications/${applicationId}/stage`, { method: "PATCH", body: { stage, reason: "Updated from job page" } }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: jobKeys.applicants(jobId) });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export const JOB_STATUS_TONE: Record<string, "success" | "warning" | "neutral" | "danger" | "primary"> = {
  Active: "success",
  Draft: "neutral",
  Paused: "warning",
  Closed: "danger",
  Archived: "neutral",
};

/** "Active" is stored for backward compatibility; people call it Published. */
export const jobStatusLabel = (status: string) => (status === "Active" ? "Published" : status);

export const ACTIONS_BY_STATUS: Record<string, JobAction[]> = {
  Draft: ["publish", "archive"],
  Active: ["pause", "close"],
  Paused: ["publish", "close", "archive"],
  Closed: ["publish", "archive"],
  Archived: [],
};
