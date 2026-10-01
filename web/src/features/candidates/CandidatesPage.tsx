import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { MapPin, Plus, Search } from "lucide-react";
import {
  Alert, Avatar, Badge, Button, Card, EmptyState, ErrorState, Input, Modal, PageHeader, Select, Skeleton, TagInput, cn, useToast,
} from "@/components/ui";
import { experienceLabel } from "@/lib/format";
import { AVAILABILITY_LABEL, useAddCandidate, useCandidates, type CandidateFilters } from "./api";

const AVAILABILITY_OPTIONS = [
  { value: "", label: "Any availability" },
  { value: "open", label: "Open to opportunities" },
  { value: "passive", label: "Open to the right role" },
  { value: "not_looking", label: "Not looking" },
];
const WORK_MODE_OPTIONS = [
  { value: "", label: "Any work mode" },
  { value: "Remote", label: "Remote" },
  { value: "Hybrid", label: "Hybrid" },
  { value: "Onsite", label: "Onsite" },
];
const EXPERIENCE_OPTIONS = [
  { value: "", label: "Any experience" },
  { value: "2", label: "2+ years" },
  { value: "5", label: "5+ years" },
  { value: "8", label: "8+ years" },
];
const SORT_OPTIONS = [
  { value: "recent", label: "Recently added" },
  { value: "active", label: "Recently active" },
  { value: "experience", label: "Most experience" },
  { value: "name", label: "Name" },
];

function AddCandidateDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast();
  const navigate = useNavigate();
  const add = useAddCandidate();
  const [form, setForm] = useState({ full_name: "", email: "", title: "", location: "", skills: [] as string[] });

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    try {
      const created = await add.mutateAsync({ ...form, location: form.location || undefined });
      toast.success(`${created.name} added to your talent pool`);
      onClose();
      navigate(`/candidates/${created.id}`);
    } catch {
      // error shown in the dialog
    }
  }

  return (
    <Modal open={open} title="Add a candidate" onClose={onClose}>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <p className="text-sm text-muted">For people who aren't on Talent Match yet. Only your organization can see them.</p>
        {add.isError && <Alert>{add.error.message}</Alert>}
        <Input label="Full name" required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        <Input label="Email" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <Input label="Current role" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <Input label="Location" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
        <TagInput label="Skills" value={form.skills} onChange={(skills) => setForm({ ...form, skills })} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" loading={add.isPending} disabled={!form.full_name || !form.email}>Add candidate</Button>
        </div>
      </form>
    </Modal>
  );
}

export function CandidatesPage() {
  const [filters, setFilters] = useState<CandidateFilters>({ sort: "recent" });
  const [skills, setSkills] = useState<string[]>([]);
  const [adding, setAdding] = useState(false);
  const query = { ...filters, skills };
  const { data, isLoading, isError, error, refetch, isFetching } = useCandidates(query);
  const update = (patch: Partial<CandidateFilters>) => setFilters((f) => ({ ...f, ...patch }));
  const filtered = !!(filters.q || skills.length || filters.location || filters.availability || filters.remote_preference || filters.min_experience);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Candidates"
        description="Your talent pool: people who applied to your jobs, searchable talent and candidates you added."
        actions={<Button icon={<Plus className="size-4" aria-hidden />} onClick={() => setAdding(true)}>Add candidate</Button>}
      />

      <Card className="flex flex-col gap-3 p-4">
        <div className="flex flex-wrap gap-2">
          <label className="relative min-w-56 flex-1">
            <span className="sr-only">Search candidates</span>
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
            <input
              value={filters.q ?? ""}
              onChange={(e) => update({ q: e.target.value || undefined })}
              placeholder="Search candidates"
              className="h-10 w-full rounded-lg border border-border bg-surface pl-9 pr-3 text-sm text-fg placeholder:text-muted focus:border-primary focus:outline-none"
            />
          </label>
          <input
            aria-label="Location"
            value={filters.location ?? ""}
            onChange={(e) => update({ location: e.target.value || undefined })}
            placeholder="Location"
            className="h-10 w-40 rounded-lg border border-border bg-surface px-3 text-sm text-fg placeholder:text-muted focus:border-primary focus:outline-none"
          />
          <Select aria-label="Experience" value={String(filters.min_experience ?? "")} onChange={(e) => update({ min_experience: e.target.value ? Number(e.target.value) : undefined })} options={EXPERIENCE_OPTIONS} className="w-36" />
          <Select aria-label="Availability" value={filters.availability ?? ""} onChange={(e) => update({ availability: e.target.value || undefined })} options={AVAILABILITY_OPTIONS} className="w-48" />
          <Select aria-label="Work mode" value={filters.remote_preference ?? ""} onChange={(e) => update({ remote_preference: e.target.value || undefined })} options={WORK_MODE_OPTIONS} className="w-36" />
          <Select aria-label="Sort by" value={filters.sort} onChange={(e) => update({ sort: e.target.value as CandidateFilters["sort"] })} options={SORT_OPTIONS} className="w-40" />
        </div>
        <TagInput label="Must have skills" value={skills} onChange={setSkills} placeholder="Type a skill and press Enter" />
      </Card>

      {isLoading ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-36" />)}
        </div>
      ) : isError ? (
        <Card><ErrorState message={error.message} onRetry={() => void refetch()} /></Card>
      ) : !data?.length ? (
        <Card>
          <EmptyState
            title={filtered ? "No candidates match these filters" : "No candidates yet"}
            description={filtered ? "Try removing a filter or a required skill." : "Candidates appear here when they apply or when you add them."}
          />
        </Card>
      ) : (
        <ul className={cn("grid gap-3 md:grid-cols-2 xl:grid-cols-3 transition-opacity", isFetching && "opacity-60")}>
          {data.map((c) => (
            <li key={c.id}>
              <Link to={`/candidates/${c.id}`} className="flex h-full flex-col gap-3 rounded-xl border border-border bg-surface p-4 shadow-card hover:border-primary">
                <div className="flex items-start gap-3">
                  <Avatar name={c.name} src={c.avatar_url} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-semibold text-fg">{c.name}</p>
                    <p className="truncate text-sm text-muted">{c.title || "No headline yet"}</p>
                  </div>
                  {c.source === "recruiter" && <Badge>Added by your team</Badge>}
                </div>
                <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                  <span className="inline-flex items-center gap-1"><MapPin className="size-3" aria-hidden />{c.location || "Location not set"}</span>
                  <span>{experienceLabel(c.experience_years)}</span>
                  <span>{c.remote_preference}</span>
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {c.skills.slice(0, 5).map((s) => <Badge key={s} tone="primary">{s}</Badge>)}
                  {c.skills.length > 5 && <Badge>+{c.skills.length - 5}</Badge>}
                </div>
                <p className="mt-auto text-xs text-muted">{AVAILABILITY_LABEL[c.availability] ?? c.availability}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}

      <AddCandidateDialog open={adding} onClose={() => setAdding(false)} />
    </div>
  );
}
