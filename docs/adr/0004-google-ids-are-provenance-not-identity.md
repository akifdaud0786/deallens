---
status: accepted (dedup fingerprint provisional)
---

# Google identifiers are provenance, not Listing identity; repeated rows are collapsed as Indistinguishable Results

SerpApi's `product_id` looks like a listing key but is not one: in the 3 Oct 2026 fixtures it equals Google's `catalogid` whenever the row belongs to a catalog cluster (80/80 rows), one value spanned four rows with four different prices, and six LowestRate rows with identical title and price carried six different `product_id`s and six different `headlineOfferDocid`s. We therefore keep all Google ids only as provenance, never as identity, dedup key or history anchor, and collapse rows only when they carry no independent price evidence: same Observation Run, Storefront, normalized title, Listed Price and List Price. A future reader may expect `product_id`-based dedup or listing tracking; that was rejected because it would both miss real repeats and silently merge different prices.

## Consequences

- Two genuinely different listings from one Storefront with identical title and prices count once. This changes counts and averages, never the observed low, high or spread.
- Listing Pins stay provisional until some reference is shown to identify one listing over time.
