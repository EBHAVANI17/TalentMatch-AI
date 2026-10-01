import { useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { Award, Download, ExternalLink, FileText, Languages, Lock, Mail, MapPin, Phone, Trash2 } from "lucide-react";
import {
  Avatar, Badge, Button, Card, CardBody, CardHeader, EmptyState, ErrorState, FullPageSpinner, Textarea, useToast,
} from "@/components/ui";
import { useAuth } from "@/lib/auth/AuthProvider";
import { isOrgMember } from "@/lib/auth/roles";
import { experienceLabel, formatDate, formatSalaryRange, timeAgo } from "@/lib/format";
import { AVAILABILITY_LABEL, openDocument, useAddNote, useCandidate, useCandidateResumes, useDeleteNote, useNotes } from "./api";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader title={title} />
      <CardBody>{children}</CardBody>
    </Card>
  );
}

function NotesPanel({ candidateId }: { candidateId: string }) {
  const { user } = useAuth();
  const toast = useToast();
  const notes = useNotes(candidateId, true);
  const add = useAddNote(candidateId);
  const remove = useDeleteNote(candidateId);
  const [body, setBody] = useState("");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    try {
      await add.mutateAsync(body.trim());
      setBody("");
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  return (
    <Card>
      <CardHeader title="Team notes" description="Only your organization can see these." />
      <CardBody className="flex flex-col gap-4">
        <form onSubmit={onSubmit} className="flex flex-col gap-2">
          <Textarea label="Add a note" rows={3} value={body} onChange={(e) => setBody(e.target.value)} maxLength={5000} />
          <div className="flex justify-end">
            <Button size="sm" type="submit" loading={add.isPending} disabled={!body.trim()}>Save note</Button>
          </div>
        </form>
        {notes.isError ? (
          <ErrorState message={notes.error.message} onRetry={() => void notes.refetch()} />
        ) : !notes.data?.length ? (
          <p className="text-sm text-muted">No notes yet.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {notes.data.map((n) => (
              <li key={n.id} className="rounded-lg border border-border p-3">
                <div className="mb-1 flex items-center justify-between gap-2 text-xs text-muted">
                  <span><span className="font-semibold text-fg">{n.author_name}</span> · {timeAgo(n.created_at)}</span>
                  {n.author_user_id === user?.id && (
                    <button type="button" onClick={() => remove.mutate(n.id)} aria-label="Delete note" className="hover:text-danger">
                      <Trash2 className="size-3.5" aria-hidden />
                    </button>
                  )}
                </div>
                <p className="whitespace-pre-line text-sm text-fg">{n.body}</p>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}

export function CandidateDetailPage() {
  const { candidateId = "" } = useParams();
  const { user } = useAuth();
  const toast = useToast();
  const candidate = useCandidate(candidateId);
  const resumes = useCandidateResumes(candidateId);

  if (candidate.isLoading) return <FullPageSpinner label="Loading profile" />;
  if (candidate.isError || !candidate.data) return <ErrorState message={candidate.error?.message ?? "Candidate not found"} onRetry={() => void candidate.refetch()} />;
  const c = candidate.data;
  const links = [
    { href: c.linkedin_url, label: "LinkedIn" },
    { href: c.github_url, label: "GitHub" },
    { href: c.portfolio_url, label: "Portfolio" },
  ].filter((l) => l.href);

  async function download(documentId: string) {
    try {
      await openDocument(documentId);
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardBody className="flex flex-wrap items-start gap-4">
          <Avatar name={c.name} src={c.avatar_url} size="lg" />
          <div className="min-w-0 flex-1">
            <h1 className="font-display text-2xl font-semibold text-fg">{c.name}</h1>
            <p className="text-sm text-muted">{c.title || "No headline yet"}</p>
            <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
              <span className="inline-flex items-center gap-1"><MapPin className="size-3.5" aria-hidden />{c.location || "Location not set"}</span>
              <span>{experienceLabel(c.experience_years)} experience</span>
              <span>{c.remote_preference}</span>
              {c.notice_period_days != null && <span>{c.notice_period_days} days notice</span>}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge tone="success">{AVAILABILITY_LABEL[c.availability] ?? c.availability}</Badge>
              {c.source === "recruiter" && <Badge>Added by your team</Badge>}
            </div>
          </div>
          <div className="flex min-w-56 flex-col gap-1.5 text-sm">
            {c.contact_visible ? (
              <>
                {c.email && <a href={`mailto:${c.email}`} className="inline-flex items-center gap-2 text-fg hover:text-primary"><Mail className="size-4 text-muted" aria-hidden />{c.email}</a>}
                {c.phone && <span className="inline-flex items-center gap-2 text-fg"><Phone className="size-4 text-muted" aria-hidden />{c.phone}</span>}
              </>
            ) : (
              <p className="inline-flex items-start gap-2 text-xs text-muted">
                <Lock className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                Contact details are shared once this person applies to one of your jobs.
              </p>
            )}
            {links.map((l) => (
              <a key={l.label} href={l.href} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-2 text-primary hover:underline">
                <ExternalLink className="size-3.5" aria-hidden />{l.label}
              </a>
            ))}
          </div>
        </CardBody>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Section title="About">
            {c.bio ? <p className="whitespace-pre-line text-sm text-fg">{c.bio}</p> : <p className="text-sm text-muted">No summary yet.</p>}
            <div className="mt-4 flex flex-wrap gap-1.5">{c.skills.map((s) => <Badge key={s} tone="primary">{s}</Badge>)}</div>
          </Section>

          <Section title="Experience">
            {c.work_experience.length === 0 ? (
              <p className="text-sm text-muted">No experience added.</p>
            ) : (
              <ol className="flex flex-col gap-4">
                {c.work_experience.map((w, i) => (
                  <li key={`${w.company_name}-${i}`} className="border-l-2 border-border pl-4">
                    <p className="font-semibold text-fg">{w.job_title}</p>
                    <p className="text-sm text-muted">{w.company_name}{w.location ? ` · ${w.location}` : ""}</p>
                    <p className="text-xs text-muted">{w.start_date || "?"} – {w.is_current ? "Present" : w.end_date || "?"}</p>
                    {w.description && <p className="mt-1 text-sm text-fg">{w.description}</p>}
                    {(w.achievements ?? []).length > 0 && (
                      <ul className="mt-1 list-disc pl-5 text-sm text-fg">{(w.achievements ?? []).map((a) => <li key={a}>{a}</li>)}</ul>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </Section>

          {c.projects.length > 0 && (
            <Section title="Projects">
              <ul className="flex flex-col gap-3">
                {c.projects.map((p) => (
                  <li key={p.title}>
                    <p className="font-semibold text-fg">{p.title}</p>
                    {p.description && <p className="text-sm text-muted">{p.description}</p>}
                    <div className="mt-1 flex flex-wrap gap-1.5">{(p.tech_stack ?? []).map((t) => <Badge key={t}>{t}</Badge>)}</div>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {isOrgMember(user) && <NotesPanel candidateId={c.id} />}
        </div>

        <div className="flex flex-col gap-6">
          <Section title="Preferences">
            <dl className="grid gap-3 text-sm">
              <div><dt className="text-xs text-muted">Expected salary</dt><dd className="text-fg">{formatSalaryRange(c.expected_salary, null)}</dd></div>
              <div><dt className="text-xs text-muted">Preferred locations</dt><dd className="text-fg">{c.preferred_locations.join(", ") || "Not specified"}</dd></div>
              <div><dt className="text-xs text-muted">Employment types</dt><dd className="text-fg">{c.employment_types.join(", ") || "Not specified"}</dd></div>
              {c.available_from && <div><dt className="text-xs text-muted">Available from</dt><dd className="text-fg">{formatDate(c.available_from)}</dd></div>}
            </dl>
          </Section>

          <Section title="Resumes">
            {resumes.isError ? (
              <p className="text-sm text-muted">Resumes aren't available.</p>
            ) : !resumes.data?.length ? (
              <EmptyState icon={<FileText className="size-5" aria-hidden />} title="No resume uploaded" />
            ) : (
              <ul className="flex flex-col gap-2">
                {resumes.data.map((r) => (
                  <li key={r.id} className="flex items-center justify-between gap-2 text-sm">
                    <span className="min-w-0">
                      <span className="block truncate text-fg">{r.original_filename}</span>
                      <span className="text-xs text-muted">{formatDate(r.created_at)}</span>
                    </span>
                    {r.document_id && c.contact_visible && (
                      <Button size="sm" variant="ghost" icon={<Download className="size-4" aria-hidden />} onClick={() => void download(r.document_id as string)}>
                        Download
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Education">
            {c.education_records.length === 0 ? (
              <p className="text-sm text-muted">{c.education || "Not added"}</p>
            ) : (
              <ul className="flex flex-col gap-2 text-sm">
                {c.education_records.map((e) => (
                  <li key={`${e.institution}-${e.degree}`}>
                    <p className="font-semibold text-fg">{e.degree}{e.field_of_study ? `, ${e.field_of_study}` : ""}</p>
                    <p className="text-muted">{e.institution}{e.graduation_year ? ` · ${e.graduation_year}` : ""}</p>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          {(c.certifications.length > 0 || c.languages.length > 0) && (
            <Section title="Certifications and languages">
              <ul className="flex flex-col gap-2 text-sm">
                {c.certifications.map((cert) => (
                  <li key={cert.name} className="flex items-start gap-2"><Award className="mt-0.5 size-4 text-muted" aria-hidden />
                    <span><span className="text-fg">{cert.name}</span>{cert.issuer && <span className="text-muted"> · {cert.issuer}</span>}</span>
                  </li>
                ))}
                {c.languages.map((l) => (
                  <li key={l.language} className="flex items-center gap-2"><Languages className="size-4 text-muted" aria-hidden />
                    <span className="text-fg">{l.language}</span><span className="text-muted">({l.proficiency})</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </div>
      </div>
    </div>
  );
}
