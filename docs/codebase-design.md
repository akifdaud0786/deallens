# DealLens — Codebase Design

Phase E (codebase design). Source of truth: [domain model](domain-model.md) and [GLOSSARY.md](../GLOSSARY.md). Evidence of behaviour: `prototype/`. Status 2026-10-03: design only, no production code. Test 1 (listing-reference stability) and Test 2 (Immersive `page_token` lifetime) are **pending**. Credits 247.

Vocabulary from the codebase-design skill: **module**, **interface** (everything a caller must know), **seam**, **adapter**, **depth**. Domain words are the glossary's.

## 0. Design stance

The user's draft listed eleven packages (`serpapi, snapshots, runs, products, matching, sellers, analysis, evidence, storage, investigation, config`). Applying the deletion test, several would be shallow pass-throughs whose callers always use them together:

- `products`, `matching`, `sellers`, plus parsing and dedup, are always run in one order over the same rows to answer one question: *what did we observe, and what counts?* They become one deep module, **`market`**, with a one-function interface; the parts survive as internal seams with their own tests.
- `snapshots` and `runs` both write immutable evidence files and must agree on run linkage. They become one module, **`evidence`** (Evidence Store).
- `evidence` in the draft (provenance) is not a separate computation: provenance is data carried by Observations and Claims. It lives in `domain` types and is exposed by `market` and `analysis`.

Only two seams get ports, because only they have two real adapters today: **SerpApi** (live HTTP / fixture replay) and **Evidence Store** (filesystem / temp-dir in tests is the same adapter, so *no* port — see §4). The LLM summarizer is a hypothetical seam (one adapter today) and is not introduced yet.

## 1. Folder structure

```
SERP/
├── pyproject.toml                  # package `deallens`, src layout, pytest config
├── config/                         # versioned configuration (JSON), no code
│   ├── products.json               # Tracked Products, Aliases, Listing Pins (empty)
│   ├── query_plans.json            # Query Plans (vivobook15-broad@1, provisional)
│   ├── sellers.json                # Seller Map + Related Storefront groups
│   ├── rules.json                  # cross-border list, used keywords, outlier, fingerprint policy
│   ├── coverage.json               # Coverage Level thresholds
│   └── collector.json              # credit guard, call caps, timeout, retries (values open)
├── data/
│   ├── evidence/                   # SOURCE OF TRUTH (append-only)
│   │   ├── manifests/<run_id>.json
│   │   ├── raw/shopping/<fetched_at>_<run_id>_<plan>.json
│   │   └── probes.json             # registers the 3 Oct manifest-less probes
│   ├── private/                    # gitignored, never published
│   │   └── raw/immersive/…
│   ├── cache/                      # existing 3 Oct probe files (stay where they are)
│   └── projection/deallens.sqlite  # disposable, rebuilt
├── src/deallens/
│   ├── domain.py                   # frozen dataclasses only: no I/O, no logic beyond validation
│   ├── config/                     # load + validate config files → Config
│   ├── serpapi/                    # SerpApi port + HTTP adapter + fixture adapter
│   ├── evidence/                   # Evidence Store: raw responses, run manifests, probes
│   ├── collector/                  # one Observation Run, credit safety
│   ├── market/                     # parsing, matching, sellers, inclusion, dedup → Ledger
│   │   ├── parsing.py  matching.py  sellers.py  inclusion.py  fingerprint.py  ledger.py
│   ├── analysis/                   # coverage, claims, templates → Deal Analysis
│   │   ├── coverage.py  claims.py  summary.py  analyse.py
│   ├── investigation/              # on-demand Immersive, sanitization
│   ├── projection/                 # SQLite rebuild + read model for the UI
│   ├── app/                        # Streamlit (later phase; reads projection only)
│   └── cli.py                      # composition root: collect | rebuild | investigate | ledger
├── tests/
│   ├── fixtures/
│   │   ├── shopping/               # copies of the 3 Oct Shopping probes
│   │   ├── immersive_sanitized/    # Immersive probe with user_reviews removed
│   │   └── synthetic/              # clearly-named hand-built rows (e.g. ambiguous)
│   ├── market/  analysis/  collector/  evidence/  investigation/  projection/  e2e/
├── prototype/                      # throwaway; moves to a branch after TDD
└── docs/
```

## 2. Modules

Each entry: responsibility · interface · depends on · must NOT know.

### `domain`
- **Responsibility**: the shared vocabulary as frozen dataclasses: `RawRecord`, `SearchAttempt`, `RunManifest`, `Observation`, `Match`, `Inclusion`, `Ledger`, `Coverage`, `Claim`, `Provenance`, `DealAnalysis`, `Investigation`, `Offer`, plus enums (`SearchStatus`, `MatchOutcome`, `ExclusionReason`, `CoverageLevel`, `RunSource`).
- **Interface**: the types and their invariants (e.g. `Match.product_key` is set iff `outcome == matched`; `Observation.fetched_at` is tz-aware UTC).
- **Depends on**: stdlib.
- **Must NOT know**: files, HTTP, SQLite, Streamlit, configuration values.

### `config`
- **Responsibility**: read `config/*.json`, validate (unique product keys, aliases not shared across products, every plan's `serves` exists, related groups disjoint), expose one immutable `Config` with a `versions` map.
- **Interface**: `load_config(path) -> Config`. Raises `ConfigError` with every problem listed.
- **Depends on**: `domain`.
- **Must NOT know**: SerpApi, evidence files, business rules (it validates shape, not policy).

### `serpapi` — **port + 2 adapters** (true external dependency)
- **Responsibility**: build requests, authenticate, return responses with request metadata; never decide anything about products, sellers or prices.
- **Interface**:
  - `SerpApi.search(params: Mapping[str, str], timeout_s) -> SearchOutcome` where `SearchOutcome = {status: ok | api_error | transport_error | timeout, http_status?, body?: dict, error?: str, elapsed_s}`. Never raises for API/transport failures; never returns the key.
  - `SerpApi.credits() -> CreditReading` (`plan_searches_left`, `this_month_usage`, `read_at`) — free endpoint; the reading may lag (observed 3 Oct).
- **Adapters**: `HttpSerpApi(api_key)` (live; key passed in by the composition root, redacted from every repr/log/exception), `FixtureSerpApi(files)` (replays recorded bodies; used by tests and never billed).
- **Depends on**: `domain`, `urllib`.
- **Must NOT know**: Query Plans, Observation Runs, matching, files on disk (other than the fixture adapter's inputs).

### `evidence` (Evidence Store)
- **Responsibility**: the only writer/reader of source evidence: raw responses (shareable and private areas), Run Manifests, the probe registry. Atomic write (temp file + `os.replace`), refuse to overwrite, SHA-256 at write, envelope `{meta, response}` with `fetched_at` UTC, params without key, `search_id`, `status`, `run_id`, `plan`, `sensitivity`.
- **Interface**:
  - `write_raw(attempt: SearchAttempt, body, sensitivity) -> RawRef` (`RawRef` = path + sha256)
  - `write_manifest(manifest: RunManifest) -> None` (exactly once per run; refuses if `run_id` exists → duplicate-run protection)
  - `has_run(run_id) -> bool`, `known_search_ids() -> set[str]`
  - `read_all() -> EvidenceSet` (manifests, raws with recomputed hashes, registered probes, **orphans** = raws with no manifest)
- **Depends on**: `domain`, filesystem.
- **Must NOT know**: matching, prices, sellers, SQLite, SerpApi.
- No port: tests use the same filesystem adapter on `tmp_path` (local-substitutable).

### `collector`
- **Responsibility**: execute one Observation Run for a set of Query Plans with every credit-safety rule; write raws and exactly one manifest.
- **Interface**: `collect(config, serpapi, store, *, trigger, target_time, now) -> RunManifest`.
  Interface facts a caller must know: it reads credits before the first paid call; it never makes more than `max_calls_per_run` attempts; a skipped run still produces a manifest with the reason; it marks a Search `repeat` when the returned `search_id` is already in the store; it never raises on API failure (status goes in the manifest); it raises only on misconfiguration or store refusal.
- **Depends on**: `domain`, `config`, `serpapi` (port), `evidence`.
- **Must NOT know**: matching, sellers, prices, claims, SQLite, Streamlit.
- Internals: `CreditGuard`, `RetryPolicy` (bounded, transport/5xx only; never retries `api_error` such as quota or invalid key), `CallBudget` (hard cap enforced by a wrapper around the port so a loop bug cannot exceed it).

### `market` — the deep core
- **Responsibility**: turn evidence + config into the **Ledger**: every Observation with parsed prices, Google identifiers (provenance), Match, Seller, Inclusion and reasons, `config_versions`, `run_id`, `run_source`, `plan`. Includes Repeat Response handling, Indistinguishable Results and outlier marking.
- **Interface**: `build_ledger(evidence: EvidenceSet, config: Config) -> Ledger`.
  `Ledger` exposes `observations` (all, nothing dropped), `for_product(key)`, `unattributed()` (unmatched + ambiguous), `runs` (from manifests + labelled probes; orphans listed but never counted).
- **Internal seams** (own unit tests, not part of the interface):
  - `parsing`: `parse_inr`, `parse_list_price` (never reads `extracted_old_price`), `normalize_title`, `strip_invisible`, `google_ids(product_link)`
  - `matching`: `match(title, pins, products) -> Match` (0/1/>1 rule; token-boundary alias test)
  - `sellers`: `seller_of(storefront, seller_map)`, `independent_seller_count(sellers, seller_map)`
  - `fingerprint`: `IndistinguishablePolicy` selected by name from `rules.json` (`"storefront_title_prices@1"`); replaceable without touching callers
  - `inclusion`: cross-border, used/refurbished, unpriced, non-INR, outlier (only when sample ≥ configured minimum)
- **Depends on**: `domain`, `config` types. Pure; no I/O.
- **Must NOT know**: SerpApi, files, SQLite, Streamlit, LLM.

### `analysis`
- **Responsibility**: deterministic numbers → Coverage → allowed Claims → template summary, per Tracked Product and Query Plan version.
- **Interface**: `analyse(ledger, product_key, config, *, as_of) -> DealAnalysis`.
  Interface facts: never combines Query Plan versions (others reported in `coverage.other_plans_not_combined`); Claims carry provenance down to raw ref, sha256, run id, search id, storefront, `fetched_at`; a Claim kind is emitted only when Coverage Level ≥ its `min_level`; forbidden phrasing is rejected by a final guard; `summary_source == "template"` always works.
- **Internal seams**: `coverage.compute`, `claims.build`, `summary.render_template`.
- **Depends on**: `domain`, `market.Ledger`, `config`.
- **Must NOT know**: SerpApi, files, SQLite, Streamlit, LLM SDKs.
- LLM later: an outer adapter `Summarizer` taking `DealAnalysis.claims` and returning text that `analysis.validate_summary(text, claims)` must accept, else the template is used. Not built now.

### `investigation`
- **Responsibility**: on-demand Immersive lookup for one Observation; store the raw privately; return Offers; produce a sanitized, publishable view.
- **Interface**: `investigate(observation, serpapi, store, config, *, now) -> Investigation` and `sanitize(investigation) -> PublicInvestigation` (drops reviewer names/text, keeps store name, price, total, stock text, link, `fetched_at`).
  Interface facts: costs 1 credit (2 if the token must be refreshed — see Test 2); its Offers never reach `market` or `analysis`.
- **Depends on**: `domain`, `serpapi`, `evidence`, `config`.
- **Must NOT know**: Coverage, Claims, SQLite.

### `projection`
- **Responsibility**: write a disposable SQLite read model from a `Ledger` and its `DealAnalysis` list; serve read queries to the UI. Plain tables mirroring domain types; no business rules in SQL (no thresholds, no matching, no inclusion).
- **Interface**: `rebuild(ledger, analyses, path) -> ProjectionInfo` (atomic replace of the DB file; stores config versions and source hashes) and `ProjectionReader(path)` with `watchlist()`, `product(key)`, `ledger(key | None)`, `claim(claim_id)`.
- **Depends on**: `domain`, `sqlite3`.
- **Must NOT know**: SerpApi, config files, how inclusion was decided.

### `app` (later phase)
- Streamlit screens (Watchlist, Product Detail). Reads `ProjectionReader` only. In public mode it has no route to `collector`, `investigation` or `serpapi`.

### `cli` — composition root
- The only place that reads environment variables, constructs `HttpSerpApi`, chooses modes, and wires modules. Commands: `collect --trigger scheduled|manual`, `rebuild`, `investigate <observation_id>`, `ledger [product]`, `credits`.

## 3. Dependency graph

```
                    domain
          ┌───────────┼──────────────┬────────────┐
        config      serpapi(port)   evidence    projection
          │            │  ▲            │  ▲          ▲
          ├──► market ─┼──┼────────────┘  │          │
          │      │     │  │               │          │
          ├──► analysis│  │               │          │
          │            ▼  │               │          │
          ├──► collector ─┴───────────────┘          │
          └──► investigation ── serpapi, evidence    │
                                                      │
 cli (composition root) ──► everything; app ──► projection only
```

Rules enforced by a test that inspects imports:
- `market`, `analysis` import only `domain`, `config` (types), stdlib.
- `serpapi` and `evidence` never import `market`/`analysis`.
- Nothing imports `app` or `cli`; nothing but `cli` imports `HttpSerpApi`.
- No module imports `streamlit` except `app`.

## 4. Data flow

```
collect:  Config.query_plans ─► collector ─► SerpApi.search ─► evidence.write_raw ─► evidence.write_manifest
rebuild:  evidence.read_all ─► market.build_ledger ─► analysis.analyse (per product) ─► projection.rebuild
view:     app ─► ProjectionReader
investigate (local only): observation ─► investigation ─► SerpApi(immersive) ─► evidence (private) ─► sanitize
```

`rebuild` is deterministic: same evidence + same config versions ⇒ byte-identical projection content.

## 5. Persistence boundaries

| Data | Owner | Format | Mutability | Published? |
|---|---|---|---|---|
| Configuration | `config/` in git | JSON with `version` per file | edited by humans, versioned | yes |
| Run Manifests | `evidence` | JSON, one file per run | write-once | yes (manifests hold statuses and ids, no response data) |
| Shopping raws | `evidence` | `{meta, response}` JSON | write-once, never overwritten | **pending SerpApi ToS review** |
| Immersive raws | `evidence` (private area) | same envelope | write-once | **never** |
| Probe registry | `evidence` | `probes.json` listing the 3 Oct files as `manifest_less_probe` | write-once entries | yes |
| SQLite | `projection` | `deallens.sqlite` | disposable, replaced atomically | shipped to public deploy as a prebuilt read model |

Orphan raws (raw written, process died before the manifest) are reported by `read_all()`, shown in the ledger as `orphan`, and never counted as runs.

## 6. Configuration boundary

All values listed in the domain model live in `config/*.json`; Python modules contain no product keys, aliases, storefront names, thresholds, URLs or limits. Each file carries `version`; `Config.versions` is copied onto every Observation and Deal Analysis. Validation failures stop every command before any paid call. Secrets never live in config: `SERPAPI_API_KEY` comes only from the environment, read only in `cli`.

## 7. Error-handling strategy

| Situation | Handling |
|---|---|
| SerpApi transport error / timeout / 5xx | `SearchOutcome.status` set; collector retries within `RetryPolicy`; each attempt recorded; **every attempt counted as potentially billed** (usage counter lags) |
| SerpApi `error` body (invalid key, quota, bad params) | no retry; Search `failed`; run `partial`/`failed`; message stored with key redacted |
| Credit guard below minimum | run `skipped` with reason; manifest written; zero paid calls |
| Duplicate scheduled slot | `write_manifest` refuses; run `skipped` (duplicate) reported to caller |
| Store refuses overwrite | hard error (bug); run aborts; manifest written with `failed` if possible |
| Malformed row field (e.g. unparsable `old_price`) | Observation kept; field `parse_status=unparsed`; never guessed |
| Config invalid | `ConfigError` before any I/O |
| Unexpected response shape | Search `succeeded` but Observations=0 with a ledger warning; never fabricated |

## 8. Testing strategy

Tests sit at module interfaces ("the interface is the test surface"); internal-seam tests are allowed for `market.parsing`/`matching`/`fingerprint` because they encode domain rules directly.

| Suite | Through | Covers |
|---|---|---|
| `tests/market` | `build_ledger` + internal seams | all 25 prototype cases (regression), Repeat Response, alias boundaries, ambiguous (synthetic), Indistinguishable Results incl. JanSport, cross-border by currency and pattern, `old_price` table, Google ids provenance, IST day, plan separation, orphan raws |
| `tests/analysis` | `analyse` | coverage gating at 1 / 2–4 / 5+ days (synthetic multi-day ledgers, clearly marked), spread wording, `listed_discount`, attributable `excluded_count` only, forbidden-phrase guard, plan versions not combined |
| `tests/collector` | `collect` with `FixtureSerpApi` + tmp store | credit guard skip, `max_calls_per_run`, bounded retries (no retry on `api_error`), timeout path, duplicate-run refusal, `repeat` status, failed call ⇒ no raw observation, manifest lists every attempt, key absent from every written byte and log record |
| `tests/evidence` | store API on `tmp_path` | atomic write, no overwrite, hash recorded and re-verified, private area separation, orphan detection |
| `tests/investigation` | `investigate` + `sanitize` | private storage, sanitized view has no `user_name`/review text, Offers never in Ledger |
| `tests/projection` | `rebuild` + reader | rebuild twice ⇒ identical; no business logic (reader returns what analysis computed) |
| `tests/e2e` | `cli rebuild` on fixtures | provenance chain Claim → Observation → raw (sha256) → manifest/probe → search_id → storefront → fetched_at; public mode never constructs `HttpSerpApi` even with the key set |
| `tests/test_architecture.py` | imports | dependency rules of §3 |

## 9. Fixture strategy

- `tests/fixtures/shopping/`: byte copies of the three 3 Oct Shopping probes (registered as `manifest_less_probe`). Publication pending SerpApi ToS; if not allowed, replace with trimmed fixtures keeping only the fields the tests read.
- `tests/fixtures/immersive_sanitized/`: Immersive probe with `user_reviews`, `reviews_images` removed. The original stays in `data/private/`.
- `tests/fixtures/synthetic/`: hand-built envelopes for cases no real data has: ambiguous rows, multi-day histories, failed searches, orphan raws. File names start with `synthetic_` and tests say so.
- No test calls the network; `HttpSerpApi` is exercised only by a manual smoke command.

## 10. Production vs public-deployment boundary

| | Local / live mode | Public read-only mode |
|---|---|---|
| Composition | `cli` + optional `app` | `app` only |
| `HttpSerpApi` constructed | yes, only when `SERPAPI_API_KEY` set and `DEALLENS_MODE=live` | **never** (code path absent, not just disabled) |
| Data | `data/evidence` + rebuilt projection | prebuilt `deallens.sqlite` + shareable evidence |
| Collect / Investigate buttons | available | hidden; "Investigate" shows sanitized cached Investigations labelled *cached* |
| Immersive raws | local private area | absent |

Default mode is public; live must be opted into explicitly.

## 11. Credit-safety boundary

All paid calls flow through one path: `collector`/`investigation` → `serpapi.CallBudget`-wrapped port → `HttpSerpApi`. `CallBudget` lives in the `serpapi` package so both callers share it; the collector's budget is `max_calls_per_run`, an Investigation's is 1, and both check `min_remaining` before calling.
- Minimum remaining-credit guard: config `collector.min_remaining` (domain-locked value 60).
- Max calls per run, max products/plans per run, per-call timeout, max attempts: config values, **numbers not locked yet**.
- Retries: bounded, transport/5xx only, recorded; no loop may exceed `CallBudget`.
- Duplicate-run protection: scheduled `run_id = scheduled-<IST target slot>`; manifest write-once.
- Every attempt counted as billed for budgeting; the Account API reading is advisory (lags).
- Key: environment only, passed once to `HttpSerpApi`, redacted in repr/logs/errors; tests scan written files and captured logs for the key.

## 12. Prototype → production mapping

| Prototype | Production |
|---|---|
| `load_raw` | `evidence.read_all` (+ hash at write time) |
| `plan_for` | `market.ledger` via `config.query_plans` lookup (plan also stamped in raw meta by `collector`) |
| `observed_day` | `market.parsing.observed_day` |
| `parse_list_price` | `market.parsing.parse_list_price` |
| `google_ids` | `market.parsing.google_ids` |
| `observations_from` | `market.ledger` (repeat handling via known `search_id`s) |
| `_tokens`, `_contains_alias`, `match` | `market.matching` |
| `seller_of`, `independent_seller_count` | `market.sellers` |
| `result_fingerprint` | `market.fingerprint.IndistinguishablePolicy` (`storefront_title_prices@1`) |
| `classify`, `_is_cross_border`, `_apply_outliers` | `market.inclusion` |
| `coverage` | `analysis.coverage` (runs from manifests; probes labelled) |
| `build_claims`, `_inr`, `_indian_grouping`, `FORBIDDEN` | `analysis.claims` |
| `summary` | `analysis.summary.render_template` |
| `run_pipeline` | `cli rebuild` composing `evidence` → `market` → `analysis` → `projection` |
| `run_prototype.render` | discarded (Streamlit `app` later) |
| `proto_config.py` | `config/*.json` |
| `scripts/live_probe.py` | **deleted** (code review, 2026-10-03): it made paid calls outside `CallBudget`. Use `DEALLENS_MODE=live deallens credits` (free) and `collect --trigger manual`. |
| 25 prototype tests | ported to `tests/market` and `tests/analysis` as regression tests |

## 13. ADRs

- **Add 0005** — Public deployment never constructs the SerpApi adapter (written alongside this document).
- **Update 0001** — note orphan raws and the probe registry: raws without a manifest are never counted as runs.
- Not ADR-worthy (easy to reverse): JSON config format, folder names, module split inside `market`.

## 14. Pending live tests — architecture holds either way

| Test | If it passes | If it fails |
|---|---|---|
| Test 1: listing-reference stability (`product_id` / `headlineOfferDocid`) | a listing reference format may be approved; Listing Pins become usable by adding pins to `config/products.json` | Listing Pins stay empty; nothing else changes (history is keyed by product + seller) |
| Test 2: Immersive `page_token` lifetime | `investigate` uses the stored token (1 credit) | `investigate` first re-runs the Observation's Query Plan to get a fresh token (2 credits); confined to `investigation` |

## 15. Unresolved decisions

| Decision | When |
|---|---|
| Numeric limits: `max_calls_per_run`, timeout, max attempts | before enabling the scheduler |
| Gzip raws or not; publish Shopping raws (SerpApi ToS) | before first public commit of evidence |
| Python version for deployment (local is 3.10; affects `tomllib`, typing) | before deployment |
| Run id scheme for manual runs | TDD of `collector` |
| How orphan raws are surfaced in the UI | app phase |
| LLM summarizer adapter kept or not; Anthropic model id from official docs | after core is complete |
| All domain-model §10 decisions (Query Plan lock, final SKUs, Related Storefronts, outlier threshold, cross-border list, cross-plan history, fingerprint beyond 3 Oct data) | as listed there |

## 16. Implementation notes from TDD (2026-10-03)

Interface details that differ slightly from §2 and are accepted as implementation decisions (no domain impact):

- `deallens/text.py` holds title tokenization shared by `config` validation and `market` matching, so `config` does not import `market`.
- `EvidenceStore.write_raw(meta, response, *, sensitivity)` takes the envelope metadata directly instead of a `SearchAttempt`.
- `projection.rebuild(ledger, analyses, path, *, products)` also takes the Tracked Products so the watchlist can show names.
- `as_of` and `fetched_at` are compared as ISO strings; both must be UTC with a `+00:00` offset.
- In live mode only, `cli` fills missing environment variables from the local `.env`; the key is never printed.
- `CallBudget` / `BudgetExceeded` moved from `collector` to `serpapi` (reconciliation, see §11).

## 17. Code-review fixes (2026-10-03)

- `scripts/live_probe.py` deleted; an architecture test forbids `serpapi.com` / `urlopen` outside `serpapi/http.py`.
- `serpapi.CallBudget(api, max_calls, min_remaining)` is the single gate for paid calls: `open()` reads credits once and raises `CallBlocked` below the minimum; `search()` refuses when the cap is reached or `credits_before - used < min_remaining`. Collector (`max_calls_per_run`) and Investigation (1) both use it; an architecture test keeps the guard comparison in one file.
- Non-JSON responses are `invalid_response` (never retried). Account-API failures raise a redacted `CreditReadError`; the collector then writes a `failed` manifest (`failure_reason`) with no paid call. A raw-write failure after a paid call is recorded as a `failed` attempt with its `search_id` and no `raw_ref`, and the run stops.
- `EvidenceSet.missing_probes` lists registered probes absent from the checkout (they live in gitignored `data/cache`); `rebuild` warns on stderr instead of crashing.
- Fixtures trimmed (see `tests/fixtures/README.md`); publication still pending the SerpApi Terms check.

## 18. UI read model (2026-10-03)

Prepared so the Streamlit `app` holds no domain logic:

- `domain.Coverage.latest_run_id`: set by `analysis.coverage` (the run of the most recent included Observation in the Coverage plan); `analysis.claims` reuses it, so "latest run" is decided in one place.
- `projection.rebuild(..., products, plans=(), missing_probes=(), as_of=None, coverage_policy=None)`; meta adds `as_of`, `missing_probes`, `coverage_policy`, `observations`. `meta.sources` lists **shareable raws only**; private (Immersive) paths never reach the projection.
- `ProjectionReader.current_market(key)` (Coverage's latest-run rows), `price_series(key)` (Coverage's `observation_ids`, one plan version only), `plans()`; `product(key)["coverage"]["latest_run_id"]`. These select by ids analysis already chose; they apply no rules.
- `public.projection_status(root)`: `missing | empty | ready`.
- `text.inr` (Indian digit grouping) moved from `analysis.claims` so the app can format without importing `analysis`.
- `tests/test_architecture.py::test_app_package_is_presentation_only`: the future `app` may import only `deallens.public`, `deallens.projection`, `deallens.text`, `deallens.app` and `streamlit` (plus non-infrastructure stdlib); no `os`, `sqlite3`, `serpapi`, `collector`, `investigation`, `analysis`, env reads. A positive-control test proves the rule rejects each forbidden import.

## 19. Probe exclusion and plan versions (2026-10-03)

- `market.inclusion` adds `development_probe` for observations from `RunSource.MANIFEST_LESS_PROBE`; nothing downstream changes, because Coverage and Claims already use included observations only.
- `market.ledger._plan_for`: recorded plan wins; otherwise the matching plan with the greatest `effective_from <= fetched_at`.
- `Config.active_plans` (status not `retired`) is what the collector executes, so two plan versions with identical parameters never cost two calls per run. The credit guard is unchanged.
- Config validation lets a retired plan name products no longer on the watchlist (provenance); active plans may not.
- Tests: `fixture_ledger` (conftest) re-labels the real 3 Oct rows as one production run (`fixture:` run ids) for tests that exercise production rules on real data; `probe_ledger` keeps the true probe semantics.

## 20. Pre-collection audit fixes (2026-10-03)

- Scheduled slot identity is canonical: `target_time` is converted to IST and spelled `YYYY-MM-DDTHH:MM+05:30`, so the same instant written in UTC or IST maps to one `run_id` and a replay spends nothing.
- `collector.json` (`collector-2`) adds `scheduled_slots_ist: ["09:00", "15:00", "21:00"]`. A scheduled request for any other time is refused before the credit read: no paid call, no manifest. This caps scheduled collection at 3 runs per IST day even if a scheduler is misconfigured. The credit guard is unchanged.
- `data/evidence/raw/` is gitignored: stored Shopping raws contain SerpApi account/archive URLs and are not publishable until the Terms are checked. Manifests stay trackable (statuses and ids only).
- Not yet built: the scheduler itself (GitHub Actions or local). Requirements recorded for it: cron at 03:30/09:30/15:30 UTC passing the exact IST slot as `--target-time`, a single `concurrency` group with `cancel-in-progress: false`, and an evidence-storage decision compatible with gitignored raws.
