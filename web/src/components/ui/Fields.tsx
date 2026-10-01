import { forwardRef, useId, useState, type KeyboardEvent, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { X } from "lucide-react";
import { cn } from "./cn";

const CONTROL = "rounded-lg border border-border bg-surface px-3 text-sm text-fg placeholder:text-muted focus:border-primary focus:outline-none";

function FieldShell({ id, label, hint, error, children }: { id: string; label: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-fg">
        {label}
      </label>
      {children}
      {error ? <p className="text-xs text-danger">{error}</p> : hint ? <p className="text-xs text-muted">{hint}</p> : null}
    </div>
  );
}

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  hint?: string;
  error?: string;
  options: ReadonlyArray<{ value: string; label: string }>;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select({ label, hint, error, options, className, id, ...rest }, ref) {
  const autoId = useId();
  const selectId = id ?? autoId;
  const control = (
    <select ref={ref} id={selectId} aria-label={label ? undefined : rest["aria-label"]} className={cn(CONTROL, "h-10", className)} {...rest}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
  return label ? (
    <FieldShell id={selectId} label={label} hint={hint} error={error}>
      {control}
    </FieldShell>
  ) : (
    control
  );
});

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
  hint?: string;
  error?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea({ label, hint, error, className, id, rows = 4, ...rest }, ref) {
  const autoId = useId();
  const textareaId = id ?? autoId;
  return (
    <FieldShell id={textareaId} label={label} hint={hint} error={error}>
      <textarea ref={ref} id={textareaId} rows={rows} className={cn(CONTROL, "py-2", className)} {...rest} />
    </FieldShell>
  );
});

/** Free-text tags (skills, locations). Enter or comma adds; Backspace on empty input removes the last one. */
export function TagInput({ label, hint, value, onChange, placeholder }: { label: string; hint?: string; value: string[]; onChange: (next: string[]) => void; placeholder?: string }) {
  const id = useId();
  const [draft, setDraft] = useState("");

  function add(raw: string) {
    const tag = raw.trim().replace(/,$/, "").trim();
    if (tag && !value.some((v) => v.toLowerCase() === tag.toLowerCase())) onChange([...value, tag]);
    setDraft("");
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add(draft);
    } else if (e.key === "Backspace" && !draft && value.length) {
      onChange(value.slice(0, -1));
    }
  }

  return (
    <FieldShell id={id} label={label} hint={hint}>
      <div className={cn(CONTROL, "flex min-h-10 flex-wrap items-center gap-1.5 py-1.5")}>
        {value.map((tag) => (
          <span key={tag} className="nowrap inline-flex items-center gap-1 rounded-md bg-primary-soft px-2 py-0.5 text-xs font-medium text-primary">
            {tag}
            <button type="button" onClick={() => onChange(value.filter((v) => v !== tag))} aria-label={`Remove ${tag}`} className="hover:text-fg">
              <X className="size-3" aria-hidden />
            </button>
          </span>
        ))}
        <input
          id={id}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          onBlur={() => draft && add(draft)}
          placeholder={value.length ? "" : placeholder}
          className="min-w-24 flex-1 bg-transparent text-sm outline-none placeholder:text-muted"
        />
      </div>
    </FieldShell>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="font-display text-2xl font-semibold text-fg">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
