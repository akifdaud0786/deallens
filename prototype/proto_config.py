"""PROTOTYPE configuration — throwaway. Mirrors docs/domain-model.md §2 (Configuration)."""

TRACKED_PRODUCTS = [
    {"product_key": "asus-x1504vap-bq224ws", "brand": "ASUS", "model_key": "X1504VAP-BQ224WS",
     "aliases": ["X1504VAP-BQ224WS"], "status": "provisional"},
    {"product_key": "asus-x1504vap-bq541ws", "brand": "ASUS", "model_key": "X1504VAP-BQ541WS",
     "aliases": ["X1504VAP-BQ541WS"], "status": "provisional"},
    {"product_key": "asus-x1504va-nj2324ws", "brand": "ASUS", "model_key": "X1504VA-NJ2324WS",
     "aliases": ["X1504VA-NJ2324WS"], "status": "provisional"},
]

LISTING_PINS = []  # usable only once Test 1 shows product_id is stable

QUERY_PLANS = [
    {"plan_id": "vivobook15-broad", "version": 1, "status": "provisional",
     "params": {"engine": "google_shopping", "q": "ASUS Vivobook 15", "gl": "in", "hl": "en",
                "google_domain": "google.co.in", "location": "Mumbai,Maharashtra,India"},
     "serves": [p["product_key"] for p in TRACKED_PRODUCTS],
     "rationale": "3 Oct broad fixture surfaced all three SKUs; bare model query returned none."},
]

SELLER_MAP = {
    "version": "seller-map-1",
    "storefront_to_seller": {},  # empty = identity mapping (each Storefront is its own Seller)
    "related_groups": [
        {"group_id": "asus-official", "storefronts": ["asus.com", "ASUS eshop IN"],
         "status": "unresolved", "note": "May be the same commercial seller; not proven."},
        {"group_id": "flipkart-family", "storefronts": ["Flipkart", "Shopsy By Flipkart"],
         "status": "unresolved", "note": "Shopsy is a Flipkart property; seller independence not proven."},
    ],
}

CROSS_BORDER = {
    "version": "cross-border-1",
    "storefront_patterns": ["desertcart", "ubuy", "microless"],  # small and documented
    "rule": "non-INR alternative_price present",
}

RULES = {
    "version": "rules-1",
    "used_keywords": ["refurbished", "renewed", "used", "open box", "open-box", "pre-owned"],
    "outlier_min_sample": 5,      # PROVISIONAL: open decision
    "outlier_threshold": 0.35,    # PROVISIONAL heuristic, not proof of wrong variant
    "indistinguishable_fingerprint": "run + storefront + normalized title + listed price + parsed list price",
}

COVERAGE_POLICY = {
    "limited_min_days": 2,
    "sufficient_min_days": 5, "sufficient_min_runs": 8, "sufficient_min_sellers": 2,
}
