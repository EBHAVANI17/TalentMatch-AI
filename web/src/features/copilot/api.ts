import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type {
  CopilotAskIn,
  CopilotAskOut,
  CopilotConversation,
  CopilotConversationSummary,
  CopilotMessage,
} from "@/lib/api/types";

export const copilotKeys = {
  conversations: ["copilot", "conversations"] as const,
  conversation: (id: string) => ["copilot", "conversations", id] as const,
};

export function useConversations(enabled = true) {
  return useQuery({
    queryKey: copilotKeys.conversations,
    enabled,
    queryFn: () => api<CopilotConversationSummary[]>("/copilot/conversations"),
  });
}

export function useConversation(id: string | null) {
  return useQuery({
    queryKey: copilotKeys.conversation(id ?? ""),
    enabled: !!id,
    queryFn: () => api<CopilotConversation>(`/copilot/conversations/${id}`),
  });
}

export function useAsk() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CopilotAskIn) => api<CopilotAskOut>("/copilot/messages", { method: "POST", body }),
    onSuccess: (res, body) => {
      // Append both turns locally instead of refetching, so the thread doesn't flicker
      const question: CopilotMessage = {
        id: `local-${res.message.id}`, role: "user", content: body.message, citations: [], follow_ups: [],
        method: "", notice: "", created_at: null,
      };
      queryClient.setQueryData<CopilotConversation>(copilotKeys.conversation(res.conversation_id), (old) => ({
        id: res.conversation_id,
        title: old?.title ?? body.message.slice(0, 120),
        updated_at: res.message.created_at,
        messages: [...(old?.messages ?? []), question, res.message],
      }));
      void queryClient.invalidateQueries({ queryKey: copilotKeys.conversations, exact: true });
    },
  });
}

export function useDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<null>(`/copilot/conversations/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: copilotKeys.conversations }),
  });
}
