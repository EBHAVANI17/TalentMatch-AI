import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Alert, Button, Card, CardBody, CardHeader, ErrorState, FullPageSpinner, Input, PageHeader, Select, TagInput, Textarea, useToast } from "@/components/ui";
import { JobDraftAssistant } from "@/features/ai/JobDraftAssistant";
import type { Job, JobCreate } from "@/lib/api/types";
import { useCreateJob, useJob, useUpdateJob } from "./api";

interface FormState {
  title: string;
  department: string;
  description: string;
  responsibilities: string;
  required_skills: string[];
  preferred_skills: string[];
  min_experience_years: string;
  max_experience_years: string;
  required_education: string;
  location: string;
  workplace_type: string;
  employment_type: string;
  openings: string;
  salary_min: string;
  salary_max: string;
  application_deadline: string;
  seniority: string;
  industry: string;
  screening_questions: string;
  interview_criteria: string;
}

const EMPTY: FormState = {
  title: "", department: "Engineering", description: "", responsibilities: "",
  required_skills: [], preferred_skills: [], min_experience_years: "3", max_experience_years: "",
  required_education: "Bachelor's", location: "", workplace_type: "Remote", employment_type: "Full-time",
  openings: "1", salary_min: "", salary_max: "", application_deadline: "", seniority: "", industry: "",
  screening_questions: "", interview_criteria: "",
};

const EDUCATION_OPTIONS = ["Self-taught", "Bachelor's", "Master's", "PhD"];
const normalizeEducation = (value?: string | null) =>
  EDUCATION_OPTIONS.find((o) => value && value.toLowerCase().startsWith(o.toLowerCase().slice(0, 4))) ?? "Bachelor's";
const lines = (items?: string[] | null) => (items ?? []).join("\n");

function fromJob(job: Job): FormState {
  return {
    title: job.title, department: job.department, description: job.description,
    responsibilities: (job.key_responsibilities ?? []).join("\n"),
    required_skills: job.required_skills ?? [], preferred_skills: job.preferred_skills ?? [],
    min_experience_years: String(job.min_experience_years ?? ""), max_experience_years: job.max_experience_years != null ? String(job.max_experience_years) : "",
    required_education: job.required_education, location: job.location, workplace_type: job.workplace_type,
    employment_type: job.employment_type, openings: String(job.openings ?? 1),
    salary_min: job.salary_min ? String(job.salary_min) : "", salary_max: job.salary_max ? String(job.salary_max) : "",
    application_deadline: job.application_deadline ? job.application_deadline.slice(0, 10) : "",
    seniority: job.seniority ?? "", industry: job.industry ?? "",
    screening_questions: lines(job.screening_questions), interview_criteria: lines(job.interview_criteria),
  };
}

function toPayload(f: FormState) {
  const num = (v: string) => (v.trim() === "" ? undefined : Number(v));
  return {
    title: f.title.trim(),
    department: f.department.trim() || "General",
    description: f.description.trim(),
    key_responsibilities: f.responsibilities.split("\n").map((l) => l.trim()).filter(Boolean),
    required_skills: f.required_skills,
    preferred_skills: f.preferred_skills,
    min_experience_years: num(f.min_experience_years) ?? 0,
    max_experience_years: num(f.max_experience_years) ?? null,
    required_education: f.required_education,
    location: f.location.trim() || "Remote",
    workplace_type: f.workplace_type,
    employment_type: f.employment_type as JobCreate["employment_type"],
    openings: num(f.openings) ?? 1,
    salary_min: num(f.salary_min) ?? 0,
    salary_max: num(f.salary_max) ?? 0,
    application_deadline: f.application_deadline ? `${f.application_deadline}T23:59:59` : null,
    seniority: f.seniority,
    industry: f.industry,
    screening_questions: f.screening_questions.split("\n").map((l) => l.trim()).filter(Boolean),
    interview_criteria: f.interview_criteria.split("\n").map((l) => l.trim()).filter(Boolean),
  };
}

function validate(f: FormState): string | null {
  if (f.title.trim().length < 2) return "Give the job a title.";
  if (!f.description.trim()) return "Add a job description.";
  const min = Number(f.salary_min || 0), max = Number(f.salary_max || 0);
  if (min && max && min > max) return "Minimum salary can't be higher than the maximum.";
  if (f.max_experience_years && Number(f.min_experience_years) > Number(f.max_experience_years)) return "Minimum experience can't be higher than the maximum.";
  return null;
}

export function JobFormPage() {
  const { jobId } = useParams();
  const editing = !!jobId;
  const navigate = useNavigate();
  const toast = useToast();
  const existing = useJob(jobId);
  const create = useCreateJob();
  const update = useUpdateJob(jobId ?? "");
  const [form, setForm] = useState<FormState>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState<"draft" | "publish" | "save" | null>(null);

  useEffect(() => {
    if (existing.data) setForm(fromJob(existing.data));
  }, [existing.data]);

  const set = <K extends keyof FormState>(key: K) => (value: FormState[K]) => setForm((f) => ({ ...f, [key]: value }));
  const field = (key: keyof FormState) => ({
    value: form[key] as string,
    onChange: (e: { target: { value: string } }) => set(key)(e.target.value as never),
  });

  async function submit(publish: boolean) {
    const problem = validate(form);
    if (problem) return setError(problem);
    setError(null);
    setSubmitting(editing ? "save" : publish ? "publish" : "draft");
    try {
      const job = editing
        ? await update.mutateAsync(toPayload(form))
        : await create.mutateAsync({ ...toPayload(form), status: publish ? "Active" : "Draft" } as JobCreate);
      toast.success(editing ? "Job updated" : publish ? "Job published" : "Draft saved");
      navigate(`/jobs/${job.id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(null);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void submit(true);
  }

  if (editing && existing.isLoading) return <FullPageSpinner label="Loading job" />;
  if (editing && existing.isError) return <ErrorState message={existing.error.message} onRetry={() => void existing.refetch()} />;
  const busy = submitting !== null;

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-6" noValidate>
      <PageHeader title={editing ? "Edit job" : "Create job"} description={editing ? existing.data?.title : "Describe the role. You can save it as a draft and publish later."} />
      {error && <Alert>{error}</Alert>}

      {!editing && (
        <JobDraftAssistant
          onDraft={(d) => setForm((f) => ({
            ...f,
            title: d.title || f.title, department: d.department || f.department, description: d.description || f.description,
            responsibilities: lines(d.responsibilities) || f.responsibilities,
            required_skills: d.required_skills?.length ? d.required_skills : f.required_skills,
            preferred_skills: d.preferred_skills?.length ? d.preferred_skills : f.preferred_skills,
            min_experience_years: String(d.min_experience_years ?? f.min_experience_years),
            max_experience_years: d.max_experience_years != null ? String(d.max_experience_years) : f.max_experience_years,
            required_education: normalizeEducation(d.required_education), location: d.location || f.location,
            workplace_type: d.workplace_type || f.workplace_type, employment_type: d.employment_type || f.employment_type,
            salary_min: d.salary_min ? String(d.salary_min) : f.salary_min, salary_max: d.salary_max ? String(d.salary_max) : f.salary_max,
            seniority: d.seniority || f.seniority,
            screening_questions: lines(d.screening_questions) || f.screening_questions,
            interview_criteria: lines(d.interview_criteria) || f.interview_criteria,
          }))}
          onAnalysis={(a, text) => setForm((f) => ({
            ...f,
            title: f.title || a.title || "", description: f.description || text,
            responsibilities: f.responsibilities || lines(a.responsibilities),
            required_skills: a.required_skills?.length ? a.required_skills : f.required_skills,
            preferred_skills: a.preferred_skills?.length ? a.preferred_skills : f.preferred_skills,
            min_experience_years: a.min_experience_years != null ? String(a.min_experience_years) : f.min_experience_years,
            max_experience_years: a.max_experience_years != null ? String(a.max_experience_years) : f.max_experience_years,
            required_education: a.required_education ? normalizeEducation(a.required_education) : f.required_education,
            location: a.location || f.location, workplace_type: a.workplace_type || f.workplace_type,
            employment_type: a.employment_type || f.employment_type,
            salary_min: a.salary_min ? String(a.salary_min) : f.salary_min, salary_max: a.salary_max ? String(a.salary_max) : f.salary_max,
            seniority: a.seniority || f.seniority, industry: a.industry || f.industry,
          }))}
        />
      )}

      <Card>
        <CardHeader title="Role" />
        <CardBody className="grid gap-4 md:grid-cols-2">
          <Input label="Job title" required {...field("title")} />
          <Input label="Department" {...field("department")} />
          <div className="md:col-span-2">
            <Textarea label="Description" rows={6} required {...field("description")} />
          </div>
          <div className="md:col-span-2">
            <Textarea label="Responsibilities" hint="One per line" rows={4} {...field("responsibilities")} />
          </div>
          <Select label="Employment type" {...field("employment_type")} options={["Full-time", "Part-time", "Contract", "Internship", "Temporary"].map((v) => ({ value: v, label: v }))} />
          <Input label="Number of openings" type="number" min={1} {...field("openings")} />
          <Input label="Seniority" placeholder="e.g. Senior, Staff" {...field("seniority")} />
          <Input label="Industry" placeholder="e.g. Fintech" {...field("industry")} />
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Requirements" description="Used by the matching engine. Be specific; required skills weigh more than preferred ones." />
        <CardBody className="grid gap-4 md:grid-cols-2">
          <TagInput label="Required skills" hint="Press Enter after each skill" value={form.required_skills} onChange={set("required_skills")} placeholder="e.g. Python" />
          <TagInput label="Preferred skills" value={form.preferred_skills} onChange={set("preferred_skills")} placeholder="e.g. Terraform" />
          <Input label="Minimum experience (years)" type="number" min={0} step={0.5} {...field("min_experience_years")} />
          <Input label="Maximum experience (years)" type="number" min={0} step={0.5} hint="Optional" {...field("max_experience_years")} />
          <Select label="Education" {...field("required_education")} options={EDUCATION_OPTIONS.map((v) => ({ value: v, label: v }))} />
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Location and compensation" />
        <CardBody className="grid gap-4 md:grid-cols-2">
          <Input label="Location" placeholder="e.g. Bangalore, India" {...field("location")} />
          <Select label="Work mode" {...field("workplace_type")} options={["Remote", "Hybrid", "Onsite"].map((v) => ({ value: v, label: v }))} />
          <Input label="Salary from" type="number" min={0} {...field("salary_min")} />
          <Input label="Salary to" type="number" min={0} {...field("salary_max")} />
          <Input label="Application deadline" type="date" hint="Optional" {...field("application_deadline")} />
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Screening and interviews" description="Used by your team to screen applicants consistently." />
        <CardBody className="grid gap-4 md:grid-cols-2">
          <Textarea label="Screening questions" hint="One per line" rows={4} {...field("screening_questions")} />
          <Textarea label="Interview criteria" hint="One per line" rows={4} {...field("interview_criteria")} />
        </CardBody>
      </Card>

      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="secondary" onClick={() => navigate(editing ? `/jobs/${jobId}` : "/jobs")} disabled={busy}>
          Cancel
        </Button>
        {editing ? (
          <Button type="submit" loading={submitting === "save"}>Save changes</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={() => void submit(false)} loading={submitting === "draft"} disabled={busy}>
              Save as draft
            </Button>
            <Button type="submit" loading={submitting === "publish"} disabled={busy}>Publish job</Button>
          </>
        )}
      </div>
    </form>
  );
}
