"""PROTOTYPE runner — throwaway. Pushes data/cache Shopping fixtures through the domain model,
prints every stage, and writes prototype/out/PROTOTYPE_report.html (wipe freely).

    python prototype/run_prototype.py
"""
import html
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import deallens_proto as dl  # noqa: E402
import proto_config as cfg  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = sorted((ROOT / "data" / "cache").glob("*_shopping.json"))


def main():
    res = dl.run_pipeline(FIXTURES, cfg)
    print("== Raw Responses / Searches ==")
    for r in res["raws"]:
        print(f"  {r['raw_ref']}  search_id={r['search_id']}  fetched_at={r['fetched_at']}  plan={r['plan']}"
              f"  repeat={r['repeat_response']}  observations={r['observation_count']}")
    obs = res["observations"]
    print(f"\n== Observations: {len(obs)} ==")
    print("  match outcomes:", dict(Counter(o["match"]["outcome"] for o in obs)))
    print("  included:", sum(o["included"] for o in obs), "excluded:", sum(not o["included"] for o in obs))
    print("  exclusion reasons:", dict(Counter(r for o in obs for r in o["reasons"])))
    for a in res["analyses"]:
        c = a["coverage"]
        print(f"\n== {a['product']['model_key']} ({a['product']['status']}) ==")
        print(f"  coverage: level={c['level']} days={c['observed_days']} runs={len(c['runs'])} "
              f"storefronts={c['sellers']} independent={c['independent_seller_count']} "
              f"valid={c['valid_observations']} plan={c['plan']} not_combined={c['other_plans_not_combined']}")
        for cl in a["claims"]:
            print(f"  [{cl['claim_id']}] ({cl['kind']}, min={cl['min_level']}) {cl['text']}")
            for p in cl["provenance"]:
                print(f"      <- {p['observation_id']} search_id={p['search_id']} {p['storefront']} {p['fetched_at']}")
        print("  SUMMARY:", a["summary"])
    out = Path(__file__).parent / "out"
    out.mkdir(exist_ok=True)
    (out / "PROTOTYPE_report.html").write_text(render(res), encoding="utf-8")
    print(f"\nwrote {out / 'PROTOTYPE_report.html'}")


def render(res):
    e = html.escape
    parts = ["""<!doctype html><meta charset="utf-8"><title>DealLens prototype</title>
<style>body{font:14px/1.5 system-ui;margin:24px;max-width:1200px;color:#1a1a1a;background:#fff}
table{border-collapse:collapse;width:100%;margin:8px 0 24px}td,th{border:1px solid #ddd;padding:4px 6px;text-align:left;vertical-align:top}
th{background:#f4f4f4}.ex{color:#888}.tag{background:#eef;border-radius:4px;padding:0 4px;margin-right:4px}
.note{background:#fff7e0;padding:8px 12px;border-left:4px solid #e0a800}</style>
<h1>DealLens — PROTOTYPE (throwaway)</h1>
<p class="note">Question: does the domain model (Search → Observation → Match → Inclusion → Sellers → Coverage → Claims)
hold up on the real 3 Oct 2026 SerpApi fixtures? Template summaries only, no LLM. Nothing here is invented: every row is a real fixture row.</p>"""]
    for a in res["analyses"]:
        c = a["coverage"]
        parts.append(f"<h2>{e(a['product']['brand'])} {e(a['product']['model_key'])} "
                     f"<span class=tag>{e(a['product']['status'])}</span></h2>")
        parts.append(f"<p><b>Deal Intelligence (template):</b> {e(a['summary'])}</p>")
        parts.append(f"<p><b>Coverage:</b> level <b>{e(c['level'])}</b> · observed days {len(c['observed_days'])} "
                     f"({e(', '.join(c['observed_days']))}) · runs {len(c['runs'])} · storefronts {e(', '.join(c['sellers']))} · "
                     f"independent sellers {c['independent_seller_count']} · valid observations {c['valid_observations']} · "
                     f"plan {e(str(c['plan']))}</p>")
        parts.append("<table><tr><th>Claim</th><th>Text</th><th>Evidence</th></tr>")
        for cl in a["claims"]:
            ev = "<br>".join(f"{e(p['observation_id'])} · {e(p['storefront'])} · {e(p['fetched_at'])} · search {e(p['search_id'])}"
                             for p in cl["provenance"])
            parts.append(f"<tr><td>{e(cl['claim_id'])}<br><small>{e(cl['kind'])}</small></td><td>{e(cl['text'])}</td><td><small>{ev}</small></td></tr>")
        parts.append("</table>")
    parts.append("<h2>Evidence Ledger — all observations</h2><table><tr><th>Observation</th><th>Storefront</th><th>Title</th>"
                 "<th>Listed</th><th>List price (parsed)</th><th>Match</th><th>Included / reasons</th><th>fetched_at (UTC) / IST day</th></tr>")
    for o in res["observations"]:
        m = o["match"]
        mtxt = m["outcome"] + (f": {', '.join(m['candidates'])}" if m["candidates"] else "")
        parts.append(f"<tr class='{'' if o['included'] else 'ex'}'><td>{e(o['observation_id'])}</td><td>{e(str(o['storefront']))}</td>"
                     f"<td>{e(o['title'][:70])}</td><td>{e(str(o['price_raw']))}</td>"
                     f"<td>{e(str(o['list_price_raw']))} → {e(str(o['list_price_inr']))}</td><td>{e(mtxt)}</td>"
                     f"<td>{'included' if o['included'] else e(', '.join(o['reasons']))}</td>"
                     f"<td>{e(o['fetched_at'])}<br>{e(o['observed_day'])}</td></tr>")
    parts.append("</table>")
    return "\n".join(parts)


if __name__ == "__main__":
    main()
