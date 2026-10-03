# DealLens

DealLens watches a small set of laptop SKUs across Indian online sellers, records what prices it actually observed and when, and explains what today's price means using only that evidence.

## Products and sellers

**Tracked Product**:
A single exact SKU on the Watchlist, identified by brand plus its model key (e.g. ASUS `X1504VAP-BQ224WS`).
_Avoid_: product family, model line, item

**Model Key**:
The manufacturer's exact model/part code that distinguishes one SKU from its siblings.
_Avoid_: model name, SKU name

**Alias**:
A hand-confirmed spelling of a Model Key that counts as a match when found in listing text.
_Avoid_: synonym, keyword

**Watchlist**:
The fixed set of Tracked Products that scheduled collection observes.
_Avoid_: catalog, product list

**Storefront**:
The seller name exactly as Google Shopping reports it for a listing (e.g. "Shopsy By Flipkart", "ASUS eshop IN").
_Avoid_: source, merchant

**Seller**:
The retailer DealLens counts as one market participant; one or more Storefronts map to a Seller, and by default each Storefront is its own Seller.
_Avoid_: store, vendor, shop

**Related Storefronts**:
Storefronts that may belong to the same commercial seller but have not been shown to be either the same or independent (e.g. asus.com and ASUS eshop IN).
_Avoid_: duplicate sellers, sister stores

**Independent Seller Count**:
The number of Sellers for a Tracked Product after counting each group of Related Storefronts only once.
_Avoid_: seller count, number of stores

**Cross-border Seller**:
A Seller that lists prices converted from a foreign currency for shipment from abroad, and therefore is not part of the India market.
_Avoid_: foreign seller, importer

**Listing**:
One seller's offer page as Google Shopping exposes it in search results; DealLens has no verified way yet to recognise the same Listing twice.
_Avoid_: product, result, item, product id

**Google Identifier**:
An id Google attaches to a shopping result (such as its product id); provenance about the result, never the identity of a Listing or a Tracked Product.
_Avoid_: listing id, SKU id

**Listing Pin**:
A proposed human attestation that a specific Listing is a specific Tracked Product, for listings whose text lacks the Model Key; not usable until a Listing can be recognised reliably.
_Avoid_: manual match, override

## Observing

**Search**:
One paid or cached call to SerpApi and the Raw Response it produced.
_Avoid_: request, query, call

**Query Plan**:
The replaceable search parameters scheduled collection uses; one Query Plan may serve several Tracked Products, and none is ever assumed to be the permanently correct query.
_Avoid_: search config, query, product query

**Observation Run**:
One execution of collection (scheduled, manual or probe) that performs zero or more Searches.
_Avoid_: snapshot, job, batch

**Run Manifest**:
The immutable record of an Observation Run listing every attempted Search and how it ended: succeeded, repeat, failed or skipped.
_Avoid_: run log

**Orphan Raw Response**:
A Raw Response that belongs to no Run Manifest (for example, collection stopped before its manifest was written); kept for inspection, never counted as a run or as statistics.
_Avoid_: lost file, stray response

**Manifest-less Probe**:
A development fixture captured before Run Manifests existed; kept for audit, but its Observations never count toward statistics, Coverage or history.
_Avoid_: test run, sample

**Raw Response**:
The unmodified SerpApi JSON of one Search plus the envelope DealLens wrote around it (fetch time, parameters, search id).
_Avoid_: cache, dump, fixture (fixture is a testing role, not a domain concept)

**Observation**:
One shopping result row read from one Raw Response at one moment: a Storefront, a listing text and a listed price.
_Avoid_: price snapshot, data point, record

**Repeat Response**:
A Raw Response whose SerpApi search id has already been recorded; it adds no new Observations.
_Avoid_: duplicate, cache hit

**Indistinguishable Results**:
Observations in the same Observation Run with the same Storefront, listing text and prices; they carry no independent price evidence, so only one counts, without claiming they are the same Listing.
_Avoid_: duplicates, duplicate listings

**Listed Price**:
The price a Listing displayed at observation time, in INR, excluding shipping.
_Avoid_: available price, actual price, deal price

**List Price**:
The struck-through "before" price a Listing displayed, when it displayed one.
_Avoid_: MRP, old price, original price

## Deciding what counts

**Match**:
The deterministic outcome of attributing an Observation to Tracked Products: matched (exactly one product), unmatched (none) or ambiguous (more than one), with the evidence that justified it (Alias found in title, or Listing Pin).
_Avoid_: guess, similarity, best match

**Ambiguous Observation**:
An Observation whose evidence points to more than one Tracked Product; DealLens never chooses between them.
_Avoid_: conflict, multi-match

**Inclusion**:
Whether an Observation counts toward a Tracked Product's statistics, with every reason it does not.
_Avoid_: filter, validity

**Exclusion Reason**:
A named rule outcome that keeps an Observation out of statistics while keeping it in the Evidence Ledger (unmatched, ambiguous, cross-border, used/refurbished, unpriced, indistinguishable-in-run, outlier, orphan raw, integrity failed, development probe).
_Avoid_: rejection, error

**Outlier**:
An included-candidate Observation whose Listed Price is far from its peers (the same Tracked Product in the same Observation Run); a flag of suspicion, not proof of a wrong variant.
_Avoid_: wrong variant, bad data

**Stock Status**:
Whether a Listing could be bought at observation time; "unknown" unless a source actually stated it.
_Avoid_: availability

## Investigating

**Investigation**:
An on-demand, non-scheduled lookup of seller offers for one Listing, outside primary statistics.
_Avoid_: deep dive, inspection

**Offer**:
One seller entry inside an Investigation, with its own total price and stock text.
_Avoid_: store, listing

## Explaining

**Coverage**:
How much evidence DealLens holds for a Tracked Product: Observed Days, runs, Independent Seller Count and valid observations, and the level they reach.
_Avoid_: confidence score, certainty, accuracy

**Observed Day**:
The India (IST) calendar date on which an Observation was fetched; a reading of the fetch time, never a replacement for it. Counting them says on how many dates prices were observed, not how long a period is covered.
_Avoid_: date, day

**Coverage Level**:
The bucket Coverage falls into (No history, Limited history, Sufficient history), which decides which Claims are allowed.
_Avoid_: confidence level

**Observation Window**:
The time span whose Observations a calculation uses.
_Avoid_: period, range

**Claim**:
A deterministic, numbered statement computed from Observations, carrying the Observations that support it.
_Avoid_: insight, finding, fact

**Evidence**:
The traceable chain from a Claim to its Observations, their Raw Responses, the Storefront and the fetch time.
_Avoid_: source, proof

**Evidence Ledger**:
The user-visible list of every Observation for a Tracked Product, included or excluded, with its reasons and Evidence.
_Avoid_: audit log, history table

**Deal Analysis**:
The explanation of a Tracked Product's current price at a point in time: Coverage, allowed Claims and a summary written only from those Claims.
_Avoid_: verdict, recommendation, score
