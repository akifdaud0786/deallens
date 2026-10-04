// Mirrors the Python view models in src/deallens/app/views.py (serialized by src/deallens/api).
// The frontend renders these values; it never recomputes prices, coverage or decisions.

export interface PageState {
  status: "missing" | "empty" | "ready";
  show_products: boolean;
  message: string | null;
  as_of: string | null;
  warnings: string[];
  latest_observation_at: string | null;
}

export interface Card {
  product_key: string;
  model_key: string;
  display_name: string;
  status: string;
  lowest_listed: string;
  independent_sellers: number | null;
  valid_observations: number | null;
  coverage: string;
  history: string;
  current: boolean;
}

export interface Identity {
  brand: string;
  model_key: string;
  display_name: string;
  status: string;
  plan_ref: string | null;
  plan_query: string | null;
  plan_status: string | null;
  other_plans: string[];
}

export interface Kpis {
  lowest_listed: string;
  lowest_listed_at: string | null;
  independent_sellers: number | null;
  valid_observations: number;
  observed_days: number;
  runs: number;
}

export interface CoverageView {
  level_code: "no_history" | "limited_history" | "sufficient_history";
  level: string;
  observed_days: number;
  runs: number;
  independent_sellers: number;
  valid_observations: number;
  days: string[];
}

export interface Evidence {
  observation_id: string;
  storefront: string | null;
  fetched_at: string;
  observed_day: string | null;
  run_id: string;
  source: string;
  search_id: string | null;
  raw_path: string;
  raw_sha256: string;
}

export interface ClaimView {
  claim_id: string;
  kind: string;
  text: string;
  level: string;
  evidence: Evidence[];
  title: string;
  source: string;
}

export interface MarketRow {
  storefront: string | null;
  listed_price: string;
  list_price: string;
  delivery: string;
  stock: string;
  observed_at: string;
}

export interface HistoryPoint {
  observed_at: string;
  day: string;
  storefront: string | null;
  seller: string | null;
  price: number;
  price_label: string;
}

export interface LedgerRow {
  observation_id: string;
  storefront: string | null;
  title: string;
  listed_price: string;
  included: boolean;
  match: string;
  reasons: string[];
  observed_day: string;
  fetched_at: string;
  source: string;
}

export interface PlanState {
  active_ref: string | null;
  shown_ref: string | null;
  is_current: boolean;
  label: string | null;
}

export interface Decision {
  question: string;
  answer: string;
  badge: string;
  checks: [boolean, string][];
  verdict: string;
}

export interface ProductView {
  product_key: string;
  identity: Identity;
  kpis: Kpis;
  coverage: CoverageView;
  summary: string;
  claims: ClaimView[];
  market: MarketRow[];
  history: { message: string | null; points: HistoryPoint[] };
  ledger: LedgerRow[];
  no_valid_observations: boolean;
  as_of: string;
  plan: PlanState;
  decision: Decision;
  hero_price: string;
  hero_meta: string;
  known: string[];
  unknown: string[];
}

export interface PlanRow {
  plan_ref: string;
  plan_id: string;
  version: number;
  status: string;
  effective_from: string;
  rationale: string;
  params: Record<string, string>;
  serves: string[];
}

export interface CoveragePolicy {
  limited_min_days: number;
  limited_min_runs: number;
  sufficient_min_days: number;
  sufficient_min_runs: number;
  sufficient_min_sellers: number;
}

export interface ProductResponse {
  view: ProductView;
  plans: PlanRow[];
  coverage_policy: CoveragePolicy | null;
}
