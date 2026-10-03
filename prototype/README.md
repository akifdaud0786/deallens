# PROTOTYPE — throwaway

Question: does the domain model in `docs/domain-model.md` hold up on the real 3 Oct 2026 SerpApi fixtures?

- `deallens_proto.py` — pure functions: Raw JSON → Search → Observation → Match → Inclusion → Sellers → Coverage → Claims → template summary. No LLM, no network, no fuzzy matching.
- `proto_config.py` — Tracked Products, provisional Query Plan, Seller Map, Cross-border List, rules (all provisional).
- `run_prototype.py` — prints every stage; writes `out/PROTOTYPE_report.html` (wipe freely).
- `test_deallens_proto.py` — domain-behaviour tests requested for this phase.

```
python prototype/run_prototype.py
python -m pytest prototype -q
```

Not production code. Validated decisions get folded into the real modules during codebase design / TDD; this folder then moves to a throwaway branch.
