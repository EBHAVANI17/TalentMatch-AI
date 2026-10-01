import { useState } from "react";
import { cn } from "./cn";

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("") || "?";
}

/** Profile photo with an initials fallback (also used when the image fails to load). */
export function Avatar({ name, src, size = "md" }: { name: string; src?: string | null; size?: "sm" | "md" | "lg" }) {
  const [failed, setFailed] = useState(false);
  const dims = { sm: "size-8 text-xs", md: "size-10 text-sm", lg: "size-16 text-lg" }[size];
  if (src && !failed) {
    return <img src={src} alt="" onError={() => setFailed(true)} className={cn("shrink-0 rounded-full object-cover", dims)} />;
  }
  return (
    <span aria-hidden className={cn("flex shrink-0 items-center justify-center rounded-full bg-primary-soft font-bold text-primary", dims)}>
      {initials(name)}
    </span>
  );
}
