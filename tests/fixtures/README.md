# Test fixtures

- `shopping/`: the three 3 Oct 2026 Google Shopping probes (India), **trimmed** to the fields the tests read. All SerpApi account/archive URLs (`markdown_endpoint`, `raw_html_file`, `serpapi.com/searches/...`, thumbnails, `serpapi_*` links), `filters` and `categorized_shopping_results` were removed.
- `immersive_sanitized/`: the 3 Oct Immersive Product probe with reviewer data (`user_reviews`, `reviews_images`) and every SerpApi URL removed; only title, rating, price range and store offers remain. The original stays local and gitignored.
- Synthetic cases are built in code by `tests/synthetic.py` (`synthetic_*`); none are stored here.

`tests/test_fixture_hygiene.py` fails if a SerpApi URL or reviewer field reappears.

**Terms check (7 Oct 2026):** SerpApi's [legal terms](https://serpapi.com/legal) prohibit reproducing or reselling the service itself and contain no clause restricting publication of returned search results. These fixtures are still kept to the minimum the tests need, with every SerpApi URL and all reviewer data removed. If SerpApi or the hackathon organizers ask, they can be replaced with synthetic fixtures.
