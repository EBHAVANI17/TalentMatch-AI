import { useSearchParams } from "react-router-dom";
import { MessageSquare, Plus, Trash2 } from "lucide-react";
import { Button, Card, PageHeader, Skeleton, cn, useToast } from "@/components/ui";
import { formatDate } from "@/lib/format";
import { useConversations, useDeleteConversation } from "./api";
import { CopilotThread } from "./CopilotThread";

export function CopilotPage() {
  const [params, setParams] = useSearchParams();
  const conversationId = params.get("c");
  const conversations = useConversations();
  const remove = useDeleteConversation();
  const toast = useToast();

  const select = (id: string | null) => setParams(id ? { c: id } : {}, { replace: true });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Copilot"
        description="Ask about your jobs, candidates, pipeline and interviews. Answers use only your organization's records and link to them."
        actions={
          <Button variant="secondary" size="sm" onClick={() => select(null)}>
            <Plus className="size-4" aria-hidden /> New conversation
          </Button>
        }
      />
      <div className="grid gap-4 lg:grid-cols-[16rem_1fr]">
        <Card className="h-fit">
          <nav aria-label="Conversations" className="p-2">
            <p className="px-2 pb-2 pt-1 text-xs font-semibold uppercase tracking-wide text-muted">History</p>
            {conversations.isLoading && <Skeleton className="h-24" />}
            {conversations.data?.length === 0 && <p className="px-2 pb-2 text-sm text-muted">No conversations yet.</p>}
            <ul className="space-y-0.5">
              {conversations.data?.map((c) => (
                <li key={c.id} className="group flex items-center">
                  <button
                    type="button"
                    onClick={() => select(c.id)}
                    aria-current={c.id === conversationId ? "true" : undefined}
                    className={cn(
                      "flex min-w-0 flex-1 items-start gap-2 rounded-lg px-2 py-2 text-left text-sm",
                      c.id === conversationId ? "bg-primary-soft text-primary" : "text-fg hover:bg-surface-2",
                    )}
                  >
                    <MessageSquare className="mt-0.5 size-4 shrink-0" aria-hidden />
                    <span className="min-w-0">
                      <span className="block truncate font-medium">{c.title}</span>
                      {c.updated_at && <span className="block text-xs text-muted">{formatDate(c.updated_at)}</span>}
                    </span>
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete conversation: ${c.title}`}
                    className="rounded-lg p-1.5 text-muted opacity-0 hover:text-danger focus:opacity-100 group-hover:opacity-100"
                    onClick={() =>
                      remove.mutate(c.id, {
                        onSuccess: () => {
                          if (c.id === conversationId) select(null);
                          toast.success("Conversation deleted");
                        },
                      })
                    }
                  >
                    <Trash2 className="size-4" aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          </nav>
        </Card>
        <Card className="flex h-[calc(100vh-14rem)] min-h-[28rem] flex-col overflow-hidden">
          <CopilotThread key={conversationId ?? "new"} conversationId={conversationId} onConversationChange={(id) => select(id)} />
        </Card>
      </div>
    </div>
  );
}
