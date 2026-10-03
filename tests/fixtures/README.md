# Test fixtures

- `shopping/`: the three 3 Oct 2026 Google Shopping probes (India), **trimmed** to the fields the tests read. All SerpApi account/archive URLs (`markdown_endpoint`, `raw_html_file`, `serpapi.com/searches/...`, thumbnails, `serpapi_*` links), `filters` and `categorized_shopping_results` were removed.
- `immersive_sanitized/`: the 3 Oct Immersive Product probe with reviewer data (`user_reviews`, `reviews_images`) and every SerpApi URL removed; only title, rating, price range and store offers remain. The original stays local and gitignored.
- Synthetic cases are built in code by `tests/synthetic.py` (`synthetic_*`); none are stored here.

`tests/test_fixture_hygiene.py` fails if a SerpApi URL or reviewer field reappears.

**TODO before publishing this repository:** verify SerpApi's Terms of Service on redistributing search results, even trimmed. Until that is confirmed, treat these files as not cleared for public release. Nothing in this repository asserts that they are publishable.
