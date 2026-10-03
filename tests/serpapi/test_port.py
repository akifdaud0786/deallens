import io
import json
import socket
import urllib.error

import pytest

from deallens.serpapi import CreditReading, FixtureSerpApi, SearchOutcome
from deallens.serpapi.http import HttpSerpApi

KEY = "k3y-THAT-must-never-leak-0123456789"
PARAMS = {"engine": "google_shopping", "q": "ASUS Vivobook 15", "gl": "in"}


class FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_returning(body, seen):
    def opener(url, timeout):
        seen.append((url, timeout))
        return FakeResponse(json.dumps(body).encode())
    return opener


def opener_raising(exc):
    def opener(url, timeout):
        raise exc
    return opener


# ---------- fixture adapter ----------

def test_fixture_adapter_replays_scripted_outcomes_and_records_calls():
    ok = SearchOutcome.ok({"search_metadata": {"id": "s1"}})
    api = FixtureSerpApi([ok, SearchOutcome.failure("timeout", "slow")], credits=200)
    assert api.search(PARAMS, timeout_s=5) == ok
    assert api.search(PARAMS, timeout_s=5).status == "timeout"
    assert api.calls == [PARAMS, PARAMS]
    assert api.credits().plan_searches_left == 200
    with pytest.raises(AssertionError, match="unexpected"):
        api.search(PARAMS, timeout_s=5)


# ---------- HTTP adapter (fake opener, no network) ----------

def test_http_search_builds_the_request_and_never_exposes_the_key():
    seen = []
    api = HttpSerpApi(KEY, opener=opener_returning({"search_metadata": {"id": "s1"}, "shopping_results": []}, seen))
    out = api.search(PARAMS, timeout_s=7)
    assert out.status == "ok" and out.body["search_metadata"]["id"] == "s1"
    url, timeout = seen[0]
    assert url.startswith("https://serpapi.com/search.json?") and "q=ASUS+Vivobook+15" in url and f"api_key={KEY}" in url
    assert timeout == 7
    assert KEY not in repr(api) and KEY not in repr(out)


def test_http_api_error_body_is_an_api_error_with_redacted_message():
    api = HttpSerpApi(KEY, opener=opener_returning({"error": f"Invalid API key {KEY}"}, []))
    out = api.search(PARAMS, timeout_s=5)
    assert out.status == "api_error" and KEY not in out.error and "***" in out.error


def test_http_status_error_is_an_api_error_for_4xx_and_transport_for_5xx():
    e4 = urllib.error.HTTPError("https://serpapi.com/search.json?api_key=" + KEY, 401, "Unauthorized", {},
                                io.BytesIO(b'{"error": "Invalid API key"}'))
    assert HttpSerpApi(KEY, opener=opener_raising(e4)).search(PARAMS, timeout_s=5).status == "api_error"
    e5 = urllib.error.HTTPError("u", 503, "Unavailable", {}, io.BytesIO(b""))
    assert HttpSerpApi(KEY, opener=opener_raising(e5)).search(PARAMS, timeout_s=5).status == "transport_error"


def test_http_timeout_and_transport_errors_are_outcomes_not_exceptions():
    assert HttpSerpApi(KEY, opener=opener_raising(socket.timeout())).search(PARAMS, timeout_s=5).status == "timeout"
    out = HttpSerpApi(KEY, opener=opener_raising(urllib.error.URLError(f"boom {KEY}"))).search(PARAMS, timeout_s=5)
    assert out.status == "transport_error" and KEY not in out.error


def test_malformed_json_is_not_retryable():
    def opener(url, timeout):
        return FakeResponse(b"not json")
    out = HttpSerpApi(KEY, opener=opener).search(PARAMS, timeout_s=5)
    assert out.status == "invalid_response" and out.retryable is False and KEY not in (out.error or "")


def test_callers_may_not_pass_an_api_key_in_params():
    with pytest.raises(ValueError, match="api_key"):
        HttpSerpApi(KEY, opener=opener_returning({}, [])).search({**PARAMS, "api_key": "x"}, timeout_s=5)


def test_credit_read_errors_are_raised_redacted():
    from deallens.serpapi import CreditReadError
    with pytest.raises(CreditReadError) as e:
        HttpSerpApi(KEY, opener=opener_raising(urllib.error.URLError(f"boom {KEY}"))).credits()
    assert KEY not in str(e.value)


def test_credits_reading_comes_from_the_account_endpoint():
    seen = []
    api = HttpSerpApi(KEY, opener=opener_returning({"plan_searches_left": 247, "this_month_usage": 3}, seen))
    reading = api.credits()
    assert isinstance(reading, CreditReading) and reading.plan_searches_left == 247 and reading.this_month_usage == 3
    assert seen[0][0].startswith("https://serpapi.com/account.json?")
