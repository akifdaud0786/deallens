import { useState } from "react";
import { CartesianGrid, Legend, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import type { CoveragePolicy, LedgerRow, PageState, PlanRow, ProductView } from "../types/deallens";
import { Badge, Card, Kicker, SCHEDULE, SectionTitle, plural } from "../lib/ui";

// Every value below comes from the API (Python view models). Components only lay it out.

export function TopBar({ state }: { state: PageState | null }) {
  return (
    <header className="border-b border-line bg-white/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-4">
        <div className="flex items-baseline gap-3">
          <span className="text-xl font-bold tracking-tight text-ink">DealLens</span>
          <span className="text-sm text-muted">Commerce Intelligence</span>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
          <span className="rounded-full border border-line px-2.5 py-1">Google Shopping via SerpApi</span>
          <span>Read-only demo</span>
          {state?.as_of && <span>Analysis built {state.as_of} UTC</span>}
        </div>
      </div>
    </header>
  );
}

export function Tagline() {
  return (
    <div className="mb-8">
      <h1 className="max-w-3xl text-3xl font-semibold leading-tight tracking-tight text-ink sm:text-4xl">
        Don't just tell me the cheapest price.
        <span className="block text-brand">Tell me what today's price means.</span>
      </h1>
    </div>
  );
}

export function HeroAndDecision({ v }: { v: ProductView }) {
  const d = v.decision;
  return (
    <div className="grid gap-6 lg:grid-cols-5">
      <Card className="lg:col-span-2">
        <Kicker>{v.identity.brand}</Kicker>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">{v.identity.display_name.replace(` ${v.identity.model_key}`, "")}</h2>
        <p className="mt-1 font-mono text-sm text-muted">{v.identity.model_key}</p>
        <div className="mt-6">
          <p className="text-4xl font-bold tracking-tight sm:text-5xl">{v.hero_price}</p>
          <p className="mt-1 text-sm text-muted">Lowest observed listed price</p>
        </div>
        {v.hero_meta && <p className="mt-4 text-sm text-ink">{v.hero_meta}</p>}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Badge text={d.badge} />
          {v.plan.active_ref && (
            <span className="text-xs text-muted">Active plan: <span className="font-mono">{v.plan.active_ref}</span></span>
          )}
        </div>
      </Card>
      <Card className="lg:col-span-3">
        <Kicker>DealLens decision</Kicker>
        <p className="mt-2 text-lg font-medium text-muted">{d.question}</p>
        <p className="mt-1 text-3xl font-bold tracking-tight">{d.answer}</p>
        <ul className="mt-5 space-y-2">
          {d.checks.map(([ok, text]) => (
            <li key={text} className="flex items-start gap-2 text-sm">
              <span className={`mt-0.5 font-bold ${ok ? "text-brand" : "text-amber-ink"}`}>{ok ? "✓" : "⚠"}</span>
              <span>{text}</span>
            </li>
          ))}
        </ul>
        <div className="mt-5 rounded-xl bg-canvas px-4 py-3">
          <Kicker>DealLens verdict</Kicker>
          <p className="mt-1 text-sm font-medium">{d.verdict}</p>
        </div>
      </Card>
    </div>
  );
}

export function Market({ v }: { v: ProductView }) {
  return (
    <div>
      <SectionTitle title="Today's observed market"
        subtitle={v.plan.is_current ? `Independent sellers (latest run): ${v.kpis.independent_sellers}` : undefined} />
      {!v.plan.is_current || v.no_valid_observations ? (
        <Card><p className="text-sm text-muted">{v.decision.answer} of this product.</p></Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {v.market.map((m) => (
            <Card key={`${m.storefront}-${m.listed_price}`}>
              <p className="font-semibold">{m.storefront}</p>
              <p className="mt-3 text-3xl font-bold tracking-tight">{m.listed_price}</p>
              <p className="text-xs text-muted">Observed listed price</p>
              {m.list_price !== "—" && (
                <p className="mt-3 rounded-lg bg-canvas px-3 py-2 text-xs text-muted">Seller-displayed list price: {m.list_price}</p>
              )}
              <dl className="mt-4 grid grid-cols-2 gap-2 text-xs">
                <div><dt className="text-muted">Delivery</dt><dd className="font-medium">{m.delivery}</dd></div>
                <div><dt className="text-muted">Stock</dt><dd className="font-medium capitalize">{m.stock}</dd></div>
              </dl>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export function KnowUnknown({ v }: { v: ProductView }) {
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card>
        <Kicker>What we know</Kicker>
        <ul className="mt-3 space-y-2 text-sm">
          {v.known.map((k) => <li key={k} className="flex gap-2"><span className="font-bold text-brand">✓</span><span>{k}</span></li>)}
        </ul>
      </Card>
      <Card>
        <Kicker>What we don't know yet</Kicker>
        <ul className="mt-3 space-y-2 text-sm">
          {v.unknown.map((k) => <li key={k} className="flex gap-2"><span className="text-muted">○</span><span>{k}</span></li>)}
        </ul>
      </Card>
    </div>
  );
}

// Reference categorical palette (dataviz skill), fixed order, assigned by sorted storefront name.
const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"];
const SHAPES = ["circle", "square", "triangle", "diamond", "cross", "star", "wye"] as const;

export function PriceHistory({ v }: { v: ProductView }) {
  const [table, setTable] = useState(false);
  if (v.history.message) {
    return (
      <div>
        <SectionTitle title="Price history" />
        <Card className="text-center">
          <p className="text-base font-semibold">Price history is building</p>
          <p className="mx-auto mt-2 max-w-xl text-sm text-muted">
            DealLens needs more observed production runs before making historical price claims.
          </p>
          <p className="mt-4 text-sm font-medium">
            {plural(v.coverage.observed_days, "observed calendar day")} · {plural(v.coverage.runs, "production run")} ·{" "}
            {plural(v.coverage.independent_sellers, "independent seller")}
          </p>
        </Card>
      </div>
    );
  }
  const stores = [...new Set(v.history.points.map((p) => p.storefront ?? "—"))].sort();
  return (
    <div>
      <SectionTitle title="Price history" subtitle="Each point is one observation. Points are not joined: prices between observations are unknown." />
      <Card>
        <div className="h-72 w-full">
          <ResponsiveContainer>
            <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
              <CartesianGrid stroke="#ececE8" />
              <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} scale="time" name="Observed at (UTC)"
                tickFormatter={(t) => new Date(t).toISOString().slice(5, 16).replace("T", " ")} tick={{ fontSize: 11 }} />
              <YAxis dataKey="price" type="number" name="Observed listed price" domain={["auto", "auto"]}
                tickFormatter={(p) => `₹${Number(p).toLocaleString("en-IN")}`} tick={{ fontSize: 11 }} width={80} />
              <Tooltip formatter={(value: number, name: string) => name === "Observed listed price" ? `₹${value.toLocaleString("en-IN")}` : new Date(value).toISOString()} />
              <Legend />
              {stores.map((s, i) => (
                <Scatter key={s} name={s} fill={SERIES[i % SERIES.length]} shape={SHAPES[i % SHAPES.length]}
                  data={v.history.points.filter((p) => (p.storefront ?? "—") === s).map((p) => ({ t: Date.parse(p.observed_at), price: p.price }))} />
              ))}
            </ScatterChart>
          </ResponsiveContainer>
        </div>
        <button className="mt-3 text-xs font-medium text-brand" onClick={() => setTable(!table)}>
          {table ? "Hide" : "Show"} observed points as a table
        </button>
        {table && (
          <table className="mt-3 w-full text-left text-xs">
            <thead className="text-muted"><tr><th className="py-1">Day (IST)</th><th>Observed at (UTC)</th><th>Storefront</th><th>Price</th></tr></thead>
            <tbody>{v.history.points.map((p) => (
              <tr key={`${p.observed_at}-${p.storefront}`} className="border-t border-line"><td className="py-1">{p.day}</td><td>{p.observed_at}</td><td>{p.storefront}</td><td>{p.price_label}</td></tr>
            ))}</tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

export function Why({ v }: { v: ProductView }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div>
      <SectionTitle title="Why DealLens says this" subtitle="Every statement is a deterministic claim computed from observations DealLens collected." />
      <div className="grid gap-4 md:grid-cols-2">
        {v.claims.map((c) => (
          <Card key={c.claim_id}>
            <Kicker>{c.title}</Kicker>
            <p className="mt-2 text-sm font-medium">{c.text}</p>
            <dl className="mt-4 space-y-1 text-xs text-muted">
              <div><dt className="inline">Source: </dt><dd className="inline text-ink">{c.source}</dd></div>
              <div><dt className="inline">Evidence: </dt><dd className="inline font-mono text-ink">{c.claim_id} · {c.kind}</dd></div>
              <div><dt className="inline">Run: </dt><dd className="inline font-mono text-ink">{[...new Set(c.evidence.map((e) => e.run_id))].join(", ")}</dd></div>
            </dl>
            <button className="mt-3 text-xs font-medium text-brand" onClick={() => setOpen(open === c.claim_id ? null : c.claim_id)}>
              {open === c.claim_id ? "Hide" : "View"} evidence details
            </button>
            {open === c.claim_id && (
              <ul className="mt-2 space-y-2 text-xs">
                {c.evidence.map((e) => (
                  <li key={e.observation_id} className="rounded-lg bg-canvas p-2 font-mono break-all">
                    {e.storefront} · {e.fetched_at} UTC · search {e.search_id} · {e.raw_path} · sha256 {e.raw_sha256.slice(0, 12)}…
                  </li>
                ))}
              </ul>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}

export function RetiredEvidence({ v }: { v: ProductView }) {
  if (!v.plan.label) return null;
  return (
    <Card className="border-dashed">
      <Kicker>{v.plan.label}</Kicker>
      <p className="mt-1 text-xs text-muted">Shown for transparency only. It does not feed the decision above.</p>
      <ul className="mt-3 space-y-1 text-sm">
        {v.market.map((m) => <li key={`${m.storefront}-${m.observed_at}`}>{m.storefront}: {m.listed_price} <span className="text-xs text-muted">({m.observed_at} UTC)</span></li>)}
      </ul>
      <p className="mt-3 text-xs text-muted">{v.summary}</p>
    </Card>
  );
}

export function Coverage({ v, policy, latest }: { v: ProductView; policy: CoveragePolicy | null; latest: string | null }) {
  const c = v.coverage;
  const metrics: [string, number][] = [["Observed calendar days", c.observed_days], ["Production runs", c.runs],
    ["Independent sellers", c.independent_sellers], ["Valid observations", c.valid_observations]];
  return (
    <div>
      <SectionTitle title="Evidence coverage"
        subtitle={!v.plan.is_current && v.plan.shown_ref ? `Figures from ${v.plan.shown_ref}, not the active plan.` : undefined} />
      <Card>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {metrics.map(([label, value]) => (
            <div key={label}><p className="text-3xl font-bold tracking-tight">{value}</p><p className="text-xs text-muted">{label}</p></div>
          ))}
        </div>
        {c.level_code !== "sufficient_history" && (
          <p className="mt-5 text-sm font-medium">Historical conclusions require more observed production data.</p>
        )}
        {policy && (
          <p className="mt-2 text-xs text-muted">
            Policy: history claims need ≥ {policy.limited_min_days} observed calendar days and ≥ {policy.limited_min_runs} runs;
            low/high/average need ≥ {policy.sufficient_min_days} calendar days, ≥ {policy.sufficient_min_runs} runs and ≥{" "}
            {policy.sufficient_min_sellers} independent sellers. A product policy, not a statistical guarantee.
          </p>
        )}
        <div className="mt-5 grid gap-4 border-t border-line pt-4 text-sm sm:grid-cols-2">
          <div><Kicker>Latest production observation</Kicker><p className="mt-1 font-mono text-xs">{latest ? `${latest} UTC` : "—"}</p></div>
          <div><Kicker>Collection schedule</Kicker><p className="mt-1 text-xs">{SCHEDULE} · GitHub Actions · one Google Shopping call per slot</p></div>
        </div>
      </Card>
    </div>
  );
}

export function Plans({ v, plans }: { v: ProductView; plans: PlanRow[] }) {
  return (
    <Card>
      <Kicker>Active tracking plan</Kicker>
      <p className="mt-2 flex items-center gap-2 text-sm">
        <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs font-semibold text-brand-ink">ACTIVE</span>
        <span className="font-mono">{v.plan.active_ref ?? "—"}</span>
      </p>
      {plans.filter((p) => p.plan_ref !== v.plan.active_ref).map((p) => (
        <p key={p.plan_ref} className="mt-2 flex items-center gap-2 text-sm text-muted">
          <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs font-semibold uppercase">{p.status}</span>
          <span className="font-mono">{p.plan_ref}</span>
        </p>
      ))}
      <p className="mt-3 text-xs text-muted">Retired evidence is not combined with the active plan.</p>
    </Card>
  );
}

export function Ledger({ rows }: { rows: LedgerRow[] }) {
  const [open, setOpen] = useState(false);
  return (
    <Card>
      <button className="text-sm font-medium text-brand" onClick={() => setOpen(!open)}>
        {open ? "Hide" : "Show"} evidence ledger ({plural(rows.length, "observation")}, included and excluded)
      </button>
      {open && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-muted"><tr><th className="py-1">Included</th><th>Reasons</th><th>Storefront</th><th>Price</th><th>Day (IST)</th><th>Source</th></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.observation_id} className="border-t border-line align-top">
                <td className="py-1">{r.included ? "yes" : "no"}</td><td>{r.reasons.join("; ") || "—"}</td>
                <td>{r.storefront}</td><td>{r.listed_price}</td><td>{r.observed_day}</td><td>{r.source}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export function Footer() {
  return (
    <footer className="mt-12 border-t border-line pt-6 text-xs leading-relaxed text-muted">
      <p>Observed data only. Prices reflect what DealLens observed at collection time. Not an all-time-low guarantee.
        Not a future price prediction. Stock may be unknown. Google Shopping coverage is not exhaustive.
        Seller-displayed list prices are not verified by DealLens.</p>
      <p className="mt-2 font-medium">Powered by Google Shopping via SerpApi</p>
    </footer>
  );
}
