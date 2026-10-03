"""Live SerpApi adapter. Only the CLI composition root may import this module (see ADR 0005)."""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Mapping

from deallens.serpapi import (API_ERROR, INVALID_RESPONSE, TIMEOUT, TRANSPORT_ERROR, CreditReadError, CreditReading,
                              SearchOutcome, now_utc)

BASE = "https://serpapi.com"


class HttpSerpApi:
    def __init__(self, api_key: str, *, opener=urllib.request.urlopen):
        if not api_key:
            raise ValueError("SerpApi key is empty")
        self.__key = api_key
        self._open = opener

    def __repr__(self) -> str:
        return "HttpSerpApi(api_key=***)"

    def _redact(self, text) -> str:
        return str(text).replace(self.__key, "***")

    def _get(self, path: str, params: Mapping[str, str], timeout_s: float):
        url = f"{BASE}/{path}?" + urllib.parse.urlencode({**params, "api_key": self.__key})
        with self._open(url, timeout=timeout_s) as r:
            return json.loads(r.read().decode("utf-8"))

    def search(self, params: Mapping[str, str], timeout_s: float) -> SearchOutcome:
        if "api_key" in params:
            raise ValueError("api_key must not be passed in params")
        try:
            body = self._get("search.json", params, timeout_s)
        except urllib.error.HTTPError as e:
            status = API_ERROR if 400 <= e.code < 500 else TRANSPORT_ERROR
            return SearchOutcome.failure(status, self._redact(f"HTTP {e.code}: {e.reason}"), e.code)
        except (socket.timeout, TimeoutError):
            return SearchOutcome.failure(TIMEOUT, f"timed out after {timeout_s}s")
        except ValueError as e:                       # JSON/UTF-8 decode: a response arrived, so never retry
            return SearchOutcome.failure(INVALID_RESPONSE, self._redact(f"{type(e).__name__}: {e}"))
        except (urllib.error.URLError, OSError) as e:
            return SearchOutcome.failure(TRANSPORT_ERROR, self._redact(e))
        if isinstance(body, dict) and body.get("error"):
            return SearchOutcome.failure(API_ERROR, self._redact(body["error"]))
        return SearchOutcome.ok(body)

    def credits(self) -> CreditReading:
        try:
            body = self._get("account.json", {}, 30)
            return CreditReading(int(body["plan_searches_left"]), body.get("this_month_usage"), now_utc())
        except Exception as e:                        # noqa: BLE001 - every failure becomes one redacted error
            raise CreditReadError(self._redact(f"{type(e).__name__}: {e}")) from None
