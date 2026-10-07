import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Bot, SendHorizontal, Wand2 } from "lucide-react";
import { Alert, Button, Spinner, cn } from "@/components/ui";
import type { CopilotMessage } from "@/lib/api/types";
import { useAsk, useConversation } from "./api";
import { MessageContent } from "./MessageContent";

export interface CopilotContext {
  job_id?: string;
  candidate_id?: string;
}

const MAX_LENGTH = 1000;

export function suggestionsFor(context: CopilotContext): string[] {
  if (context.job_id) return ["Who are the best candidates for this job?", "Show the pipeline for this job", "Any interviews coming up?"];
  if (context.candidate_id) return ["Summarize this candidate", "Which of our jobs fit this candidate?"];
  return ["Show my hiring pipeline", "List my jobs", "Any interviews coming up?", "Find senior Python engineers"];
}

function AnswerNotice({ message }: { message: CopilotMessage }) {
  if (!message.notice) return null;
  const Icon = message.method === "ai" ? Bot : Wand2;
  return (
    <p className="mt-2 flex items-start gap-1.5 text-xs text-muted">
      <Icon className="mt-0.5 size-3 shrink-0" aria-hidden />
      <span>{message.notice}</span>
    </p>
  );
}

/** "Tell me more about [C1]" -> "Tell me more about Aarav Sharma" (names come from the message's citations). */
function readableFollowUp(q: string, message: CopilotMessage): string {
  const labels = new Map(message.citations.filter((c) => c.available).map((c) => [c.ref, c.label]));
  return q.replace(/\[([CJS]\d+)\]/g, (_, ref: string) => labels.get(ref) ?? "this record");
}

function Bubble({ message, onNavigate, onFollowUp }: { message: CopilotMessage; onNavigate?: () => void; onFollowUp: (q: string) => void }) {
  const mine = message.role === "user";
  return (
    <li className={cn("flex", mine ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[92%] rounded-2xl px-3.5 py-2.5",
          mine ? "bg-primary text-primary-fg" : "border border-border bg-surface text-fg",
        )}
      >
        {mine ? (
          <p className="whitespace-pre-line text-sm">{message.content}</p>
        ) : (
          <>
            <MessageContent text={message.content} citations={message.citations} onNavigate={onNavigate} />
            <AnswerNotice message={message} />
            {message.follow_ups.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {message.follow_ups.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => onFollowUp(q)}
                    className="rounded-full border border-border px-2.5 py-1 text-xs text-muted hover:border-primary hover:text-primary"
                  >
                    {readableFollowUp(q, message)}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </li>
  );
}

interface ThreadProps {
  conversationId: string | null;
  onConversationChange: (id: string) => void;
  context?: CopilotContext;
  /** Called when a citation link is followed (the panel closes itself). */
  onNavigate?: () => void;
}

export function CopilotThread({ conversationId, onConversationChange, context = {}, onNavigate }: ThreadProps) {
  const conversation = useConversation(conversationId);
  const ask = useAsk();
  const [draft, setDraft] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const messages = conversation.data?.messages ?? [];

  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, ask.isPending]);

  function send(text: string) {
    const message = text.trim();
    if (!message || ask.isPending) return;
    setDraft("");
    ask.mutate(
      { message, conversation_id: conversationId, context },
      { onSuccess: (res) => onConversationChange(res.conversation_id) },
    );
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    send(draft);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(draft);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {conversation.isLoading && <Spinner label="Loading conversation" />}
        {!conversationId && !ask.isPending && (
          <div className="space-y-3">
            <p className="text-sm text-muted">
              Ask about your jobs, candidates, pipeline or interviews. Answers come only from your organization's
              records and link to them, so you can check before acting.
            </p>
            <div className="flex flex-wrap gap-2">
              {suggestionsFor(context).map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => send(q)}
                  className="rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium text-fg hover:border-primary hover:text-primary"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        <ul className="space-y-3" aria-live="polite">
          {messages.map((m) => (
            <Bubble key={m.id} message={m} onNavigate={onNavigate} onFollowUp={send} />
          ))}
          {ask.isPending && ask.variables && (
            <>
              <li className="flex justify-end">
                <p className="max-w-[92%] whitespace-pre-line rounded-2xl bg-primary px-3.5 py-2.5 text-sm text-primary-fg">
                  {ask.variables.message}
                </p>
              </li>
              <li className="flex items-center gap-2 text-sm text-muted">
                <Spinner label="Copilot is looking this up" className="size-4" /> Looking this up...
              </li>
            </>
          )}
        </ul>
        {ask.isError && (
          <div className="mt-3">
            <Alert>{ask.error.message}</Alert>
          </div>
        )}
        <div ref={bottom} />
      </div>

      <form onSubmit={onSubmit} className="border-t border-border bg-surface p-3">
        <label htmlFor="copilot-input" className="sr-only">Ask the copilot</label>
        <div className="flex items-end gap-2">
          <textarea
            id="copilot-input"
            value={draft}
            maxLength={MAX_LENGTH}
            rows={2}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask about candidates, jobs or your pipeline"
            className="min-h-[2.5rem] flex-1 resize-none rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-fg placeholder:text-muted focus:border-primary focus:bg-surface focus:outline-none"
          />
          <Button type="submit" size="md" disabled={!draft.trim() || ask.isPending} aria-label="Send">
            <SendHorizontal className="size-4" aria-hidden />
          </Button>
        </div>
        <p className="mt-1.5 text-[11px] text-muted">Enter to send, Shift+Enter for a new line. Copilot recommends; you decide.</p>
      </form>
    </div>
  );
}
