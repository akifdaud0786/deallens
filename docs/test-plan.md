# DealLens — Test Plan (TDD phase)

Seams under test are exactly the interfaces in [codebase-design.md](codebase-design.md) §2. Internal-seam tests exist only for `market` parsing/matching rules that encode domain rules directly. No test touches the network; no paid calls. `P#` marks a regression of one of the 25 prototype cases (`prototype/test_deallens_proto.py`).

Fixtures: `tests/fixtures/shopping/` (3 Oct probes, manifest-less), `tests/fixtures/immersive_sanitized/` (no reviewer data), `synthetic_*` builders in `tests/synthetic.py` for cases real data lacks (ambiguous rows, multi-day history, failures). Synthetic data is always named so.

| # | Domain rule | Module (seam) | Test file | Cases |
|---|---|---|---|---|
| 1 | Product identity = brand + model key + aliases; config validated | `config.load_config` | `tests/test_config.py` | loads repo config; duplicate alias across products rejected; plan `serves` unknown product rejected; overlapping related groups rejected |
| 2 | Title normalization, invisible chars | `market.parsing` (internal) | `tests/market/test_parsing.py` | `‎` stripped; tokens uppercase |
| 3 | Match outcomes 0/1/>1, token boundary | `market.matching` (internal) + `build_ledger` | `tests/market/test_matching.py` | matched Amazon BQ224WS (P1); `X1504VA`, `BQ1341WS` not matched (P3); synthetic ambiguous never attributed (P4); pin + other alias ⇒ ambiguous (P5); pins in config do not attribute while provisional |
| 4 | INR price parsing | `market.parsing` | `test_parsing.py` | `₹1,16,076` → 116076; `₹72,051.94`; non-₹ → None |
| 5 | `old_price` parsing; `extracted_old_price` ignored | `market.parsing` + ledger | `test_parsing.py`, `test_ledger.py` | 8-case table (P10–P17); Flipkart row list price 68999 / 11 % (P18) |
| 6 | Google ids are provenance only | `market.parsing.google_ids` + ledger | `test_parsing.py`, `test_ledger.py` | catalogid/productid/headlineOfferDocid extracted; `product_id == catalogid or productid` on all fixture rows |
| 7 | Indistinguishable Results within one run | `build_ledger` | `test_ledger.py` | LowestRate ×6 → 1 counted, 5 `indistinguishable_in_run`, 6 offer ids (P6); JanSport 4 prices not collapsed (P7); same row in two different runs both counted |
| 8 | Inclusion reasons, nothing dropped | `build_ledger` | `test_ledger.py` | 80 observations kept (P2); unmatched excluded; unpriced; used/refurbished keyword |
| 9 | Cross-border | `build_ledger` | `test_ledger.py` | desertcart.com.sa (SAR) and iGeek (JOD) (P9) |
| 10–11 | Storefront vs Seller; Related groups; Independent Seller Count | `market.sellers` + `analyse` | `test_sellers.py`, `tests/analysis/test_analyse.py` | BQ541WS → 1, BQ224WS → 2 (P19); group marked independent → 2 (P20); explicit merge map |
| 12–13 | `fetched_at` UTC kept; `observed_day` IST | `market.parsing.observed_day` + ledger | `test_parsing.py` | 19:00Z → next IST day; 18:29:59Z same day; ledger keeps UTC string (P21) |
| 14 | Query Plan versioning; unplanned probes; no cross-plan combining | `build_ledger` + `analyse` | `test_ledger.py`, `test_analyse.py` | broad probe → `vivobook15-broad@1`; model probe → `None` (P23); synthetic second plan version not combined |
| 15 | Run Manifest rules | `evidence`, `collector`, ledger | `tests/evidence`, `tests/collector`, `test_ledger.py` | probes labelled `manifest_less_probe` (P24); orphan raws excluded and never runs |
| 16 | Repeat search | `build_ledger`, `collect` | `test_ledger.py`, `test_collect.py` | repeated `search_id` → 0 observations (P8); collector marks `repeat` |
| 17–18 | Coverage levels; Claim eligibility; forbidden phrasing | `analyse` | `test_analyse.py` | fixtures → `no_history` + "No price history yet." (P22); synthetic 3-day → limited + change_since; synthetic 6-day/9-run/2-seller → sufficient + low/high/average; related group blocks sufficient; spread wording equal/unequal (P25a/b); no bogus `excluded_count` |
| 19 | Claim provenance | `analyse` | `test_analyse.py` | every claim → observation → raw sha256 → run → search_id → storefront → fetched_at; claim ids appear in summary (P25) |
| 20 | Deterministic Deal Analysis | `analyse` | `test_analyse.py` | same inputs ⇒ equal output |
| E | Evidence Store | `evidence.EvidenceStore` | `tests/evidence/test_store.py` | atomic write; no overwrite; sha256 recorded and verified; manifest write-once; orphans in `read_all`; private area separate; key never in written bytes |
| S | SerpApi port | `serpapi` | `tests/serpapi/test_port.py` | fixture adapter success / api_error / timeout / credits; HTTP adapter with injected fake opener: URL has key, outcome and repr never do; error messages redacted |
| C | Collector | `collector.collect` | `tests/collector/test_collect.py` | one manifest per execution; duplicate slot skipped; success writes raw; api_error → failed, no retry; transport error retried up to max then failed; guard `remaining < 60` → skipped, 0 calls; call budget cap; key absent from logs/files; collector imports no market/analysis |
| M | Market pipeline | `market.build_ledger` | `tests/market/test_ledger.py` | rows 3–16 above on real fixtures |
| A | Analysis | `analysis.analyse` | `tests/analysis/test_analyse.py` | rows 10–20 above |
| PJ | Projection | `projection.rebuild`, `ProjectionReader` | `tests/projection/test_projection.py` | rebuild twice identical; delete + rebuild; reader returns watchlist/product/ledger/claim; SQL contains no rule thresholds |
| I | Investigation | `investigation.investigate`, `sanitize` | `tests/investigation/test_investigation.py` | raw stored private; sanitized view has no reviewer data; offers never enter ledger |
| AR | Architecture | imports | `tests/test_architecture.py` | domain/market/analysis import no infrastructure; collector imports no market/analysis; only `cli` imports `serpapi.http`; only `cli` reads env; no `streamlit` outside `app`; public composition never loads `HttpSerpApi` (subprocess with key set) |
| E2E | Rebuild on fixtures | `cli rebuild` composition | `tests/test_e2e.py` | probes → projection with 3 products `no_history`; full provenance chain |
