import { Bot, Wand2 } from "lucide-react";

/** Always shown next to AI-produced drafts: how the draft was made and that it needs review. */
export function AINotice({ method, notice }: { method: string; notice: string }) {
  const ai = method === "ai";
  return (
    <div role="status" className="flex items-start gap-2 rounded-lg border border-primary/30 bg-primary-soft px-3 py-2 text-sm text-primary">
      {ai ? <Bot className="mt-0.5 size-4 shrink-0" aria-hidden /> : <Wand2 className="mt-0.5 size-4 shrink-0" aria-hidden />}
      <span>
        <span className="font-semibold">{ai ? "AI draft" : "Automatic draft"}</span> · {notice}
      </span>
    </div>
  );
}
