import type { ReactNode } from "react";

// Display helpers only: layout primitives and fixed badge styles. No business rules.

export const SCHEDULE = "09:00 · 15:00 · 21:00 IST";

const BADGE: Record<string, string> = {
  "Evidence accumulating": "bg-amber-bg text-amber-ink",
  "Limited history": "bg-amber-bg text-amber-ink",
  "History available": "bg-blue-50 text-brand-ink",
  "No current observation": "bg-stone-100 text-muted",
};

export function Badge({ text }: { text: string }) {
  return (
    <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${BADGE[text] ?? "bg-stone-100 text-muted"}`}>
      {text}
    </span>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-2xl border border-line bg-white p-6 shadow-[0_1px_2px_rgba(16,24,40,0.04)] ${className}`}>{children}</section>;
}

export function Kicker({ children }: { children: ReactNode }) {
  return <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">{children}</p>;
}

export function SectionTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-lg font-semibold tracking-tight text-ink">{title}</h2>
      {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
    </div>
  );
}

export function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}
