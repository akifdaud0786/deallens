"""Committed fixtures must carry only what tests read: no SerpApi account/archive URLs, no reviewer data."""
import json

from conftest import FIXTURES

ROW_FIELDS = {"position", "title", "product_id", "product_link", "immersive_product_page_token", "source", "price",
              "extracted_price", "old_price", "extracted_old_price", "alternative_price", "delivery", "rating",
              "reviews", "multiple_sources", "second_hand_condition"}


def fixture_files():
    return sorted(p for p in FIXTURES.rglob("*.json"))


def test_fixtures_contain_no_serpapi_urls_or_reviewer_data():
    for f in fixture_files():
        text = f.read_text(encoding="utf-8")
        assert "serpapi.com" not in text, f.name
        assert "user_reviews" not in text and "user_name" not in text, f.name


def test_shopping_fixtures_are_trimmed_to_fields_the_tests_read():
    for f in sorted((FIXTURES / "shopping").glob("*.json")):
        resp = json.loads(f.read_text(encoding="utf-8"))["response"]
        assert set(resp) <= {"search_metadata", "search_parameters", "search_information", "shopping_results"}
        assert set(resp["search_metadata"]) <= {"id", "status", "created_at", "processed_at"}
        for row in resp["shopping_results"]:
            assert set(row) <= ROW_FIELDS, f"{f.name}: {set(row) - ROW_FIELDS}"
