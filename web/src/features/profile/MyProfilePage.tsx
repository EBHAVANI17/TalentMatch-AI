import { useEffect, useState, type ReactNode } from "react";
import { Plus, Trash2 } from "lucide-react";
import {
  Alert, Button, Card, CardBody, CardHeader, ErrorState, FullPageSpinner, Input, PageHeader, Select, TagInput, Textarea, useToast,
} from "@/components/ui";
import { useMyProfile, useUpdateMyProfile } from "@/features/candidates/api";
import type { CandidateDetail, CandidateUpdate } from "@/lib/api/types";

type Experience = NonNullable<CandidateDetail["work_experience"]>[number];
type Education = NonNullable<CandidateDetail["education_records"]>[number];
type Certification = NonNullable<CandidateDetail["certifications"]>[number];
type Language = NonNullable<CandidateDetail["languages"]>[number];

const NEW_EXPERIENCE: Experience = { company_name: "", job_title: "", location: "", start_date: "", end_date: "", is_current: false, description: "", achievements: [] };
const NEW_EDUCATION: Education = { institution: "", degree: "", field_of_study: "", graduation_year: null, gpa: "" };
const NEW_CERTIFICATION: Certification = { name: "", issuer: "", issued_on: "", expires_on: "", credential_url: "" };
const NEW_LANGUAGE: Language = { language: "", proficiency: "professional" };

function ListSection<T>({ title, description, items, onChange, blank, render, addLabel }: {
  title: string; description?: string; items: T[]; onChange: (items: T[]) => void; blank: T;
  render: (item: T, update: (patch: Partial<T>) => void) => ReactNode; addLabel: string;
}) {
  return (
    <Card>
      <CardHeader
        title={title}
        description={description}
        actions={<Button size="sm" variant="secondary" icon={<Plus className="size-4" aria-hidden />} onClick={() => onChange([...items, { ...blank }])}>{addLabel}</Button>}
      />
      <CardBody className="flex flex-col gap-4">
        {items.length === 0 && <p className="text-sm text-muted">Nothing added yet.</p>}
        {items.map((item, i) => (
          <div key={i} className="relative rounded-lg border border-border p-4">
            <button
              type="button"
              onClick={() => onChange(items.filter((_, j) => j !== i))}
              className="absolute right-3 top-3 text-muted hover:text-danger"
              aria-label={`Remove ${title.toLowerCase()} entry ${i + 1}`}
            >
              <Trash2 className="size-4" aria-hidden />
            </button>
            {render(item, (patch) => onChange(items.map((it, j) => (j === i ? { ...it, ...patch } : it))))}
          </div>
        ))}
      </CardBody>
    </Card>
  );
}

function StrengthMeter({ value }: { value: number }) {
  const tone = value >= 80 ? "bg-success" : value >= 50 ? "bg-primary" : "bg-warning";
  return (
    <div className="min-w-56">
      <div className="mb-1 flex justify-between text-xs text-muted">
        <span>Profile strength</span>
        <span className="font-semibold text-fg">{value}%</span>
      </div>
      <div className="h-2 rounded-full bg-primary-soft" role="meter" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100} aria-label="Profile strength">
        <div className={`h-2 rounded-full ${tone}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

export function MyProfilePage() {
  const toast = useToast();
  const profile = useMyProfile();
  const save = useUpdateMyProfile();
  const [form, setForm] = useState<CandidateDetail | null>(null);

  useEffect(() => {
    if (profile.data) setForm(profile.data);
  }, [profile.data]);

  if (profile.isLoading || (!form && !profile.isError)) return <FullPageSpinner label="Loading your profile" />;
  if (profile.isError || !form) return <ErrorState message={profile.error?.message} onRetry={() => void profile.refetch()} />;

  const set = (patch: Partial<CandidateDetail>) => setForm((f) => (f ? { ...f, ...patch } : f));
  const text = (key: keyof CandidateDetail) => ({
    value: (form[key] as string | null | undefined) ?? "",
    onChange: (e: { target: { value: string } }) => set({ [key]: e.target.value } as Partial<CandidateDetail>),
  });

  async function onSave() {
    if (!form) return;
    const payload: CandidateUpdate = {
      full_name: form.name, title: form.title, bio: form.bio, phone: form.phone, location: form.location,
      skills: form.skills, experience_years: Number(form.experience_years) || 0, expected_salary: Number(form.expected_salary) || 0,
      notice_period_days: form.notice_period_days === null || form.notice_period_days === undefined || String(form.notice_period_days) === "" ? null : Number(form.notice_period_days),
      availability: form.availability as CandidateUpdate["availability"], remote_preference: form.remote_preference,
      preferred_locations: form.preferred_locations, employment_types: form.employment_types, is_searchable: form.is_searchable,
      industry: form.industry, education: form.education,
      linkedin_url: form.linkedin_url, github_url: form.github_url, portfolio_url: form.portfolio_url,
      work_experience: (form.work_experience ?? []).filter((w) => w.company_name && w.job_title),
      education_records: (form.education_records ?? []).filter((e) => e.institution && e.degree),
      certifications: (form.certifications ?? []).filter((c) => c.name),
      languages: (form.languages ?? []).filter((l) => l.language),
    };
    try {
      await save.mutateAsync(payload);
      toast.success("Profile saved");
    } catch (err) {
      toast.error((err as Error).message);
    }
  }

  return (
    <div className="flex flex-col gap-6 pb-20">
      <PageHeader
        title="My profile"
        description="Recruiters see this profile when it matches their jobs. Contact details are only shared with companies you apply to."
        actions={<StrengthMeter value={form.profile_strength} />}
      />
      {save.isError && <Alert>{save.error.message}</Alert>}

      <Card>
        <CardHeader title="Basics" />
        <CardBody className="grid gap-4 md:grid-cols-2">
          <Input label="Full name" {...text("name")} />
          <Input label="Professional headline" placeholder="e.g. Senior Backend Engineer" {...text("title")} />
          <Input label="Phone" type="tel" {...text("phone")} />
          <Input label="Location" placeholder="City, country" {...text("location")} />
          <div className="md:col-span-2">
            <Textarea label="Summary" rows={4} hint="A few sentences about what you do and what you're looking for." {...text("bio")} />
          </div>
          <Input label="Years of experience" type="number" min={0} step={0.5} value={String(form.experience_years ?? "")} onChange={(e) => set({ experience_years: e.target.value as unknown as number })} />
          <Input label="Industry" {...text("industry")} />
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Skills" description="Add the skills you'd want to be matched on." />
        <CardBody>
          <TagInput label="Skills" value={form.skills} onChange={(skills) => set({ skills })} placeholder="Type a skill and press Enter" />
        </CardBody>
      </Card>

      <ListSection
        title="Experience" addLabel="Add role" items={form.work_experience ?? []} blank={NEW_EXPERIENCE}
        onChange={(work_experience) => set({ work_experience })}
        render={(w, update) => (
          <div className="grid gap-3 md:grid-cols-2">
            <Input label="Job title" value={w.job_title} onChange={(e) => update({ job_title: e.target.value })} />
            <Input label="Company" value={w.company_name} onChange={(e) => update({ company_name: e.target.value })} />
            <Input label="Start (YYYY-MM)" placeholder="2021-04" value={w.start_date ?? ""} onChange={(e) => update({ start_date: e.target.value })} />
            <Input label="End (YYYY-MM)" placeholder="2023-08" disabled={w.is_current} value={w.is_current ? "" : w.end_date ?? ""} onChange={(e) => update({ end_date: e.target.value })} />
            <label className="flex items-center gap-2 text-sm text-fg md:col-span-2">
              <input type="checkbox" checked={!!w.is_current} onChange={(e) => update({ is_current: e.target.checked })} /> I currently work here
            </label>
            <div className="md:col-span-2">
              <Textarea label="What you did" rows={3} value={w.description ?? ""} onChange={(e) => update({ description: e.target.value })} />
            </div>
          </div>
        )}
      />

      <ListSection
        title="Education" addLabel="Add education" items={form.education_records ?? []} blank={NEW_EDUCATION}
        onChange={(education_records) => set({ education_records })}
        render={(e, update) => (
          <div className="grid gap-3 md:grid-cols-2">
            <Input label="Institution" value={e.institution} onChange={(ev) => update({ institution: ev.target.value })} />
            <Input label="Degree" value={e.degree} onChange={(ev) => update({ degree: ev.target.value })} />
            <Input label="Field of study" value={e.field_of_study ?? ""} onChange={(ev) => update({ field_of_study: ev.target.value })} />
            <Input label="Graduation year" type="number" value={e.graduation_year ? String(e.graduation_year) : ""} onChange={(ev) => update({ graduation_year: ev.target.value ? Number(ev.target.value) : null })} />
          </div>
        )}
      />

      <ListSection
        title="Certifications" addLabel="Add certification" items={form.certifications ?? []} blank={NEW_CERTIFICATION}
        onChange={(certifications) => set({ certifications })}
        render={(c, update) => (
          <div className="grid gap-3 md:grid-cols-3">
            <Input label="Name" value={c.name} onChange={(e) => update({ name: e.target.value })} />
            <Input label="Issuer" value={c.issuer ?? ""} onChange={(e) => update({ issuer: e.target.value })} />
            <Input label="Issued (YYYY-MM)" value={c.issued_on ?? ""} onChange={(e) => update({ issued_on: e.target.value })} />
          </div>
        )}
      />

      <ListSection
        title="Languages" addLabel="Add language" items={form.languages ?? []} blank={NEW_LANGUAGE}
        onChange={(languages) => set({ languages })}
        render={(l, update) => (
          <div className="grid gap-3 md:grid-cols-2">
            <Input label="Language" value={l.language} onChange={(e) => update({ language: e.target.value })} />
            <Select
              label="Proficiency" value={l.proficiency ?? "professional"}
              onChange={(e) => update({ proficiency: e.target.value as Language["proficiency"] })}
              options={["basic", "conversational", "professional", "native"].map((v) => ({ value: v, label: v[0].toUpperCase() + v.slice(1) }))}
            />
          </div>
        )}
      />

      <Card>
        <CardHeader title="Job preferences" />
        <CardBody className="grid gap-4 md:grid-cols-2">
          <Select
            label="Availability" value={form.availability} onChange={(e) => set({ availability: e.target.value })}
            options={[{ value: "open", label: "Open to opportunities" }, { value: "passive", label: "Open to the right role" }, { value: "not_looking", label: "Not looking" }]}
          />
          <Select
            label="Work mode" value={form.remote_preference} onChange={(e) => set({ remote_preference: e.target.value })}
            options={["Remote", "Hybrid", "Onsite", "Flexible"].map((v) => ({ value: v, label: v }))}
          />
          <Input label="Expected salary" type="number" min={0} value={String(form.expected_salary ?? "")} onChange={(e) => set({ expected_salary: e.target.value as unknown as number })} />
          <Input label="Notice period (days)" type="number" min={0} max={365} value={form.notice_period_days == null ? "" : String(form.notice_period_days)} onChange={(e) => set({ notice_period_days: e.target.value as unknown as number })} />
          <TagInput label="Preferred locations" value={form.preferred_locations} onChange={(preferred_locations) => set({ preferred_locations })} placeholder="City, or Remote" />
          <TagInput label="Employment types" value={form.employment_types ?? []} onChange={(employment_types) => set({ employment_types })} placeholder="Full-time, Contract" />
          <label className="flex items-start gap-2 text-sm text-fg md:col-span-2">
            <input type="checkbox" className="mt-1" checked={!!form.is_searchable} onChange={(e) => set({ is_searchable: e.target.checked })} />
            <span>Let recruiters find my profile in search.<span className="block text-xs text-muted">Turn off to be visible only to companies you apply to.</span></span>
          </label>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Links" />
        <CardBody className="grid gap-4 md:grid-cols-3">
          <Input label="LinkedIn" type="url" {...text("linkedin_url")} />
          <Input label="GitHub" type="url" {...text("github_url")} />
          <Input label="Portfolio" type="url" {...text("portfolio_url")} />
        </CardBody>
      </Card>

      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-border bg-surface/95 px-4 py-3 backdrop-blur lg:left-60">
        <div className="mx-auto flex max-w-6xl justify-end">
          <Button loading={save.isPending} onClick={() => void onSave()}>Save profile</Button>
        </div>
      </div>
    </div>
  );
}
