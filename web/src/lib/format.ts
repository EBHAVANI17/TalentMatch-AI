const number = new Intl.NumberFormat();
const compact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });

export const formatNumber = (n: number | null | undefined) => (n === null || n === undefined ? "–" : number.format(n));

/** Salaries are stored without a currency; show them as grouped numbers. */
export function formatSalaryRange(min?: number | null, max?: number | null) {
  if (!min && !max) return "Not specified";
  if (min && max) return `${compact.format(min)} – ${compact.format(max)}`;
  return compact.format((min || max) as number);
}

export function formatDate(value?: string | null) {
  if (!value) return "";
  return new Date(value).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function timeAgo(value?: string | null) {
  if (!value) return "";
  const seconds = Math.round((Date.now() - new Date(value).getTime()) / 1000);
  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["year", 31536000], ["month", 2592000], ["week", 604800], ["day", 86400], ["hour", 3600], ["minute", 60],
  ];
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return rtf.format(-Math.round(seconds / size), unit);
  }
  return "just now";
}

export const experienceLabel = (years?: number | null) =>
  years === null || years === undefined ? "–" : `${Number.isInteger(years) ? years : years.toFixed(1)} yrs`;
