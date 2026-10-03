# DealLens — Domain Model

Phase C (domain modeling). Inputs: [grilling report](grilling-report.md), [SerpApi research](research/serpapi-google-shopping-india.md), fixtures in `data/cache/`. Vocabulary: [GLOSSARY.md](../GLOSSARY.md). Decisions: [docs/adr/](adr/).
Status 2026-10-03: core implemented test-first (`src/deallens`, 109 tests); updated after the prototype review (§11) and the TDD reconciliation (§12). Test 1 (`product_id` day-to-day stability) and Test 2 (Immersive `page_token` lifetime) are **pending**. Balance 247 credits.

## 1. Refinements to the grilling proposal

The grilling report proposed `Product, Seller, Listing, ObservationRun, RawResponse, PriceSnapshot, Offer, ObservationWindow, Coverage, Claim, Evidence, DealAnalysis`. Changes, and why:

| Change | Why |
|---|---|
| **Search** split out of ObservationRun | A run performs several SerpApi calls; each call has its own `search_id`, status, credit cost and raw file. Failures happen per call. |
| **Search is not per product** (Search ↔ Tracked Product is many-to-many) | One broad query ("ASUS Vivobook 15") returned listings of all three provisional SKUs (`BQ224WS`, `BQ541WS`, `NJ2324WS`). Every Observation is matched against *all* Tracked Products. This also keeps the scheduled query configurable (Test 3 showed the bare model query failed) and can cut credits from 3 per run to 1. |
| **PriceSnapshot → Observation** | "Snapshot" was used for both "one run" and "one price". An Observation is one row of one Raw Response — including rows that match nothing. |
| **Run Manifest** added | Raw responses only exist for successful calls. Failed and skipped (credit-guard) Searches must still be recorded, or the "runs" count in Coverage cannot be rebuilt honestly. |
| **Storefront vs Seller** | The raw `source` string is kept verbatim (Storefront); grouping into Sellers is a replaceable mapping. Flipkart vs Shopsy, asus.com vs ASUS eshop IN stay undecided without redesign. |
| **Listing demoted to a derived reference** | `product_id` stability is unproven (Test 1), and the prototype showed it is not a listing identity at all (§11). History is keyed by (Tracked Product, Seller), never by `product_id`. |
| **Match is its own concept, with Listing Pin** | Test 3 and the broad fixture show relevant listings whose titles lack the Model Key (e.g. Flipkart "Asus Vivobook 15 2025 I5 14th Gen…"). A Listing Pin is a deterministic, human-attested route for those — not fuzzy, not LLM. **Provisional** (§2): its identity semantics are unverified. |
| **Inclusion carries a list of reasons** | One Observation can be both cross-border and unmatched; the ledger must show all reasons. |
| **Investigation** added as Offer's parent | Immersive lookups are on-demand, private, and outside statistics; they are not Observation Runs. |

## 2. Entities

### Configuration (hand-maintained, versioned in git)

**Tracked Product** — `product_key` (slug), `brand`, `model_key`, `aliases[]`, `display_name`, `status: provisional | locked`.
- Identity = brand + Model Key. Product families are never a Tracked Product.
- The three provisional SKUs (`X1504VAP-BQ224WS`, `X1504VAP-BQ541WS`, `X1504VA-NJ2324WS`) stay `provisional` until enough matched Indian sellers are shown.

**Listing Pin** — **PROVISIONAL, not production-ready.** (`product_key`, listing reference, `pinned_by`, `pinned_at`, `note`). Intended to attest that a Listing is a Tracked Product. `product_id` alone cannot identify a Listing (it is a Google catalog cluster when one exists; identical rows carry different values), so no reference format is approved yet. Until Test 1 and further evidence establish a reference that identifies one listing over time, a Listing Pin must not be used to attribute Observations or to create continuity across Observations. Configuration may hold zero pins.

**Query Plan** — `plan_id`, engine, `q`, `gl`, `hl`, `google_domain`, `location`, `serves[]` (product keys), `status: provisional | locked`, `rationale`. Scheduled collection executes Query Plans, not products. Replaceable configuration: changing a plan changes future Searches only; past Raw Responses keep the params they were fetched with.
- Initial plan (D2, **provisional**): `q="ASUS Vivobook 15"`, `gl=in`, `hl=en`, `google_domain=google.co.in`, `location=Mumbai,Maharashtra,India`, `no_cache=true`, serves all three provisional products. Rationale: the 3 Oct broad fixture surfaced listings for all three; the bare model query for `X1504VAP-BQ224WS` returned zero title matches.
- A raw that records its plan keeps it. A raw without a recorded plan (probes) is assigned the matching plan version **in force when it was fetched** (greatest `effective_from` <= `fetched_at`), never a later version.
- `status: retired` plans are kept for provenance only: the collector never executes them, and a retired plan may still name products that have left the watchlist.
- A Search's Observations are matched against **every** Tracked Product, not only `serves[]`; `serves[]` only says which products expect coverage from the plan.

**Seller Map** — `mapping_version`, with two parts (D3):
- `storefront → seller_key`. Default: identity (each Storefront is its own Seller). Merging Storefronts is an explicit, versioned edit backed by a note on the evidence.
- `related_groups[]`: groups of Related Storefronts, each with a `note`. Initial groups: {`asus.com`, `ASUS eshop IN`}, {`Flipkart`, `Shopsy By Flipkart`}. They remain separate Sellers for display, but each group counts **once** in the Independent Seller Count until the mapping either merges them or marks them independent.

**Cross-border List** — small documented list of Storefront patterns (e.g. desertcart\*, ubuy, Microless) plus the rule "non-INR `alternative_price` present". `rules_version`.

### Immutable evidence (append-only files)

**Observation Run** (recorded as a **Run Manifest**) — `run_id`, `trigger: scheduled | manual | probe`, `target_time`, `started_at`, `finished_at`, `status`, `searches[]` (each with `plan_id`, status, `raw_ref` or failure/skip reason), credit guard reading.
- Real collection **must** write an explicit Run Manifest. Every attempted SerpApi call belongs to exactly one run and appears in its manifest with an explicit status.
- Coverage counts runs only from manifests; in production, runs are never inferred from raw file names.
- **Orphan Raw Response**: a Raw Response whose `run_id` matches no Run Manifest (e.g. collection stopped after writing the raw, before the manifest). It does not count as a run, contributes nothing to Coverage, and every Observation read from it is excluded with reason `orphan_raw`; it stays inspectable in the Evidence Ledger for forensic purposes. Production collection always writes a manifest, so orphans signal an interrupted run, not a data source.
- **Manifest-less development fixtures**: the 3 Oct probe files have no manifest. They may be ingested only as development fixtures, each labelled `run_source = manifest_less_probe` with a synthetic run per file; this labelling is visible in the ledger.

**Search** — one attempted SerpApi call. `engine`, params (no secret), `status: succeeded | repeat | failed | skipped`, `search_id` and `raw_ref` (when a response arrived), failure/skip reason.
- `repeat`: a response arrived but its `search_id` was already recorded (SerpApi cache); kept as a Raw Response, yields no Observations.

**Raw Response** — `{meta, response}` file. `meta.fetched_at` (UTC, authoritative time), `meta.params`, `meta.search_id`, `meta.kind`; plus a content hash recorded by the ledger. `sensitivity: shareable | private` (Immersive = private, contains reviewer names).

### Derived (rebuildable)

**Observation** — one `shopping_results[i]` of one non-repeat Raw Response: `observation_id = (raw_ref, position)`, `run_id`, `storefront`, `title`, `google_ids` (provenance only: `product_id` and, when present in `product_link`, `catalogid` / `productid` / `headlineOfferDocid`), `listed_price_inr`, `price_raw`, `list_price_inr?`, `list_price_raw?`, `delivery_raw?`, `rating?`, `reviews?`, `alternative_price?`, `stock_status = unknown`, `fetched_at = meta.fetched_at` (UTC, authoritative), `observed_day` = calendar date of `fetched_at` in Asia/Kolkata (derived on read, never stored in place of `fetched_at`).

**Match** — (`observation_id`, `outcome: matched | unmatched | ambiguous`, `product_key` (only when matched), `candidates[]` (every product whose evidence was found), `evidence[]` (each: `alias` found in title, or `pin`), `config_versions`). Outcome is decided purely by the number of distinct candidate products (D1):
- 0 → `unmatched`
- exactly 1 → `matched`
- > 1 → `ambiguous` — DealLens never picks one; all candidates are recorded so the ledger can show why.

**Inclusion** — (`observation_id`, `product_key`, `included: bool`, `reasons[]`, `rules_version`). Reasons: `unmatched`, `ambiguous`, `cross_border`, `used_or_refurbished`, `unpriced`, `non_inr`, `indistinguishable_in_run`, `outlier`, `orphan_raw`, `integrity_failed`, `development_probe`.
- **Development probe**: every Observation read from a Manifest-less Probe is excluded with `development_probe`. Probes remain in the Evidence Ledger for audit, but contribute nothing to statistics, Coverage, observed days, runs, seller counts, price history or Claims (other than an attributable `excluded_count`).
- **Integrity failure**: when a Run Manifest recorded a content hash for a Raw Response and the file's current hash differs, every Observation read from it is excluded with `integrity_failed` and stays visible. Raws with no recorded hash (Manifest-less Probes, Orphan Raw Responses) are unverifiable, not failed; this rule does not apply to them.
- **Outlier peer group (provisional heuristic)**: an Observation is compared only with the other included Observations of the **same Tracked Product in the same Observation Run**; prices from other runs or days are never peers (a price that moved between days is history, not an outlier). The rule applies only when that peer group has at least the configured minimum size (currently 5) and flags deviation above the configured threshold (currently ±35% from the group median).
- **Indistinguishable Results (provisional policy)**: within one Observation Run, rows with the same fingerprint (Storefront, normalized title, Listed Price, parsed List Price) carry no independent price evidence; the first counts, the rest are excluded as `indistinguishable_in_run` and stay in the ledger.
- This is **not** a claim that they are the same listing: Google gave the six LowestRate rows six different `headlineOfferDocid`s. Collapsing them cannot change the observed low, high or spread (same Storefront, same price); it only stops them inflating valid-observation counts and averages.
- Google ids (`product_id`, offer ids) are excluded from the fingerprint because identical rows carry different values. Rows that differ in price are never collapsed (JanSport: one `product_id`, four prices, four Observations).
- Known limitation: two genuinely different listings from one Storefront with identical normalized title and price are counted once. No fixture can distinguish this case; accepted because it changes no price-level Claim, only counts.

**Listing** — a seller's offer page. DealLens currently has **no verified identifier** for it: `product_id` is a Google catalog cluster when one exists, otherwise a per-offer id (80/80 fixture rows), and `headlineOfferDocid` is observed but undocumented. Listing is therefore a descriptive term only — not an entity with an identity, not a dedup key, not a history anchor.

**Investigation / Offer** — Investigation: (`investigation_id`, source `observation_id` and its `page_token`, `status: succeeded | failed | skipped`, `raw_ref` private, `fetched_at`). A live Investigation spends at most one paid call, obeys the same credit guard as collection, and is impossible in public mode; a failed or blocked Investigation has no Offers. Offer: store row with `seller name`, `price`, `total`, `shipping`, `stock_text`, link. Never feeds statistics.

**Observation Window**, **Coverage**, **Claim**, **Evidence**, **Deal Analysis** — see §6–§7.

## 3. Relationships

| Relationship | Cardinality |
|---|---|
| Observation Run → Search | 1 : N |
| Search → Raw Response | 1 : 0..1 (failed/skipped have none) |
| Raw Response → Observation | 1 : N (0 if Repeat Response) |
| Query Plan ↔ Tracked Product | N : M |
| Search (via its Observations) ↔ Tracked Product | N : M (one response may match several products) |
| Observation → Match | 1 : 1 |
| Match → Tracked Product (`matched`) | N : 1; `ambiguous` keeps N : M candidates but attributes to none |
| Observation → Inclusion | 1 : 1 (excluded with `unmatched`/`ambiguous` when there is no single product) |
| Related Storefront group → Storefront | 1 : N (a Storefront is in at most one group) |
| Storefront → Seller | N : 1 (mapping, revisable) |
| Listing → Observation | not modelled (no verified Listing identity) |
| Listing Pin → Tracked Product | N : 1 (provisional; not used for attribution yet) |
| Observation Run → Observation | 1 : N (Indistinguishable Results are judged within a run) |
| Investigation → Offer | 1 : N |
| Observation → Investigation | 1 : N |
| Deal Analysis → Claim | 1 : N |
| Claim ↔ Observation | N : M (the Evidence link) |
| Tracked Product → Coverage | 1 : 1 per Observation Window |

## 4. Invariants

1. A Raw Response is never modified or overwritten; file names are unique and timestamped.
2. `meta.fetched_at` (UTC) is the only observation time and is never rewritten. `observed_day` is derived from it in Asia/Kolkata. Git commit time is extra provenance only.
3. A Raw Response whose `search_id` was already recorded is a Repeat Response (Search status `repeat`) and yields no Observations.
4. A failed or skipped Search yields no Observation and no price.
4a. Every attempted collection call appears in exactly one Run Manifest with status `succeeded | repeat | failed | skipped`. Production Coverage never infers runs from file names.
4b. An Orphan Raw Response never counts as a run; its Observations are always excluded (`orphan_raw`) and remain visible.
4d. Only Observations from runs with a valid Run Manifest can count toward Coverage; Manifest-less Probe Observations are always excluded (`development_probe`).
4c. A Raw Response whose content no longer matches the hash its Run Manifest recorded never contributes to statistics or Coverage; its Observations are excluded (`integrity_failed`) and remain visible.
5. Every Observation is kept and visible in the Evidence Ledger, whatever its Inclusion.
6. An Observation is included only if Match ≠ none **and** reasons is empty.
7. Matching is deterministic: same inputs + same configuration versions ⇒ same Match. No fuzzy, embedding or LLM matching.
8. An Observation is attributed to at most one Tracked Product; evidence for more than one makes it `ambiguous` and excluded, never auto-resolved.
9. Investigation Offers never enter statistics or Coverage. A live Investigation obeys the credit guard (`remaining < min_remaining` ⇒ `skipped`, no call) and a one-call budget; public mode cannot invoke it; a failed or skipped Investigation yields no Offer.
10. Private Raw Responses (Immersive) never leave the local machine.
11. Listed Price is only ever `extracted_price` of a Shopping row; `extracted_old_price` is never used (it returned the discount %, `11`, live).
12. Stock Status is `unknown` unless a source stated it; wording is "lowest listed price".
13. Outlier is judged only within its peer group (same Tracked Product, same Observation Run), only when the group is large enough; flagged Observations stay in the ledger.
14. Every number in a Deal Analysis comes from a Claim; every Claim lists its supporting Observations.
15. A Claim is allowed only if Coverage Level permits its kind.
16. Changing a Query Plan or the Seller Map never rewrites past Raw Responses; it only changes future Searches or re-derived projections, under a new configuration version.
17. Related Storefronts are never counted as independent Sellers unless the Seller Map explicitly says so; coverage is never satisfied artificially.
18. `product_id` (and any Google id) is provenance only: never a Listing identity, never a dedup key on its own, never a history anchor.
19. Indistinguishable Results are judged only within one Observation Run, never across runs: the same Storefront at the same price in a later run is a new Observation.
20. A product-level exclusion Claim is produced only for Observations matched to that product and then excluded; unmatched and ambiguous Observations appear in the global ledger, not in any product's Claims.
21. Listing Pins do not attribute Observations or create continuity until their identity semantics are verified.

## 5. Lifecycles

**Observation Run**: `planned → running → completed | partial | failed | skipped`
- `skipped`: credit guard (`remaining < 60`) or duplicate-run detection; reason recorded.
- `partial`: at least one Search failed or was skipped.

**Search**: `pending → succeeded | repeat | failed | skipped`. Retries bounded; each attempt is recorded in the Run Manifest.

**Observation (derived)**: `read → matched | unmatched → included | excluded(reasons)`. Re-derived whenever configuration versions change; prior derivations are not history.

**Tracked Product**: `provisional → locked` (or replaced). Requires an Independent Seller Count ≥ 2 of matched, non-cross-border Observations.

## 6. Coverage and Claims

**Coverage** (per Tracked Product, per Observation Window), computed from included Observations only:

| Input | Definition |
|---|---|
| observed days | distinct `observed_day` values (Asia/Kolkata date of `fetched_at`) with ≥ 1 included Observation |
| runs | distinct Observation Runs with ≥ 1 included Observation |
| independent sellers | distinct `seller_key` among included Observations, each Related Storefront group counted once |
| valid observations | count of included Observations |
| runs searched | Runs whose Query Plans serve the product (shown so gaps are visible) |

**Coverage Level** (product policy, not a scientific guarantee):
- *No history*: < 2 runs or 1 observed day → current-market Claims only.
- *Limited history*: 2–4 observed days → change-since-date Claims.
- *Sufficient history*: ≥ 5 observed days and ≥ 8 runs and Independent Seller Count ≥ 2 → observed low / high / average Claims.

**Claim** — `claim_id`, `kind`, `params` (numbers), `text` (deterministic template), `supporting_observation_ids[]`, `min_level`.
Kinds: `current_lowest_listed`, `current_spread`, `seller_count`, `listed_discount`, `change_since`, `observed_low`, `observed_high`, `observed_average`, `excluded_count`.
- `current_spread` wording: when low ≠ high, "range from ₹X to ₹Y"; when low = high, "Observed listed prices are ₹X across the included sellers".
- `listed_discount` restates a seller's displayed List Price and says DealLens has not verified it.
- `excluded_count` only for exclusions attributable to the product (invariant 20).
Never: all-time low, fake discount, future price.

**Evidence** — for each Claim: Observation → Raw Response (`raw_ref`, content hash, `search_id`) → Storefront → `fetched_at`.

## 7. Deal Analysis

`product_key`, `as_of`, Observation Window, Coverage (inputs + level), allowed Claims, `summary`, `summary_source: template | llm`, configuration versions. The summary may only restate Claims and must cite claim IDs; an LLM summary that fails validation is replaced by the template. Works with no LLM.

## 8. Persistence boundary

| Kind | Where | Rebuildable? |
|---|---|---|
| Configuration (Tracked Products, Aliases, Listing Pins, Query Plans, Seller Map, Cross-border List, rule versions) | files in git | — source |
| Run Manifests | append-only files | — source |
| Raw Responses (Shopping) | immutable files; public publication pending ToS | — source |
| Raw Responses (Immersive) | immutable local-only files | — source, private |
| Observation, Match, Inclusion, Listing, Investigation/Offer | SQLite | yes, from source |
| Coverage, Claim, Evidence, Deal Analysis | computed on read (may be cached in SQLite) | yes |

SQLite is a disposable projection: deleting it and re-ingesting source files must reproduce identical results for the same configuration versions.

## 9. Raw SerpApi JSON → domain

| Raw field | Domain concept |
|---|---|
| `meta.fetched_at` | Observation `fetched_at` (UTC); `observed_day` derived in Asia/Kolkata |
| `meta.params`, `search_parameters.location_used` | Search params; Query Plan check |
| `search_metadata.id` | Search `search_id`; Repeat Response detection |
| `search_metadata.status` | Search status |
| `shopping_results[i].position` | Observation id part |
| `.source` | Storefront → Seller Map |
| `.title` | Match (Alias search after normalization) |
| `.product_id` | provenance only; equals `catalogid` in `product_link` when present, else `productid` (80/80 fixture rows; undocumented) |
| `.product_link` → `prds=` `catalogid`, `productid`, `headlineOfferDocid` | provenance only (`google_ids`); undocumented |
| `.extracted_price` / `.price` | Listed Price / raw evidence |
| `.old_price` | List Price, parsed by DealLens (e.g. `"11% off₹68,999"` → 68999) |
| `.extracted_old_price` | **ignored** |
| `.alternative_price.currency` ≠ INR | Cross-border signal |
| `.delivery`, `.rating`, `.reviews` | kept as evidence; nullable |
| `.second_hand_condition` | used/refurbished signal (never observed for India) |
| `.immersive_product_page_token` | Investigation entry point (lifetime pending) |
| `categorized_shopping_results` | ignored (cut) |
| Immersive `product_results.stores[]` | Offers (`name`, `price`, `extracted_total`, `details_and_offers` → stock text, `link`) |
| Immersive `user_reviews` | never stored outside private raw |

**Fixture scenarios this model must handle**
- `20261003T140442Z_shopping.json` — first Observations; history starts 3 Oct 14:04 UTC.
- `20261003T140455Z_shopping.json` — same `search_id` ⇒ Repeat Response, zero Observations.
- `20261003T144432Z_shopping.json` — bare model query: zero Alias matches; all Observations `unmatched` but visible.
- LowestRate Shopping ×6 rows: same title and price, six different `product_id` and `headlineOfferDocid` ⇒ one counted, five `indistinguishable_in_run`.
- Meetel ×2 (Test 3 fixture): same pattern ⇒ one counted, one `indistinguishable_in_run`.
- JanSport (Test 3 fixture): one `product_id`, four different prices ⇒ four Observations, none collapsed.
- No fixture row is `ambiguous`; that outcome is covered only by a synthetic unit test.
- desertcart.com.sa with SAR `alternative_price` ⇒ `cross_border`.

## 10. Unresolved decisions

| Decision | Blocked on |
|---|---|
| Lock the broad Query Plan, or replace it (brand+family+model / other) | Several days of scheduled results; any paid comparison needs approval |
| Listing Pins viable, and with which listing reference? | Test 1 plus evidence that some reference identifies one listing over time (`product_id` cannot) |
| Investigation needs a fresh search first? | Test 2 (`page_token` lifetime) |
| Final three Tracked Products | Query Plan + matched-seller evidence |
| Resolve Related Storefront groups (merge or mark independent): Flipkart/Shopsy, asus.com/ASUS eshop IN | Evidence about the commercial seller; until then each group counts once |
| Outlier minimum sample size and threshold | Product decision |
| Contents of the Cross-border List | Product decision (keep small) |
| Publishing Shopping raws publicly | SerpApi ToS review |
| LLM integration and model ID | Codebase design, official Anthropic docs |
| Can history span Query Plan changes (e.g. a change-since Claim comparing observations from two different plans)? | Product decision before any plan change |
| What evidence resolves a Related Storefront group (merge vs independent) | Product decision |
| Is the Indistinguishable Results fingerprint right beyond the 3 Oct fixtures (e.g. same title and price but different delivery)? | More scheduled data |
| Is `headlineOfferDocid` stable and meaningful enough to become a Listing reference? | Undocumented; needs cross-day evidence |

## 11. Prototype review (2026-10-03)

The throwaway prototype (`prototype/`) ran the model end-to-end on the three Shopping fixtures without an LLM or paid calls. It confirmed Repeat Response handling, alias boundaries (`X1504VA` and `BQ1341WS` do not match), cross-border detection via non-INR `alternative_price` (iGeek Megastore, JOD), deterministic `old_price` parsing, Related Storefront counting, UTC → IST days, plan-version separation, coverage gating (all three products `no_history`) and Claim provenance. It exposed:

1. `product_id` is not a Listing identity: identical rows carry different values, and one value spans rows with different prices. Now provenance only (invariant 18).
2. The original dedup key `(seller, product_id, price)` would not have collapsed LowestRate ×6. Replaced by the provisional Indistinguishable Results policy (§2 Inclusion), with its limitation documented.
3. Probe fixtures have no Run Manifest; real collection must write one (§2, invariant 4a).
4. `current_spread` read "range from ₹73,990 to ₹73,990"; wording fixed (§6).
5. Product-level `excluded_count` would have counted unmatched rows; now only attributable exclusions (invariant 20).

## 12. TDD reconciliation (2026-10-03)

| Finding | Decision |
|---|---|
| Observations from Orphan Raw Responses had no defined treatment | **Accepted**: Orphan Raw Response defined (§2, invariant 4b, glossary); new Exclusion Reason `orphan_raw`. |
| Outlier "peers" were undefined | **Accepted**: peer group = same Tracked Product + same Observation Run (§2 Inclusion, invariant 13). Threshold and minimum unchanged and still provisional. |
| `current_median` listed as a Claim kind but required by nothing | **Removed** from the kinds list. No requirement in the grilling report, prototype or tests depends on it; it can be re-added if a later need appears. |
| Raw content hash computed but never enforced (code review) | **Accepted**: Exclusion Reason `integrity_failed` for raws whose recorded hash no longer matches (invariant 4c); unverifiable raws unchanged. |
| Investigation is a paid call outside the collector | **Accepted**: credit guard + one-call budget + public-mode impossibility + no Offer on failure (invariant 9). No change to the Investigation model itself. |

## 13. Watchlist and probe corrections (2026-10-03, after Tests 1 and 2)

| Change | Reason |
|---|---|
| `development_probe` Exclusion Reason; invariant 4d | Probes (no Run Manifest) were inflating production Coverage: the 3 Oct probe plus the first manual run produced "2 observed days" from a 5-hour gap across IST midnight. |
| `X1504VAP-BQ541WS` replaced by `X1504MA-BQ832WS` (`products-2`) | BQ541WS was absent from the repeat response and its only storefronts are one Related Storefront group. BQ832WS: single model key in title, Vijay Sales (India), present in both broad responses at ₹82,990 with the same `product_id`. Chosen from existing evidence; no paid call. |
| `vivobook15-broad@1` retired, `vivobook15-broad@2` provisional (`plans-2`) | A watchlist change is a Query Plan version change: same query parameters, new `serves`. Coverage never combines @1 and @2. |
| Coverage wording: "observed calendar days" | Counting IST dates is not elapsed duration. |
