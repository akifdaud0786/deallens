# DealLens — Grilling Report

Phase B of the Matt Pocock workflow (research → live verification → **grilling** → domain modeling → prototype → codebase design → TDD → code review).
Date: 2026-10-03. Grounded in `docs/research/serpapi-google-shopping-india.md` and the live fixtures in `data/cache/` (2 credits spent, 248 left).

> DealLens is an AI-powered commerce intelligence agent that tracks the same product across sellers, builds an evidence-backed price history, and explains whether today's price is actually good based on the data it has observed.
> Demo line: "Don't just tell me the cheapest price. Tell me what today's price means."

## 1. Key risks discovered

| # | Risk | Evidence | Mitigation |
|---|---|---|---|
| R1 | Broad queries return mostly noise | "ASUS Vivobook 15": only 10/40 titles carry a model number; 21/40 from cross-border resellers | Query by exact model number (tested 4 Oct) |
| R2 | `product_id` is a listing ID, not a product ID | Same model `X1504VAP-BQ541WS` has different `product_id` at asus.com and ASUS eshop IN | Canonical product = brand + exact model key |
| R3 | `extracted_old_price` is wrong | `old_price="11% off₹68,999"` → `extracted_old_price=11` | Own deterministic parser on `old_price` raw string |
| R4 | Immersive Product unreliable as seller source | 7 offers all Flipkart; 4 out of stock; title variant `nj3700ws` ≠ `NJ2324WS`; `price_range` inconsistent; no `original_price`/rating per store | Optional, on-demand only |
| R5 | Cheapest listing may be unavailable | Immersive's lowest (₹47,990) was "Out of stock online"; Shopping has no stock field | "stock status: unknown", "lowest listed price" wording |
| R6 | Variant contamination of history | R4 title mismatch | Exact alias match + outlier flag (kept in ledger) |
| R7 | Duplicate listings inflate counts | "LowestRate Shopping" same listing ×6 | Dedup within an ObservationRun |
| R8 | Too little history by the deadline | Deadline 10 Oct 23:59 IST | Raw-only collector starts 4 Oct |
| R9 | Usage counter lags | Immersive call recorded `credits_used=0`, Account API later showed +1 | Count credits by calls made; don't trust immediate `usage_after` |
| R10 | Public demo could burn credits | Live calls cost 1 credit each | Public deployment is read-only fixture mode |
| R11 | Raw Immersive JSON contains third-party personal data | `user_reviews[]` include `user_name` and review text | Never commit Immersive raws publicly |
| R12 | Repo bloat | Shopping raw ≈ 350 KB each → 63 runs ≈ 22 MB | Gzip raws (decision in codebase design) |
| R13 | Provisional SKU may have only one real seller | `X1504VAP-BQ541WS`: asus.com and ASUS eshop IN may be the same retailer | 4 Oct model-query test; replace SKU if < 2 Indian sellers |

## 2. Decisions locked

**Identity & matching**
- Product = brand + exact model key (SKU), with a small hand-confirmed alias list. No product families. (Q1)
- Deterministic normalized exact alias matching only. No fuzzy matching in MVP. (Q4)
- Unmatched listings stay in the Evidence Ledger as `unmatched`, excluded from statistics. (Q4)

**Data sources**
- Google Shopping = primary scheduled source. Immersive Product = optional, on-demand ("Inspect seller offers"); never in the scheduler. Reverse only on strong evidence. (Q7)
- Canonical scheduled price = Shopping `extracted_price`. Raw `price` and `delivery` kept as evidence. Immersive `extracted_total` shown separately, never mixed into primary stats. (Q8)
- `extracted_old_price` is never trusted; list price parsed deterministically from `old_price` raw. No LLM in parsing.

**Inclusion rules** (everything stays in the ledger with a reason; `excluded_from_statistics = true`)
- Cross-border: non-INR `alternative_price` OR a small, documented reseller-domain list. (Q6)
- Outlier: ±35% from median — heuristic only, not proof of wrong variant; not applied when too few valid observations for a reliable median. (Q5)
- Used/refurbished/open-box: title keywords or `second_hand_condition`. (Q13)
- Missing price: `unpriced`. (Q13)

**Wording & claims**
- Stock unknown from Shopping → "stock status: unknown"; "lowest listed price", never "lowest available price" unless verified. (Q9)
- Coverage levels (product policy, not a scientific guarantee): (Q11)
  - < 2 runs / 1 day → current-market claims only, "No price history yet"
  - 2–4 days → limited historical claims ("changed X% since <date>")
  - 5+ days and 8+ runs and 2+ sellers → observed low/high/average
- Always display coverage inputs: observed days, runs, sellers, valid observations. Phrase as "Based on the observations collected by DealLens…".
- Never claim: all-time low, fake discount, future price.

**LLM**
- Deterministic code computes all numbers. LLM only synthesizes from approved claims `{claim_id, claim_text, supporting_snapshot_ids, supporting_source}`; must cite claim IDs; output validated, rejected/regenerated on failure. (Q12)
- `ANTHROPIC_API_KEY` optional; app works fully on a deterministic template fallback. Model ID not assumed — verify from official Anthropic docs during codebase design, only if integration is kept. (Q20)

**Collection**
- Raw JSON `{meta, response}` is the source of truth; the DB is always rebuildable from it. (Q14)
- Authoritative observation time = `meta.fetched_at`. Git commit time is extra provenance only.
- Raw-only collector starts 4 Oct after the three approved tests, after a dry-run against a cached fixture. (Q14)
- GitHub Actions cron, `SERPAPI_API_KEY` as Actions secret, 3 target runs/day at 09:00 / 15:00 / 21:00 IST (targets, not guarantees). (Q15, Q17)
- One `ObservationRun` per execution; dedup within run; a repeated `search_id` (cache hit) never creates a new observation; a fresh later search with the same seller/price **is** a new observation. (Q10)
- Collector safety: credit guard (`remaining < 60` → skip and log reason), max products per run, max calls per run, timeout, bounded retries with no credit-consuming loops, duplicate-run detection, key never logged, atomic write, never overwrite, failed call → `status = failed`, never a price observation.

**Product & stack**
- Watchlist of 3 SKUs for scheduled snapshots; "Investigate now" is secondary and shows "No price history yet". (Q2)
- Public deployment = read-only fixture mode; live mode only with local config. Both secondary actions show whether data is cached or live. (Q18, Q21)
- Stack: Python, SQLite, Streamlit, SerpApi, pytest, GitHub Actions. (Q19)

## 3. Decisions still open (until 4 Oct tests or later phases)

| Open decision | Settled by |
|---|---|
| Final 3 SKUs (provisional: `X1504VAP-BQ224WS`, `X1504VAP-BQ541WS`, `X1504VA-NJ2324WS`) — each needs ≥ 2 useful Indian sellers | 4 Oct model-number query |
| Is the exact model-number query clean enough to be the scheduled query? | 4 Oct model-number query |
| Is `product_id` stable day-to-day (usable as listing key)? | 4 Oct Shopping repeat |
| Does an Immersive `page_token` survive a day? (decides whether "Inspect seller offers" needs a fresh search first) | 4 Oct old-token test |
| Which raw files may be committed publicly (Shopping gzip? Immersive never) and SerpApi ToS on redistribution | Codebase design; ToS not yet read |
| Whether "Shopsy By Flipkart" and "Flipkart", or "asus.com" and "ASUS eshop IN", count as distinct sellers | Domain modeling |
| Exact seller-normalization rules and the documented cross-border list | Domain modeling |
| Minimum valid observations for applying the outlier rule | Domain modeling |
| Anthropic integration kept or template-only; exact model ID | Codebase design (official docs) |
| Collector numeric limits (max products/calls per run, timeout, retries) | Codebase design |

## 4. Final MVP scope

1. Raw-only scheduled collector (Shopping, 3 SKUs, 3×/day) with all safety rules.
2. Deterministic pipeline: raw JSON → parse/normalize (₹, `old_price`) → match → classify inclusion → SQLite.
3. History analyzer: per-SKU and per-seller change, observed min/max/average (gated by coverage).
4. Coverage calculator (days, runs, sellers, valid observations → level).
5. Claims builder + Deal Intelligence (template; optional Claude synthesis with claim-ID validation).
6. Evidence Ledger: every observation, inclusion/exclusion reason, link to raw file and `search_id`.
7. Streamlit: Watchlist + Product Detail (Current Market → Observed Price History → Coverage → Deal Intelligence → Evidence Ledger), secondary "Investigate now" / "Inspect seller offers" with cached/live indicator.
8. Public read-only deployment; README with SerpApi usage and AI-tool disclosure; demo video < 3 min.

## 5. Proposed domain entities (input to domain modeling)

| Entity | Meaning |
|---|---|
| `Product` | Brand + exact model key (SKU) + alias list. Unit of tracking. |
| `Seller` | Normalized retailer name (from Shopping `source` / Immersive store `name`), with `is_cross_border`. |
| `Listing` | A seller's listing as Google exposes it (Shopping `product_id`; Immersive `pid`+`lid`). Many per Product. |
| `ObservationRun` | One scheduled or manual execution: run ID, trigger, target time, status, raw files, credits. |
| `RawResponse` | Immutable `{meta, response}` file; `search_id`, `fetched_at`, params. Source of truth. |
| `PriceSnapshot` (observation) | One listing's price at one run: price, raw price, list price, discount, delivery, stock (unknown), match result, inclusion status + reason, link to RawResponse. |
| `Offer` | Immersive-only seller offer (price, total, stock text). Supplementary; never in primary stats. |
| `ObservationWindow` | Time span + runs over which statistics are computed. |
| `Coverage` | Observed days, runs, sellers, valid observations → level (none / limited / sufficient). Not an LLM score. |
| `Claim` | Deterministic, numbered statement with supporting snapshot IDs and source. |
| `Evidence` | Claim → Snapshot(s) → RawResponse → source + timestamp chain. |
| `DealAnalysis` | Claims + coverage + summary (template or validated LLM). |

## 6. Product-matching strategy

1. Normalize title: strip invisible chars (`‎`), unify case, collapse spaces/hyphens.
2. Match only if a hand-confirmed alias of the Product's model key appears in the normalized title.
3. Unmatched → ledger `unmatched`, excluded.
4. Second guard: outlier flag vs median of included observations (only when enough observations); flagged rows stay visible with reason.
5. No fuzzy, embedding or LLM matching in MVP.

## 7. Snapshot strategy

- Query = exact model number (pending 4 Oct), `engine=google_shopping`, `gl=in`, `hl=en`, `google_domain=google.co.in`, `location=Mumbai,Maharashtra,India`, `no_cache=true`.
- 3 SKUs × 3 runs/day; 1 Shopping call per SKU per run; Immersive never scheduled.
- Save raw immutably with UTC `fetched_at`; parse later, deterministically; DB rebuildable.
- A cached (`search_id` repeat) response never becomes a new observation; failed calls → `status=failed`.

## 8. Explicitly cut

Login/accounts, alerts, multi-category, phones, Google Trends, fuzzy matching, price prediction, fake-discount verdict, scheduled Immersive calls, `categorized_shopping_results`, mobile app, excessive filters.
Stretch only after the core is complete and tested: SerpApi MCP agent flow.

## 9. Assumptions still requiring live verification

- `product_id` stability across days (4 Oct).
- Immersive `page_token` lifetime (4 Oct).
- Exact model-number query quality and ≥ 2 Indian sellers per SKU (4 Oct).
- `old_price` formats beyond `"11% off₹68,999"` (only 2/40 samples).
- `second_hand_condition` behavior for India (never observed).
- Collector behavior on GitHub Actions runners (location honored, no IP-related differences).
- SerpApi ToS on publishing raw responses (docs read pending).

## Live verification log (post-grilling)

### 2026-10-03 14:44 UTC — Test 3: exact model-number query (1 credit)

Fixture: `data/cache/20261003T144432Z_shopping.json`. Params: `q=X1504VAP-BQ224WS`, `gl=in`, `hl=en`, `google_domain=google.co.in`, `location=Mumbai,Maharashtra,India`, `no_cache=true`. `location_used` = Mumbai; `shopping_results_state` = "Results for exact spelling".

| Measure | Result |
|---|---|
| Results | 40 |
| Titles containing `X1504VAP-BQ224WS` (normalized) | **0** |
| Titles containing "Vivobook" | 28 (mostly other models: Vivobook 14 X1404VAP-*, Go 15 E1504FA-*, X1504ZA) |
| Non-laptop junk (backpacks, keyboard) | 8 |
| Top sources | desertcart.in 13, Meetel Computer's 7, Flipkart 4, Amazon.in 2 |
| Amazon.in listing of this SKU from the broad query (`product_id 11178454701273335360`) | **absent** |
| `product_id` overlap with the 14:04 broad-query fixture | 0 |

Findings (from one sample — not generalized):
- A bare exact-model query did **not** return the target SKU at all, and returned less relevant results than the broad family query.
- Some relevant-looking listings (e.g. Flipkart "Asus Vivobook 15 2025 I5 14th Gen…") carry no model number in the title, so exact-title matching cannot attribute them to a SKU. This threatens the recall of the locked matching strategy (§6), not only the query choice.
- Usage counter lag reproduced: `meta.credits_used=0` at save time; Account API afterward showed 247.

Consequences:
- **Exact bare model-number query is NOT suitable as the scheduled query** on current evidence.
- Final SKUs **cannot be locked** yet.
- New open decisions: scheduled query shape (broad family query + matching / brand+family+model query / other) and whether title-only matching has enough recall.

### Tests 1 and 2 — deferred

Not run. At 14:44 UTC the previous fixture was only ~40 minutes old, so they could not measure cross-day stability, which is their purpose. To run on 2026-10-04 (≥ 18 h after 14:04 UTC).

## Credit budget through 10 Oct 23:59 IST

| Item | Credits |
|---|---:|
| Spent (3 Oct live probe) | 2 |
| Model-number query (done 3 Oct, Test 3) | 1 |
| 4 Oct approved tests (Shopping repeat, old Immersive token) | 2 |
| Scheduled collector: 3 SKUs × 3/day, ~4 Oct 15:00 → 10 Oct 21:00 (≤ 21 runs) | ≤ 63 |
| Collector dry-run / manual verification | ~3 |
| Development & integration checks (prefer fixtures) | ~15 |
| Demo: "Investigate now" + "Inspect seller offers" live | ~5 |
| **Planned total** | **~91** |
| **Remaining margin of 250** | **~159** |

Hard guard: collector skips when `remaining < 60`.

### 2026-10-03 19:05–19:06 UTC (00:35 IST, 4 Oct) — Tests 1 and 2 (2 credits, via CLI + CallBudget)

Elapsed since the first probe: **~5 hours**, not a full day (the IST calendar date did change). Evidence: run manifest `manual-2026-10-03T19:05:53.470788+00:00`; private Immersive raw under `data/private/raw/immersive/`.

**Test 1 — Shopping repeat (`collect --trigger manual`, plan `vivobook15-broad@1`)**: fresh `search_id` (`6ac152128b61d60fbfaf9cc9`), 40 rows.
- Rows with the same storefront and normalized title in both responses: 28 (of 32 new / 35 old distinct keys).
- Over those 28: `product_id` equal 27/28; `headlineOfferDocid` equal 26/28; listed price equal 26/28.
- `X1504VAP-BQ224WS`: Amazon.in ₹72,800 → **₹72,790** (same `product_id`); ASUS eshop IN ₹73,990 (same).
- `X1504VA-NJ2324WS`: Flipkart ₹61,599 (same `product_id`).
- `X1504VAP-BQ541WS`: **absent** from the new response.
- Conclusion (5-hour evidence only): Google ids are mostly but not fully stable, so ADR 0004 holds; Listing Pins stay provisional.

**Test 2 — Immersive with the 3 Oct `page_token`**: fresh `search_id` (`6ac1521ca20802600cc8b979`), status Success, same product title and the same 7 Flipkart offers (3 in stock, 4 out of stock). A ~5-hour-old token is still valid; a one-day lifetime is not yet proven.
