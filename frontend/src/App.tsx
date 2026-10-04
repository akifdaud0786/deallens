import { useEffect, useState } from "react";
import { api } from "./api/client";
import type { Card as CardT, PageState, ProductResponse } from "./types/deallens";
import { Card } from "./lib/ui";
import { Coverage, Footer, HeroAndDecision, KnowUnknown, Ledger, Market, Plans, PriceHistory, RetiredEvidence,
  Tagline, TopBar, Why } from "./components/sections";

export default function App() {
  const [state, setState] = useState<PageState | null>(null);
  const [cards, setCards] = useState<CardT[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [product, setProduct] = useState<ProductResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.status(), api.products()])
      .then(([s, c]) => {
        setState(s);
        setCards(c);
        setSelected((c.find((x) => x.current) ?? c[0])?.product_key ?? null);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setProduct(null);
    api.product(selected).then(setProduct).catch((e: Error) => setError(e.message));
  }, [selected]);

  const v = product?.view;
  return (
    <div className="min-h-screen">
      <TopBar state={state} />
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Tagline />
        {error && <Card><p className="text-sm">Could not reach the DealLens API: {error}</p></Card>}
        {state && !state.show_products && <Card><p className="text-sm">{state.message}</p></Card>}
        {state?.warnings.map((w) => <Card key={w} className="mb-4 border-amber-200 bg-amber-bg"><p className="text-xs text-amber-ink">{w}</p></Card>)}

        {cards.length > 0 && (
          <nav className="mb-6 flex flex-wrap gap-2" aria-label="Tracked products">
            {cards.map((c) => (
              <button key={c.product_key} onClick={() => setSelected(c.product_key)}
                className={`rounded-xl border px-4 py-2 text-left text-sm transition ${selected === c.product_key
                  ? "border-brand bg-white shadow-sm" : "border-line bg-white/60 hover:bg-white"}`}>
                <span className="block font-mono text-xs font-semibold">{c.model_key}</span>
                <span className={`block text-xs ${c.current ? "text-ink" : "text-muted"}`}>{c.lowest_listed}</span>
              </button>
            ))}
          </nav>
        )}

        {v && product && (
          <div className="space-y-10">
            <HeroAndDecision v={v} />
            <Market v={v} />
            <KnowUnknown v={v} />
            {v.plan.is_current && <PriceHistory v={v} />}
            {(v.plan.is_current || !v.plan.label) && <Why v={v} />}
            <RetiredEvidence v={v} />
            <Coverage v={v} policy={product.coverage_policy} latest={state?.latest_observation_at ?? null} />
            <Plans v={v} plans={product.plans} />
            <Ledger rows={v.ledger} />
          </div>
        )}
        <Footer />
      </main>
    </div>
  );
}
