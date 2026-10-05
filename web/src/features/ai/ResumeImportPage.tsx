import { useState, type ChangeEvent, type DragEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileUp, Trash2 } from "lucide-react";
import { Alert, Button, Card, CardBody, CardHeader, Input, PageHeader, Spinner, TagInput, Textarea, cn, useToast } from "@/components/ui";
import { candidateKeys } from "@/features/candidates/api";
import { api } from "@/lib/api/client";
import type { CandidateDetail, CandidateUpdate, ResumeDraft, ResumeParseResult, SourcedCandidateCreate } from "@/lib/api/types";
import { AINotice } from "./AINotice";

type Mode = "candidate" | "recruiter";
type Experience = NonNullable<ResumeDraft["work_experience"]>[number];
type Education = NonNullable<ResumeDraft["education"]>[number];

function Uploader({ onFile, busy }: { onFile: (f: File) => void; busy: boolean }) {
  const [dragging, setDragging] = useState(false);
  const pick = (e: ChangeEvent<HTMLInputElement>) => e.target.files?.[0] && onFile(e.target.files[0]);
  const drop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files[0]) onFile(e.dataTransfer.files[0]);
  };
  return (
    <label
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={drop}
      className={cn("flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-12 text-center",
        dragging ? "border-primary bg-primary-soft" : "border-border bg-surface hover:border-primary")}
    >
      {busy ? <Spinner label="Reading the resume" /> : (
        <>
          <FileUp className="size-8 text-primary" aria-hidden />
          <span className="font-semibold text-fg">Drop a resume here, or choose a file</span>
          <span className="text-sm text-muted">PDF, DOCX or TXT, up to 10 MB. Scanned images can't be read.</span>
        </>
      )}
      <input type="file" accept=".pdf,.docx,.txt,.md,.json" className="sr-only" onChange={pick} disabled={busy} aria-label="Resume file" />
    </label>
  );
}

function ExperienceEditor({ items, onChange }: { items: Experience[]; onChange: (items: Experience[]) => void }) {
  const update = (i: number, patch: Partial<Experience>) => onChange(items.map((it, j) => (j === i ? { ...it, ...patch } : it)));
  return (
    <div className="flex flex-col gap-3">
      {items.length === 0 && <p className="text-sm text-muted">No roles found. You can add them later on your profile.</p>}
      {items.map((w, i) => (
        <div key={i} className="relative grid gap-3 rounded-lg border border-border p-4 md:grid-cols-2">
          <button type="button" onClick={() => onChange(items.filter((_, j) => j !== i))} className="absolute right-3 top-3 text-muted hover:text-danger" aria-label={`Remove role ${i + 1}`}>
            <Trash2 className="size-4" aria-hidden />
          </button>
          <Input label="Job title" value={w.job_title ?? ""} onChange={(e) => update(i, { job_title: e.target.value })} />
          <Input label="Company" value={w.company_name ?? ""} onChange={(e) => update(i, { company_name: e.target.value })} />
          <Input label="Start (YYYY-MM)" value={w.start_date ?? ""} onChange={(e) => update(i, { start_date: e.target.value })} />
          <Input label="End (YYYY-MM)" value={w.is_current ? "" : w.end_date ?? ""} disabled={!!w.is_current} onChange={(e) => update(i, { end_date: e.target.value })} />
          <div className="md:col-span-2">
            <Textarea label="Highlights" rows={2} value={[w.description, ...(w.achievements ?? [])].filter(Boolean).join("\n")}
              onChange={(e) => update(i, { description: "", achievements: e.target.value.split("\n").filter(Boolean) })} />
          </div>
        </div>
      ))}
    </div>
  );
}

function EducationEditor({ items, onChange }: { items: Education[]; onChange: (items: Education[]) => void }) {
  const update = (i: number, patch: Partial<Education>) => onChange(items.map((it, j) => (j === i ? { ...it, ...patch } : it)));
  return (
    <div className="flex flex-col gap-3">
      {items.length === 0 && <p className="text-sm text-muted">No education found.</p>}
      {items.map((e, i) => (
        <div key={i} className="grid gap-3 rounded-lg border border-border p-4 md:grid-cols-4">
          <Input label="Degree" value={e.degree ?? ""} onChange={(ev) => update(i, { degree: ev.target.value })} />
          <Input label="Field" value={e.field_of_study ?? ""} onChange={(ev) => update(i, { field_of_study: ev.target.value })} />
          <Input label="Institution" value={e.institution ?? ""} onChange={(ev) => update(i, { institution: ev.target.value })} />
          <Input label="Year" type="number" value={e.graduation_year ? String(e.graduation_year) : ""}
            onChange={(ev) => update(i, { graduation_year: ev.target.value ? Number(ev.target.value) : null })} />
        </div>
      ))}
    </div>
  );
}

export function ResumeImportPage({ mode }: { mode: Mode }) {
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [result, setResult] = useState<ResumeParseResult | null>(null);
  const [draft, setDraft] = useState<ResumeDraft | null>(null);
  const [contact, setContact] = useState({ name: "", email: "", phone: "", location: "" });

  const parse = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api<ResumeParseResult>("/ai/resume/parse", { method: "POST", body: form });
    },
    onSuccess: (res) => {
      setResult(res);
      setDraft(res.draft);
      setContact({ name: res.contact.name, email: res.contact.email, phone: res.contact.phone, location: res.contact.location });
    },
  });

  const save = useMutation({
    mutationFn: async () => {
      if (!draft || !result) throw new Error("Nothing to save");
      const profile: CandidateUpdate = {
        title: draft.headline || undefined,
        bio: draft.summary || undefined,
        skills: draft.skills,
        experience_years: draft.total_experience_years ?? undefined,
        location: contact.location || undefined,
        phone: contact.phone || undefined,
        work_experience: (draft.work_experience ?? []).filter((w) => w.job_title && w.company_name).map((w) => ({
          job_title: w.job_title!, company_name: w.company_name!, location: w.location ?? "", start_date: w.start_date ?? "",
          end_date: w.end_date ?? "", is_current: !!w.is_current, description: w.description ?? "", achievements: w.achievements ?? [],
        })),
        education_records: (draft.education ?? []).filter((e) => e.institution && e.degree).map((e) => ({
          institution: e.institution!, degree: e.degree!, field_of_study: e.field_of_study ?? "", graduation_year: e.graduation_year ?? null, gpa: "",
        })),
        certifications: (draft.certifications ?? []).filter((c) => c.name).map((c) => ({ name: c.name!, issuer: c.issuer ?? "", issued_on: c.issued_on ?? "", expires_on: "", credential_url: "" })),
        languages: (draft.languages ?? []).filter((l) => l.language).map((l) => ({ language: l.language!, proficiency: (l.proficiency ?? "professional") as "professional" })),
      };
      if (mode === "candidate") return api<CandidateDetail>("/candidates/me", { method: "PATCH", body: profile });
      const create: SourcedCandidateCreate = {
        ...profile, full_name: contact.name, email: contact.email, title: draft.headline ?? "", resume_document_id: result.document_id,
      } as SourcedCandidateCreate;
      return api<CandidateDetail>("/candidates", { method: "POST", body: create });
    },
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: candidateKeys.all });
      toast.success(mode === "candidate" ? "Your profile was updated from your resume" : `${saved.name} added to your talent pool`);
      navigate(mode === "candidate" ? "/profile" : `/candidates/${saved.id}`);
    },
  });

  const set = (patch: Partial<ResumeDraft>) => setDraft((d) => (d ? { ...d, ...patch } : d));
  const canSave = mode === "candidate" || (contact.name.trim() && contact.email.trim());

  return (
    <div className="flex flex-col gap-6 pb-10">
      <PageHeader
        title={mode === "candidate" ? "Import from resume" : "Add candidate from resume"}
        description="We read the resume and fill in a draft. Check every field before saving; nothing changes until you do."
      />

      {!result ? (
        <>
          {parse.isError && <Alert>{parse.error.message}</Alert>}
          <Uploader onFile={(f) => parse.mutate(f)} busy={parse.isPending} />
        </>
      ) : draft && (
        <>
          <AINotice method={result.method} notice={result.notice} />

          {mode === "recruiter" && (
            <Card>
              <CardHeader title="Contact details" description="Read directly from the file; never sent to an AI model." />
              <CardBody className="grid gap-4 md:grid-cols-2">
                <Input label="Full name" required value={contact.name} onChange={(e) => setContact({ ...contact, name: e.target.value })} />
                <Input label="Email" type="email" required value={contact.email} onChange={(e) => setContact({ ...contact, email: e.target.value })} />
                <Input label="Phone" value={contact.phone} onChange={(e) => setContact({ ...contact, phone: e.target.value })} />
                <Input label="Location" value={contact.location} onChange={(e) => setContact({ ...contact, location: e.target.value })} />
              </CardBody>
            </Card>
          )}

          <Card>
            <CardHeader title="Profile" />
            <CardBody className="grid gap-4 md:grid-cols-2">
              <Input label="Headline" value={draft.headline ?? ""} onChange={(e) => set({ headline: e.target.value })} />
              <Input label="Years of experience" type="number" min={0} step={0.5} value={draft.total_experience_years ?? ""}
                onChange={(e) => set({ total_experience_years: e.target.value ? Number(e.target.value) : null })} />
              <div className="md:col-span-2">
                <Textarea label="Summary" rows={3} value={draft.summary ?? ""} onChange={(e) => set({ summary: e.target.value })} />
              </div>
              <div className="md:col-span-2">
                <TagInput label="Skills" value={draft.skills ?? []} onChange={(skills) => set({ skills })} />
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Experience" />
            <CardBody><ExperienceEditor items={draft.work_experience ?? []} onChange={(work_experience) => set({ work_experience })} /></CardBody>
          </Card>
          <Card>
            <CardHeader title="Education" />
            <CardBody><EducationEditor items={draft.education ?? []} onChange={(education) => set({ education })} /></CardBody>
          </Card>
          {((draft.certifications ?? []).length > 0 || (draft.languages ?? []).length > 0) && (
            <Card>
              <CardHeader title="Certifications and languages" />
              <CardBody className="grid gap-4 md:grid-cols-2">
                <TagInput label="Certifications" value={(draft.certifications ?? []).map((c) => c.name ?? "").filter(Boolean)}
                  onChange={(names) => set({ certifications: names.map((name) => ({ name, issuer: "", issued_on: "" })) })} />
                <TagInput label="Languages" value={(draft.languages ?? []).map((l) => l.language ?? "").filter(Boolean)}
                  onChange={(names) => set({ languages: names.map((language) => ({ language, proficiency: "professional" })) })} />
              </CardBody>
            </Card>
          )}

          {save.isError && <Alert>{save.error.message}</Alert>}
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="secondary" onClick={() => { setResult(null); setDraft(null); }} disabled={save.isPending}>Start over</Button>
            <Button loading={save.isPending} disabled={!canSave} onClick={() => save.mutate()}>
              {mode === "candidate" ? "Save to my profile" : "Create candidate"}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
