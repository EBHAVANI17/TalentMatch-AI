import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type {
  CandidateDetail, CandidateNote, CandidateSummary, CandidateUpdate, DownloadLink, Resume, SourcedCandidateCreate,
} from "@/lib/api/types";

export interface CandidateFilters {
  q?: string;
  skills?: string[];
  location?: string;
  min_experience?: number;
  max_experience?: number;
  availability?: string;
  remote_preference?: string;
  max_salary?: number;
  education?: string;
  source?: string;
  sort?: "recent" | "experience" | "active" | "name";
}

export const candidateKeys = {
  all: ["candidates"] as const,
  list: (f: CandidateFilters) => ["candidates", "list", f] as const,
  detail: (id: string) => ["candidates", "detail", id] as const,
  notes: (id: string) => ["candidates", "notes", id] as const,
  resumes: (id: string) => ["candidates", "resumes", id] as const,
  me: ["candidates", "me"] as const,
};

function toQuery(f: CandidateFilters) {
  const { skills, ...rest } = f;
  return { ...rest, skills: undefined, _skills: skills };
}

export function useCandidates(filters: CandidateFilters) {
  return useQuery({
    queryKey: candidateKeys.list(filters),
    queryFn: () => {
      // skills is a repeated query parameter (?skills=Go&skills=AWS)
      const { _skills, ...query } = toQuery(filters);
      const suffix = (_skills ?? []).map((s) => `skills=${encodeURIComponent(s)}`).join("&");
      return api<CandidateSummary[]>(suffix ? `/candidates?${suffix}` : "/candidates", { query });
    },
    placeholderData: (previous) => previous,
  });
}

export function useCandidate(id: string | undefined) {
  return useQuery({ queryKey: candidateKeys.detail(id ?? ""), queryFn: () => api<CandidateDetail>(`/candidates/${id}`), enabled: !!id });
}

export function useCandidateResumes(id: string | undefined) {
  return useQuery({ queryKey: candidateKeys.resumes(id ?? ""), queryFn: () => api<Resume[]>(`/resumes/candidate/${id}`), enabled: !!id });
}

export function useAddCandidate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SourcedCandidateCreate) => api<CandidateDetail>("/candidates", { method: "POST", body: payload }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: candidateKeys.all }),
  });
}

export function useMyProfile() {
  return useQuery({ queryKey: candidateKeys.me, queryFn: () => api<CandidateDetail>("/candidates/me") });
}

export function useUpdateMyProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CandidateUpdate) => api<CandidateDetail>("/candidates/me", { method: "PATCH", body: payload }),
    onSuccess: (profile) => queryClient.setQueryData(candidateKeys.me, profile),
  });
}

export function useNotes(candidateId: string, enabled: boolean) {
  return useQuery({
    queryKey: candidateKeys.notes(candidateId),
    queryFn: () => api<CandidateNote[]>(`/candidates/${candidateId}/notes`),
    enabled,
  });
}

export function useAddNote(candidateId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: string) => api<CandidateNote>(`/candidates/${candidateId}/notes`, { method: "POST", body: { body } }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: candidateKeys.notes(candidateId) }),
  });
}

export function useDeleteNote(candidateId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (noteId: string) => api<void>(`/candidates/${candidateId}/notes/${noteId}`, { method: "DELETE" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: candidateKeys.notes(candidateId) }),
  });
}

export async function openDocument(documentId: string) {
  const link = await api<DownloadLink>(`/documents/${documentId}/download-url`, { method: "POST" });
  window.open(link.url, "_blank", "noopener");
}

export const AVAILABILITY_LABEL: Record<string, string> = {
  open: "Open to opportunities",
  passive: "Open to the right role",
  not_looking: "Not looking",
};
