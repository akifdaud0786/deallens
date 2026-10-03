# SerpApi Google Shopping for India: research notes for DealLens

Researched 2026-10-03 from primary sources only: serpapi.com doc pages, the `serpapi/*` GitHub repos, and the `serpapi/public-roadmap` issues linked from SerpApi's own release notes. **No live SerpApi API calls were made.** JSON quoted below is the **doc example** (US, BR or TR playground samples). It is not observed India behavior.

## Summary

- **India is a supported Google Shopping country.** `gl=in` appears on the [Google Shopping countries list](https://serpapi.com/google-shopping-countries), and `google.co.in` appears on the [Google domains list](https://serpapi.com/google-domains). The default domain is `google.com` ([Shopping API](https://serpapi.com/google-shopping-api)), so DealLens has to set `google_domain=google.co.in` itself.
- **One page only.** "Google Shopping's current layout does not support offset pagination: the `start` parameter is ignored and every request returns the first page of results (around 40 items)". `num` does not change the page size either ([Shopping API, `start`](https://serpapi.com/google-shopping-api)). There is no documented `page`, `tbs` or `currency` parameter.
- **The cross-seller snapshot comes from the Immersive Product API.** Each shopping result carries `immersive_product_page_token` and `serpapi_immersive_product_api`. That call returns `product_results.stores[]`, a per-seller list with `name`, `price`, `extracted_price`, `original_price`, `shipping`, `total`, `extracted_total`, `rating` and `reviews`. It returns 3–5 stores by default and up to 13 with `more_stores=true`, then pages with `stores_next_page_token` ([Immersive Product API](https://serpapi.com/google-immersive-product-api)).
- **SerpApi documents no price history, "typical price" or price-insight field for Shopping or Immersive Product.** "Price Insights" exists only under Google Flights in the docs nav. DealLens has to build the history itself by storing snapshots over time.
- **Cost model:**
  - Every successful search costs 1 credit, whatever the engine or result count. A Shopping search plus an Immersive lookup is therefore 2 credits per product snapshot.
  - Cached searches are free. A cache hit needs exactly identical params, and the cache expires after 1h.
  - `no_cache=true` forces a fresh, billed search.
  - Free plan: 250 searches per month and 50 per hour.
  - Sources: [pricing](https://serpapi.com/pricing), [FAQ](https://serpapi.com/faq), and the `no_cache` text on [Shopping API](https://serpapi.com/google-shopping-api).
- **Stored searches can be re-read for 31 days.** The JSON can be fetched again by `search_id` through the [Searches Archive API](https://serpapi.com/searches-archive-api). The docs do not say whether archive fetches cost credits. Raw responses still belong in DealLens's own DB.
- **Seller identity is not stable across time:**
  - `product_id` is documented as a "Unique Google product identifier".
  - Immersive tokens embed Google session data. Decoding the doc example token shows `ei`, `catalogid`, `gpcid`, `query`, `gl`, `hl` and `uule`.
  - Nothing says how long a token lives. Whether `product_id` or `catalogid` is stable day-to-day for `gl=in` has to be tested live.
- **India-specific formatting is undocumented.** No doc page shows ₹ or lakh-style grouping like `₹1,29,999`. Locale-aware parsing is shown for TRY and BRL ("R$ 449,91" → `449.91`), but `extracted_price` for INR has to be verified live.

---

## 1. Google Shopping API request parameters (`engine=google_shopping`)

Source for every row: [serpapi.com/google-shopping-api](https://serpapi.com/google-shopping-api).

| Param | Documented behavior | DealLens notes |
|---|---|---|
| `q` | Required unless `shoprs` is given | Product query |
| `location` | City-level location is recommended. "If location is omitted, the search may take on the location of the proxy." It cannot be combined with `uule`. Canonical names come from the [Locations API](https://serpapi.com/locations-api), which is free. | Set an Indian city such as Mumbai or Bengaluru. Look up the exact canonical string via `locations.json?q=Mumbai`, which costs nothing. |
| `uule` | Encoded location. A coordinates-based `uule` needs a matching `gl`. | Alternative to `location` |
| `google_domain` | "It defaults to `google.com`" | Use `google.co.in` ([domains list](https://serpapi.com/google-domains)) |
| `gl` | Two-letter country code, checked against the [Shopping countries list](https://serpapi.com/google-shopping-countries) | `in` is listed |
| `hl` | Language code, optionally with a region, e.g. `en-gb` | `en`. `hi` and `hi-in` are on the [languages list](https://serpapi.com/google-languages). |
| `shoprs` | Filter token taken from `filters[].options[].shoprs`. Combine tokens with `\|\|`. | |
| `min_price` / `max_price` | Price range. Overrides the same filter inside `shoprs`. | The unit is presumably local currency, but the docs don't say |
| `sort_by` | `1` = price low→high, `2` = high→low | |
| `free_shipping`, `on_sale`, `small_business` | Boolean filters | |
| `safe` | `active` / `off` | |
| `start` | **Ignored** on the current layout. The first page is about 40 items, and `num` "does not change the number of results returned". | Treat each query as one page of about 40 items. Changelog: [roadmap #3314](https://github.com/serpapi/public-roadmap/issues/3314), closed 2026-07-31. |
| `device` | `desktop` (default), `tablet`, `mobile` | Pin it to keep snapshots consistent |
| `no_cache` | Forces a fresh fetch. The cache is served only for identical params, expires after 1h, and cached hits are free. Don't combine with `async`. | Use `true` for scheduled snapshots so you never store a stale cached copy |
| `async` | Submit now, collect later through the Searches Archive API. Don't combine with `no_cache`. | |
| `output` | `json` (default), `html`, `md` | |
| `json_restrictor` | Limits the fields returned in the output ([docs](https://serpapi.com/json-restrictor)) | Shrinks the payload. Not documented to affect cost. |
| `zero_trace` | Enterprise only | n/a |

**Not documented as Shopping params:** `currency`, `tbs`, `page`, `direct_link`, and a configurable `num`. The [official MCP engine schema for google_shopping](https://raw.githubusercontent.com/serpapi/serpapi-mcp/main/engines/google_shopping.json) also lists `as_*` advanced-search params and `start`. The doc page does not show those `as_*` params, so treat them as unverified for Shopping.

Results per page are about 40, with no offset pagination. To cover more products, change the query or apply `shoprs`/`sort_by` filters.

## 2. Response fields

The field lists come from [shopping-results](https://serpapi.com/shopping-results), [inline-shopping-results](https://serpapi.com/inline-shopping-results) and [shopping-categorized-shopping-results](https://serpapi.com/shopping-categorized-shopping-results), each of which has a "JSON Structure Overview".

| Field | Documented? | Type / notes | Source | Must verify live for `gl=in` |
|---|---|---|---|---|
| `product_id` | Yes: `shopping_results`, `categorized_*` | String, "Unique Google product identifier" | [shopping-results](https://serpapi.com/shopping-results) | **Yes.** Is it stable across days and across queries for the same SKU? |
| `title` | Yes | String | same | No |
| `source` | Yes: all three | String, seller name | same | Yes. Is the name normalized (e.g. "Amazon.in" vs "Amazon")? |
| `source_icon` | Yes: shopping, categorized | String URL | same | No |
| `price` | Yes: all three | String, e.g. "$5.88" | same | **Yes.** ₹ symbol and lakh grouping |
| `extracted_price` | Yes: all three | Numeric (float or int) | same | **Yes.** Does "₹1,29,999" parse to 129999? |
| `old_price` / `extracted_old_price` | Yes: all three | String / Numeric, the price before discount | same | Yes. How often is it present in India? |
| `alternative_price` {`price`, `extracted_price`, `currency`} | Yes: shopping, categorized | Price in another currency. Doc example: TRY price with an EUR alternative. | same | Yes. Does it ever appear for `gl=in`? |
| `installment` {`price`, `extracted_price`, `period`} | Yes: all three | Monthly price. **The main `price` can itself be the monthly figure**: the doc example has `price` "$20.99/mo" and `extracted_price` 20.99. | same | **Yes.** No-cost EMI listings could pollute the price series |
| `rating` | Yes | Float, can be `null` (tablet doc example) | same | No |
| `reviews` | Yes | Integer | same | No |
| `delivery` | Yes: all three | String, e.g. "Free delivery on $45+" | same | Yes (wording) |
| `product_link` | Yes: shopping, categorized | String, "Link to the Google item page". Google discontinued product pages, and SerpApi's tracking issue proposed removing or replacing the field ([#3083](https://github.com/serpapi/public-roadmap/issues/3083)). | same | Yes. Is it useful at all? |
| `link` | **Only `inline_shopping_results`**, the ads block | String, "Direct link to the Google item page", plus `tracking_link` | [inline-shopping-results](https://serpapi.com/inline-shopping-results) | Organic results have no documented merchant link. Per-seller merchant links are `stores[].link` in the Immersive API. |
| `multiple_sources` | Yes: shopping, categorized | "True - If more than one seller available" | [shopping-results](https://serpapi.com/shopping-results) | Yes. It is the trigger for an Immersive lookup. |
| `tag` | Yes | String, e.g. "SALE", "45% OFF" | same | No |
| `extensions` | Yes | Array of strings | same | No |
| `badge` | Yes: shopping, categorized | String, e.g. "Small business" | same | No |
| `second_hand_condition` | Yes: all three | String, "used" or "refurbished" | same | Yes. Filter these rows out |
| `immersive_product_page_token` | Yes: shopping, categorized | String. Every result should have it since [#2815](https://github.com/serpapi/public-roadmap/issues/2815), fixed 2025-08-21. | same | Yes. Presence rate on `gl=in` |
| `serpapi_immersive_product_api` | Yes: shopping, categorized | String, a ready-made SerpApi URL | same | No |
| `serpapi_product_api` | Named in the page intro, **missing from the structure overview** | Probably legacy ([#3083](https://github.com/serpapi/public-roadmap/issues/3083)) | same | Ignore |
| `snippet`, `thumbnail(s)`, `serpapi_thumbnail(s)`, `tagline`, `position` | Yes | Various | same | No |
| `block_position` | Inline only | `top` / `bottom` | [inline](https://serpapi.com/inline-shopping-results) | No |
| `filters[]` {`type`, `input_type`, `options[]{text, shoprs, serpapi_link}`} | Yes | Includes "Carousel Filters" with `selected` | [shopping-filters-results](https://serpapi.com/shopping-filters-results) | No |
| Price insights, typical price, price history | **Not documented** for Shopping or Immersive | n/a | Searched every doc page fetched. Only Google Flights has "Price Insights". | n/a |

## 3. Google Immersive Product API (`engine=google_immersive_product`)

Source: [serpapi.com/google-immersive-product-api](https://serpapi.com/google-immersive-product-api) and the [Stores sub-page](https://serpapi.com/google-immersive-product-stores).

- **Params:**
  - `page_token` (required)
  - `more_stores` (`1`/`true`, which returns up to 13 stores instead of the default 3–5)
  - `next_page_token`, set from `stores_next_page_token`
  - `no_cache`, `async`, `output`, `json_restrictor`, `zero_trace`
- **No `gl`, `hl`, `location` or `google_domain` param is documented.** Decoding the doc example token (base64 JSON) shows `"gl":"us","hl":"en","uule":null,"query":...`. The locale therefore appears to come from the Shopping search that produced the token. This is an inference from the doc example, not a documented rule.
- **Where tokens come from:** `immersive_product_page_token` in Shopping results. The Shopping API also provides a prebuilt `serpapi_immersive_product_api` URL. `more_options[].serpapi_link` and `variants[].items[].serpapi_link` inside Immersive results lead to related products.
- **Token expiry is not documented.** The token embeds a Google `ei` value, which looks like a session id, so it may go stale. That has to be tested live.
- **Per-seller offers:** `product_results.stores[]` contains:
  - `name`, `logo`, `link` (the merchant URL), `title`, `rating`, `reviews`, `payment_methods`, `tag` (e.g. "Best price"), `details_and_offers[]`, `coupon`, `discount`
  - `price` / `extracted_price`, `original_price` / `extracted_original_price`
  - `monthly_payment_duration`, `installments_description`, `down_payment`
  - `estimated_tax` / `extracted_estimated_tax`, `shipping` / `shipping_extracted`, `total` / `extracted_total`
- **Product-level fields:**
  - `title`, `brand`, `rating`, `reviews`, `critic_ratings[]`, `price_range` (string, e.g. "$1,797-$2,200")
  - `about_the_product`, `top_insights` (review insights, not price insights), `ratings[]` (star histogram), `user_reviews[]`, `videos[]`, `discussions_and_forums[]`, `more_options[]`, `variants[]`
- **No price history or price-insight fields are documented.**
- **Credit cost:** no engine-specific price is documented, so the general rule applies: 1 successful search = 1 credit ([pricing FAQ](https://serpapi.com/pricing)). Cache rules are identical to Shopping: 1h, free on a hit. Each `next_page_token` page is presumably another search, but that is not stated explicitly.
- **Fit for "same product across sellers" snapshots:** yes, this is the documented mechanism. One Shopping search finds the product and the token, and one Immersive call (with `more_stores=true`) returns the seller list with prices. Reliability caveats are in SerpApi's recent [release notes](https://serpapi.com/google-immersive-product-api/release-notes). They include fixes for "Malformed product_results" (2026-10-01), "Intermittent Empty Results" (2026-04-28) and "No results found" (2026-05-14).
- **Doc example showing locale parsing (BR):** `"price": "R$ 124,98"` → `"extracted_price": 124.98`, and `"total": "R$ 449,91"` → `449.91`.

## 4. Credits, cache, limits, archive

- **Counting:** "Only successful searches are counted towards your monthly searches. Cached, errored, and failed searches are not." The number of results returned has no effect: one response costs 1 credit ([FAQ](https://serpapi.com/faq), [pricing](https://serpapi.com/pricing)).
- **Cache:**
  - It is served only when the query and all params are exactly the same.
  - "Cache expires after 1h. Cached searches are free."
  - `no_cache=true` disallows the cache.
  - Source: the `no_cache` text on the [Shopping](https://serpapi.com/google-shopping-api), [Immersive](https://serpapi.com/google-immersive-product-api) and [Search API](https://serpapi.com/search-api) pages.
- **Plans** ([pricing](https://serpapi.com/pricing)):

  | Plan | Price | Searches per month | Throughput per hour |
  |---|---|---|---|
  | Free | $0 | 250 | 50 |
  | Starter | $25 | 1,000 | 200 |
  | Developer | $75 | 5,000 | 1,000 |
  | Production | $150 | 15,000 | 3,000 |
  | Big Data | $275 | 30,000 | 6,000 |

- **Throughput rule:** "The hourly throughput limit for plans with under 1 million searches per month is 20% of your plan volume". There is no other specific rate limit ([FAQ](https://serpapi.com/faq)). Unused searches do not roll over.
- **Usage check without spending credits:** the [Account API](https://serpapi.com/account-api) is "free of charge". It returns `plan_searches_left`, `this_hour_searches` and `account_rate_limit_per_hour`.
- **Searches Archive API:** `GET https://serpapi.com/searches/{search_id}.json`. It retrieves JSON or HTML "up to 31 days after the search has been completed" ([Searches Archive API](https://serpapi.com/searches-archive-api)), and the FAQ says SerpApi stores files for 31 days. **Whether archive fetches consume credits is not stated.**
- **Budget implication on the free plan:** a 2-credit snapshot per product means roughly 125 product snapshots per month. For example, 4 products once a day for a month is 4 × 2 × 30 = 240 credits.

## 5. Indian locale specifics

- **Documented:**
  - `gl=in` ([Shopping countries](https://serpapi.com/google-shopping-countries))
  - `google.co.in` ([domains](https://serpapi.com/google-domains))
  - `hl=hi` and `hl=hi-in` ([languages](https://serpapi.com/google-languages))
- **Not documented anywhere:** the ₹ symbol, INR, "Rs.", or lakh/crore grouping such as `₹1,29,999`. Searches for these terms across the fetched docs and the public-roadmap issues found nothing.
- **Indirect evidence (doc examples, not India):**
  - Comma-grouped thousands parse correctly: `"TRY 28,782.94"` → `28782.94` ([shopping-results](https://serpapi.com/shopping-results)).
  - Comma-decimal BRL also parses correctly ([immersive](https://serpapi.com/google-immersive-product-api)).
  - **Lakh grouping (`1,29,999`) and a ₹ with no decimals, e.g. `₹62,999`, are untested in the docs.**
- **Localization accuracy risk:** SerpApi's own issue [#3973](https://github.com/serpapi/public-roadmap/issues/3973) questions "whether our current localization parameters fully replicate the behavior of searches performed from within the target country" for BR and ES. The same could apply to IN.

## 6. Official agent integrations

- **serpapi-search-tools (Python)**, repo [github.com/serpapi/serpapi-search-tools-python](https://github.com/serpapi/serpapi-search-tools-python). The URL `serpapi-search-tools` without `-python` returns 404.
  - **Install:** `pip install serpapi-search-tools`, with extras such as `[openai-agents]`, `[langchain]`, `[claude-agent-sdk]`, `[pydantic-ai]` and `[crewai]`. Set the key with `SERPAPI_API_KEY` (or `SERPAPI_KEY`).
  - **Shopping:** the `shopping_search` tool covers `google_shopping`, `amazon`, `walmart` and `ebay`.
  - **Gaps for DealLens:**
    - **No `google_immersive_product` tool**, so per-seller offers are not available through it.
    - `default_params` can pin locale, for example `{"gl":"in","hl":"en","google_domain":"google.co.in"}`. A multi-engine tool sends those defaults to every allowed engine, so restrict `allowed_engines` to Google Shopping.
- **SerpApi MCP**, repo [github.com/serpapi/serpapi-mcp](https://github.com/serpapi/serpapi-mcp).
  - **Setup:** it is hosted at `https://mcp.serpapi.com/mcp` with `Authorization: Bearer <key>`. For Claude Code: `claude mcp add --transport http serpapi https://mcp.serpapi.com/mcp --header "Authorization: Bearer YOUR_SERPAPI_API_KEY"`. Self-hosting uses `uv`, and there is also a `.mcpb` bundle for Claude Desktop.
  - **Tools:** a single `search` tool that takes any engine's params, plus the opt-in `search_table` and `search_dashboard` tools.
  - **Engine coverage:** per-engine schemas are exposed as `serpapi://engines/<engine>`. The repo's [`engines/`](https://github.com/serpapi/serpapi-mcp/tree/main/engines) folder includes `google_shopping.json`, `google_shopping_light.json`, `google_shopping_filters.json` and **`google_immersive_product.json`**, so both DealLens calls are reachable through MCP.
  - The default engine is `google_light`, so pass `engine` explicitly.

---

## Documented vs must-verify-live

**Documented (safe to build on):**
- Params: `gl`, `hl`, `google_domain`, `location`, `sort_by`, `min_price`/`max_price` and `shoprs`. `start` is ignored, a page is about 40 results, and `num` has no effect.
- Shopping result fields and their types as listed in the table above.
- Immersive `stores[]` schema and `more_stores`, which returns up to 13 stores.
- 1 credit per successful search, free cached hits, 1h cache, `no_cache` semantics, 31-day archive.

**Only a live `gl=in` test can settle:**
1. Whether `price` contains ₹ and how `extracted_price` parses lakh grouping (`₹1,29,999` → 129999?) and prices without decimals.
2. Whether `currency` or `alternative_price` ever appears for Indian results.
3. How many results come back, and whether `categorized_shopping_results` replaces `shopping_results` for typical electronics queries in India.
4. **Whether `product_id` is stable** across days and across slightly different queries for the same SKU. This is the core of the time series.
5. Whether `immersive_product_page_token` is present on every IN result, and whether the decoded token carries `gl:"in"`.
6. **Token lifetime:** does a token from day N still work on day N+1 with `no_cache=true`?
7. How many `stores[]` Immersive returns for IN products, both default and with `more_stores`. Also how sellers like Amazon.in, Flipkart, Croma and Reliance Digital are named, and whether `stores[].link` points to the merchant directly.
8. Whether `installment` or EMI prices replace the headline `price` on IN listings.
9. Whether `min_price`/`max_price` are interpreted in INR.
10. Whether `location` changes results materially versus `gl=in` alone, given the proxy-location caveat.
11. Whether a Searches Archive fetch decrements credits. Check `this_month_usage` in the Account API before and after.

## Recommended minimal live test plan (4 credits, 1 spare)

Before any credit is spent:
- Call the free [Account API](https://serpapi.com/account-api) and record `plan_searches_left`.
- Get the location canonical name from the free `https://serpapi.com/locations.json?q=Mumbai&limit=3`.

| # | Call | Exact params | Record |
|---|---|---|---|
| 1 (1 credit) | Shopping search | `engine=google_shopping&q=Apple iPhone 15 128GB Black&gl=in&hl=en&google_domain=google.co.in&location=<Mumbai canonical>&device=desktop&no_cache=true` | Save the full raw JSON. Record: count of `shopping_results` and `categorized_shopping_results`; the `price` and `extracted_price` pairs, especially any value ≥ 1 lakh; presence of `old_price`, `alternative_price`, `installment` and `second_hand_condition`; `source` names; `multiple_sources`; `product_id`s; whether every item has `immersive_product_page_token`; the decoded token's `gl`/`hl`; `search_metadata.id`. |
| 2 (0 credits expected) | Repeat #1 within 1h **without** `no_cache` | Same params minus `no_cache` | Confirm the call is served from cache: `this_month_usage` in the Account API is unchanged. Note any `search_metadata` field that signals a cache hit. |
| 3 (1 credit) | Immersive | `engine=google_immersive_product&page_token=<token of the top multiple_sources=true result from #1>&more_stores=true&no_cache=true` | `stores[]` count; each store's `name`, `price`, `extracted_price`, `original_price`, `shipping`, `total`, `extracted_total` and `link` domain; `price_range`; presence of `stores_next_page_token`. |
| 4 (1 credit, next day) | Shopping repeat | The same params as #1, including `no_cache=true` | Compare `product_id`s and `source`s with day 1 to measure ID stability and ranking drift. |
| 5 (1 credit, next day) | Immersive using the **day-1 token** | The same as #3 with the old token | Tests token expiry. If it fails, the design must re-search before every seller snapshot. |

Also fetch `https://serpapi.com/searches/<id from #1>.json` once and check the Account API afterward to settle whether archive fetches cost credits. Do this only if the spare credit allows.

## Open questions

- Token lifetime and validity across days or IPs: undocumented.
- Whether `product_id` is a durable SKU key for India, or whether DealLens needs fuzzy title matching as a fallback.
- Whether Searches Archive retrievals are free: the docs don't say.
- Whether `json_restrictor` or `output=md` affects cost: not stated, and probably not.
- `as_*` params appear in the MCP schema for google_shopping but not on the doc page. They are unverified.
- What the "around 40 items" first page looks like for IN, and whether India's layout differs (localization caveat, [#3973](https://github.com/serpapi/public-roadmap/issues/3973)).
- Whether the [Google Shopping Light API](https://serpapi.com/google-shopping-light-api) is cheaper or faster for discovery. It was not investigated in depth here, and its fields would need comparing.
