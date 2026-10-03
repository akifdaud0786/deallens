"""PROTOTYPE — throwaway. Pure functions that push real SerpApi fixtures through the DealLens
domain model (docs/domain-model.md). No I/O except loading raw files; no LLM; no network.

Raw JSON -> Search -> Observations -> Match -> Inclusion -> Sellers -> Coverage -> Claims -> Summary
"""
import hashlib
import json
import re
import statistics
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
INR_MARKERS = {"INR", "₹"}


# ---------- Raw Response / Search ----------

def load_raw(path):
    path = Path(path)
    blob = path.read_bytes()
    doc = json.loads(blob.decode("utf-8"))
    meta, resp = doc["meta"], doc["response"]
    return {
        "raw_ref": path.name,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "kind": meta["kind"],
        "fetched_at": meta["fetched_at"],
        "params": meta["params"],
        "search_id": resp.get("search_metadata", {}).get("id"),
        "status": resp.get("search_metadata", {}).get("status"),
        "sensitivity": "private" if meta["kind"] == "immersive" else "shareable",
        "response": resp,
    }


def plan_for(params, plans):
    """Which Query Plan (id@version) produced these params, or None if unplanned (e.g. a probe)."""
    keys = ("engine", "q", "gl", "hl", "google_domain", "location")
    for p in plans:
        if all(params.get(k) == p["params"].get(k) for k in keys):
            return f'{p["plan_id"]}@{p["version"]}'
    return None


def observed_day(fetched_at_utc):
    """IST calendar date of the UTC fetch time. Derived; fetched_at is never replaced."""
    return datetime.fromisoformat(fetched_at_utc).astimezone(IST).date().isoformat()


# ---------- Prices ----------

_RUPEE_AMOUNT = re.compile(r"₹\s*([\d,]+(?:\.\d+)?)")
_PCT_OFF = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*off", re.I)


def parse_list_price(old_price):
    """Deterministic parse of Shopping `old_price`. Never uses `extracted_old_price`.
    Returns {"list_price_inr", "discount_pct", "parse_status"}."""
    if old_price is None:
        return {"list_price_inr": None, "discount_pct": None, "parse_status": "absent"}
    amounts = _RUPEE_AMOUNT.findall(old_price)
    pct = _PCT_OFF.search(old_price)
    if len(amounts) != 1:
        return {"list_price_inr": None, "discount_pct": None, "parse_status": "unparsed"}
    value = float(amounts[0].replace(",", ""))
    return {"list_price_inr": int(value) if value.is_integer() else value,
            "discount_pct": float(pct.group(1)) if pct else None,
            "parse_status": "parsed"}


# ---------- Observations ----------

def google_ids(product_link):
    """Google identifiers embedded in Shopping `product_link` (observed, undocumented). Provenance only."""
    out = {}
    if product_link:
        m = re.search(r"prds=([^&]+)", product_link)
        for part in (m.group(1).split(",") if m else []):
            k, _, v = part.partition(":")
            if k in ("catalogid", "productid", "headlineOfferDocid") and v:
                out[k] = v
    return out


def observations_from(raw, seen_search_ids):
    """Rows of one Shopping Raw Response. A Repeat Response (search_id already seen) yields none."""
    if raw["kind"] != "shopping" or raw["search_id"] in seen_search_ids:
        return []
    out = []
    for row in raw["response"].get("shopping_results", []):
        lp = parse_list_price(row.get("old_price"))
        out.append({
            "observation_id": f'{raw["raw_ref"]}#{row["position"]}',
            "raw_ref": raw["raw_ref"], "raw_sha256": raw["sha256"], "search_id": raw["search_id"],
            "fetched_at": raw["fetched_at"], "observed_day": observed_day(raw["fetched_at"]),
            "storefront": row.get("source"), "title": row.get("title", ""),
            "listing_ref": row.get("product_id"),  # provenance only: NOT a Listing identity
            "google_ids": google_ids(row.get("product_link")),
            "run_id": raw["run_id"], "run_source": raw["run_source"],
            "listed_price_inr": row.get("extracted_price"), "price_raw": row.get("price"),
            "list_price_raw": row.get("old_price"), **lp,
            "alternative_price": row.get("alternative_price"),
            "second_hand_condition": row.get("second_hand_condition"),
            "delivery_raw": row.get("delivery"), "rating": row.get("rating"), "reviews": row.get("reviews"),
            "stock_status": "unknown",
        })
    return out


# ---------- Match ----------

def _tokens(text):
    return re.findall(r"[A-Z0-9]+", text.replace("‎", "").replace("‏", "").upper())


def _contains_alias(title, alias, max_span=3):
    """Alias found as a whole run of adjacent tokens (so X1504VA never matches X1504VAP)."""
    target = "".join(_tokens(alias))
    toks = _tokens(title)
    for i in range(len(toks)):
        for n in range(1, max_span + 1):
            if "".join(toks[i:i + n]) == target:
                return True
    return False


def match(obs, products, pins):
    evidence = []
    for p in products:
        for a in p["aliases"]:
            if _contains_alias(obs["title"], a):
                evidence.append({"product_key": p["product_key"], "via": "alias", "alias": a})
    for pin in pins:
        if pin["listing_ref"] == obs["listing_ref"]:
            evidence.append({"product_key": pin["product_key"], "via": "pin"})
    candidates = sorted({e["product_key"] for e in evidence})
    outcome = {0: "unmatched", 1: "matched"}.get(len(candidates), "ambiguous")
    return {"outcome": outcome, "product_key": candidates[0] if outcome == "matched" else None,
            "candidates": candidates, "evidence": evidence}


# ---------- Sellers ----------

def seller_of(storefront, seller_map):
    return seller_map["storefront_to_seller"].get(storefront, storefront)


def independent_seller_count(seller_keys, seller_map):
    """Each unresolved Related Storefront group counts once; 'independent' groups count per member."""
    units = set()
    for s in seller_keys:
        group = next((g for g in seller_map["related_groups"]
                      if s in g["storefronts"] and g["status"] != "independent"), None)
        units.add(("group", group["group_id"]) if group else ("seller", s))
    return len(units)


# ---------- Inclusion ----------

def _is_cross_border(obs, cfg):
    alt = obs.get("alternative_price") or {}
    if alt.get("currency") and alt["currency"] not in INR_MARKERS:
        return True
    sf = (obs["storefront"] or "").lower()
    return any(p in sf for p in cfg["storefront_patterns"])


def classify(observations, products, pins, seller_map, cross_border, rules):
    """Adds match, seller_key and inclusion (included + reasons) to each observation. Nothing is dropped."""
    seen = set()  # Indistinguishable Results within one Observation Run
    for o in observations:
        m = match(o, products, pins)
        reasons = []
        if m["outcome"] != "matched":
            reasons.append(m["outcome"])
        if o["listed_price_inr"] is None:
            reasons.append("unpriced")
        elif not (o["price_raw"] or "").strip().startswith("₹"):
            reasons.append("non_inr")
        if _is_cross_border(o, cross_border):
            reasons.append("cross_border")
        t = o["title"].lower()
        if o.get("second_hand_condition") or any(k in t for k in rules["used_keywords"]):
            reasons.append("used_or_refurbished")
        key = result_fingerprint(o)
        if key in seen:
            reasons.append("indistinguishable_in_run")
        seen.add(key)
        o.update(match=m, seller_key=seller_of(o["storefront"], seller_map),
                 included=not reasons, reasons=reasons)
    _apply_outliers(observations, rules)
    return observations


def result_fingerprint(o):
    """Rows with the same fingerprint carry no independent price evidence within a run.
    product_id / Google offer ids are deliberately NOT part of it (they differ on identical rows)."""
    return (o["run_id"], o["storefront"], " ".join(_tokens(o["title"])), o["listed_price_inr"], o["list_price_inr"])


def _apply_outliers(observations, rules):
    by_product = {}
    for o in observations:
        if o["included"]:
            by_product.setdefault(o["match"]["product_key"], []).append(o)
    for pk, group in by_product.items():
        if len(group) < rules["outlier_min_sample"]:
            for o in group:
                o["outlier_check"] = f'not applied: {len(group)} < {rules["outlier_min_sample"]} observations'
            continue
        med = statistics.median(o["listed_price_inr"] for o in group)
        for o in group:
            dev = abs(o["listed_price_inr"] - med) / med
            o["outlier_check"] = f"deviation {dev:.0%} from median {med}"
            if dev > rules["outlier_threshold"]:
                o["included"] = False
                o["reasons"].append("outlier")


# ---------- Coverage ----------

def coverage(product_key, observations, raws, plans, seller_map, policy):
    """Coverage per Query Plan version. Cross-plan aggregation is an unresolved policy: never combined."""
    mine = [o for o in observations if o["included"] and o["match"]["product_key"] == product_key]
    by_plan = {}
    for o in mine:
        by_plan.setdefault(o["plan"], []).append(o)
    current = max(by_plan, key=lambda k: max(o["fetched_at"] for o in by_plan[k]), default=None)
    obs = by_plan.get(current, [])
    days = sorted({o["observed_day"] for o in obs})
    runs = sorted({o["run_id"] for o in obs})
    sellers = sorted({o["seller_key"] for o in obs})
    indep = independent_seller_count(sellers, seller_map)
    if len(days) >= policy["sufficient_min_days"] and len(runs) >= policy["sufficient_min_runs"] \
            and indep >= policy["sufficient_min_sellers"]:
        level = "sufficient_history"
    elif len(days) >= policy["limited_min_days"] and len(runs) >= 2:
        level = "limited_history"
    else:
        level = "no_history"
    runs_searched = sorted({r["run_id"] for r in raws if r.get("plan") == current})
    return {"product_key": product_key, "plan": current,
            "other_plans_not_combined": sorted(k for k in by_plan if k != current),
            "observed_days": days, "runs": runs, "runs_searched": runs_searched,
            "sellers": sellers, "independent_seller_count": indep,
            "valid_observations": len(obs), "level": level, "observation_ids": [o["observation_id"] for o in obs]}


# ---------- Claims ----------

LEVEL_RANK = {"no_history": 0, "limited_history": 1, "sufficient_history": 2}
FORBIDDEN = re.compile(r"all[- ]time|fake|will (drop|rise|fall)|best deal|guarantee", re.I)


def _prov(o):
    return {"observation_id": o["observation_id"], "raw_ref": o["raw_ref"], "raw_sha256": o["raw_sha256"],
            "search_id": o["search_id"], "storefront": o["storefront"], "fetched_at": o["fetched_at"]}


def _inr(x):
    s = f"{x:,.0f}" if float(x).is_integer() else f"{x:,.2f}"
    return "₹" + _indian_grouping(s)


def _indian_grouping(s):
    whole, _, frac = s.replace(",", "").partition(".")
    head, tail = whole[:-3], whole[-3:]
    head = ",".join(re.findall(r"\d{1,2}(?=(?:\d{2})*$)", head)) if head else ""
    out = f"{head},{tail}" if head else tail
    return out + (f".{frac}" if frac else "")


def build_claims(cov, observations):
    by_id = {o["observation_id"]: o for o in observations}
    obs = [by_id[i] for i in cov["observation_ids"]]
    pk = cov["product_key"]
    claims = []

    def add(kind, text, support, min_level, params):
        claims.append({"claim_id": f"{pk}:C{len(claims) + 1}", "kind": kind, "text": text, "params": params,
                       "supporting_observation_ids": [o["observation_id"] for o in support],
                       "provenance": [_prov(o) for o in support], "min_level": min_level})

    # Only exclusions attributable to this product (matched, then excluded for another reason).
    excluded = [o for o in observations if o["match"]["product_key"] == pk and not o["included"]]
    if obs:
        latest = max(o["fetched_at"] for o in obs)
        now = [o for o in obs if o["fetched_at"] == latest]
        low = min(o["listed_price_inr"] for o in now)
        lows = [o for o in now if o["listed_price_inr"] == low]
        add("current_lowest_listed",
            f"Lowest listed price observed in the latest run: {_inr(low)} at "
            f"{', '.join(sorted({o['storefront'] for o in lows}))} (stock status: unknown).",
            lows, "no_history", {"price_inr": low})
        add("seller_count",
            f"Observed at {len({o['seller_key'] for o in now})} storefront(s), counting as "
            f"{cov['independent_seller_count']} independent seller(s).",
            now, "no_history", {"storefronts": len({o['seller_key'] for o in now}),
                                "independent": cov["independent_seller_count"]})
        if len(now) >= 2:
            hi = max(o["listed_price_inr"] for o in now)
            text = (f"Listed prices in the latest run range from {_inr(low)} to {_inr(hi)}." if low != hi else
                    f"Observed listed prices are {_inr(low)} across the included sellers in the latest run.")
            add("current_spread", text, now, "no_history", {"low": low, "high": hi})
        for o in now:
            if o["list_price_inr"] is not None:
                add("listed_discount",
                    f"{o['storefront']} displayed a list price of {_inr(o['list_price_inr'])} next to "
                    f"{_inr(o['listed_price_inr'])}; DealLens has not verified that list price.",
                    [o], "no_history", {"list_price_inr": o["list_price_inr"], "listed_price_inr": o["listed_price_inr"]})
    if excluded:
        add("excluded_count",
            f"{len(excluded)} observation(s) attributed to this product were excluded from statistics "
            f"(see Evidence Ledger).", excluded, "no_history", {"count": len(excluded)})
    # History claims (change_since, observed_low/high/average) only above no_history — not reachable with fixtures.
    allowed = [c for c in claims if LEVEL_RANK[c["min_level"]] <= LEVEL_RANK[cov["level"]]]
    for c in allowed:
        assert not FORBIDDEN.search(c["text"]), c["text"]
    return allowed


def summary(cov, claims):
    if not cov["valid_observations"]:
        return ("No valid observations yet for this product under the current Query Plan. "
                "No price history yet.")
    days, runs = len(cov["observed_days"]), len(cov["runs"])
    head = (f"Based on the observations collected by DealLens ({cov['valid_observations']} valid observation(s), "
            f"{runs} run(s), {days} observed day(s), {cov['independent_seller_count']} independent seller(s)):")
    body = " ".join(f"{c['text']} [{c['claim_id']}]" for c in claims)
    tail = {"no_history": "No price history yet.",
            "limited_history": f"Limited history ({days} days).",
            "sufficient_history": ""}[cov["level"]]
    return f"{head} {body} {tail}".strip()


# ---------- Pipeline ----------

def run_pipeline(raw_paths, cfg):
    raws = sorted((load_raw(p) for p in raw_paths), key=lambda r: r["fetched_at"])
    seen, observations = set(), []
    for r in raws:
        # Probe fixtures have no Run Manifest: each file becomes its own run, explicitly labelled.
        # Production must read runs from Run Manifests, never infer them from file names.
        r["run_id"], r["run_source"] = f"probe:{r['raw_ref']}", "manifest_less_probe"
        r["plan"] = plan_for(r["params"], cfg.QUERY_PLANS)
        r["repeat_response"] = r["search_id"] in seen
        obs = observations_from(r, seen)
        for o in obs:
            o["plan"] = r["plan"]
            o["config_versions"] = {"seller_map": cfg.SELLER_MAP["version"], "rules": cfg.RULES["version"],
                                    "cross_border": cfg.CROSS_BORDER["version"], "plan": r["plan"]}
        r["observation_count"] = len(obs)
        observations += obs
        if r["search_id"]:
            seen.add(r["search_id"])
    classify(observations, cfg.TRACKED_PRODUCTS, cfg.LISTING_PINS, cfg.SELLER_MAP, cfg.CROSS_BORDER, cfg.RULES)
    analyses = []
    for p in cfg.TRACKED_PRODUCTS:
        cov = coverage(p["product_key"], observations, raws, cfg.QUERY_PLANS, cfg.SELLER_MAP, cfg.COVERAGE_POLICY)
        cl = build_claims(cov, observations)
        analyses.append({"product": p, "coverage": cov, "claims": cl, "summary": summary(cov, cl),
                         "summary_source": "template"})
    return {"raws": raws, "observations": observations, "analyses": analyses}
