# SerpApi India Hackathon 2026: submission text for DealLens

Copy each block into the matching field of the submission form.

## Project name

DealLens

## Track

Track 4: Commerce & Market Intelligence

## One-line description

An evidence-backed commerce intelligence agent that tracks the same product across Indian sellers, builds a price history from repeated Google Shopping observations, and explains whether today's price is actually good, based only on the data it has observed.

## Description

Shoppers see a price like ₹66,990 but cannot tell whether it is a good price. The cheapest listing is not the whole story, listings for different variants of the same laptop family are easily mixed up, and "great deal" labels are rarely backed by evidence.

DealLens watches a small watchlist of exact laptop SKUs in India. Three times a day a GitHub Actions job makes one bounded Google Shopping call through SerpApi and stores the raw response as immutable, hash-checked evidence with a Run Manifest. Each result row becomes an Observation, is attributed to a product only by deterministic exact-model matching (no fuzzy, embedding or LLM matching), and keeps an explicit reason whenever it is excluded (cross-border reseller, used/refurbished, ambiguous, development probe and others).

From those observations DealLens computes deterministic claims (lowest listed price, spread, change since a date, observed low/high/average) that are only allowed once enough evidence exists: observed calendar days, production runs and independent sellers are always shown next to the conclusion. The UI answers one question first: "Is this a good price?" Today the honest answer for the first production run is "Not enough evidence yet", with what DealLens knows, what it does not know, and the exact SerpApi evidence behind every statement.

DealLens never claims an all-time low, a fake discount or a future price, and never presents a seller's displayed list price as verified.

## How SerpApi is used

- **Google Shopping API (primary source):** `engine=google_shopping`, `gl=in`, `google_domain=google.co.in`, `location=Mumbai,Maharashtra,India`. One broad query per scheduled slot (09:00, 15:00, 21:00 IST) returns about 40 Indian listings; every price, seller, coverage figure and claim in DealLens comes from these results. Repeated observations form the price history.
- **Google Immersive Product API (on-demand, supplementary):** a CLI investigation of one listing's seller offers (total price, stock text). Its raw responses are stored privately and never enter statistics.
- **Account API:** a free credit check before every paid call. One `CallBudget` gate, a 60-credit floor, a per-run call cap and no retry after timeouts keep the scheduled collection at one credit per slot (21 credits for 7 days).
- Lessons from live SerpApi responses are encoded as rules: `extracted_old_price` returned the discount percentage, so DealLens parses `old_price` itself; `product_id` turned out to be a Google catalog cluster, so it is kept as provenance only.

## Tech stack

Python (standard library HTTP, SQLite), SerpApi, FastAPI (read-only API), React + TypeScript + Vite + Tailwind CSS + Recharts, Streamlit (alternative UI), pytest (246 tests), GitHub Actions (scheduled collection).

## AI tools used (disclosure)

DealLens was built with Claude Code (Anthropic), following Matt Pocock's engineering skills workflow: research, grilling, domain modeling, prototype, codebase design, test-driven development and code review. The working documents are in `docs/`. These tools were used during development only; DealLens has no runtime LLM: every number and summary is produced by deterministic code.

## Links

- Repository: https://github.com/akifdaud0786/deallens
- Live read-only site: https://akifdaud0786.github.io/deallens/
- Demo video: _paste the unlisted YouTube / Google Drive link here_
