import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { Alert, Button, Card, CardBody, CardHeader, Input, Textarea } from "@/components/ui";
import { api } from "@/lib/api/client";
import type { JobAnalysisResult, JobDraftResult } from "@/lib/api/types";
import { AINotice } from "./AINotice";

type Draft = JobDraftResult["draft"];
type Analysis = JobAnalysisResult["analysis"];

/** Generate a job from a brief, or turn a pasted description into requirements. Results fill the form for editing. */
export function JobDraftAssistant({ onDraft, onAnalysis }: { onDraft: (d: Draft) => void; onAnalysis: (a: Analysis, text: string) => void }) {
  const [brief, setBrief] = useState("");
  const [pasted, setPasted] = useState("");
  const [showAnalyze, setShowAnalyze] = useState(false);
  const [notice, setNotice] = useState<{ method: string; notice: string } | null>(null);

  const generate = useMutation({
    mutationFn: () => api<JobDraftResult>("/ai/jobs/generate", { method: "POST", body: { brief } }),
    onSuccess: (res) => { onDraft(res.draft); setNotice(res); },
  });
  const analyze = useMutation({
    mutationFn: () => api<JobAnalysisResult>("/ai/jobs/analyze", { method: "POST", body: { text: pasted } }),
    onSuccess: (res) => { onAnalysis(res.analysis, pasted); setNotice(res); },
  });

  return (
    <Card>
      <CardHeader title="Draft with AI" description="Describe the role in a line, or paste an existing description. You review everything before publishing." />
      <CardBody className="flex flex-col gap-4">
        {notice && <AINotice method={notice.method} notice={notice.notice} />}
        {(generate.isError || analyze.isError) && <Alert>{(generate.error ?? analyze.error)?.message}</Alert>}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <div className="flex-1">
            <Input label="Brief" placeholder="e.g. Senior Backend Developer, 5+ years, Node.js, AWS, Bangalore, hybrid" value={brief} onChange={(e) => setBrief(e.target.value)} />
          </div>
          <Button icon={<Sparkles className="size-4" aria-hidden />} loading={generate.isPending} disabled={brief.trim().length < 3} onClick={() => generate.mutate()}>
            Generate draft
          </Button>
        </div>
        {showAnalyze ? (
          <div className="flex flex-col gap-2">
            <Textarea label="Existing job description" rows={6} value={pasted} onChange={(e) => setPasted(e.target.value)} />
            <div className="flex justify-end">
              <Button variant="secondary" loading={analyze.isPending} disabled={pasted.trim().length < 20} onClick={() => analyze.mutate()}>
                Extract requirements
              </Button>
            </div>
          </div>
        ) : (
          <button type="button" onClick={() => setShowAnalyze(true)} className="self-start text-sm font-medium text-primary hover:underline">
            Or paste an existing job description
          </button>
        )}
      </CardBody>
    </Card>
  );
}
