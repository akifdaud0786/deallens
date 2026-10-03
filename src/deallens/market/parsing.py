"""Deterministic parsing of Shopping row fields. Never reads SerpApi's `extracted_old_price`."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from deallens.domain import ListPrice
from deallens.text import title_tokens

IST = ZoneInfo("Asia/Kolkata")
_RUPEE = re.compile(r"₹\s*([\d,]+(?:\.\d+)?)")
_PCT_OFF = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*off", re.I)
_GOOGLE_ID_KEYS = ("catalogid", "productid", "headlineOfferDocid")


def _number(text: str):
    value = float(text.replace(",", ""))
    return int(value) if value.is_integer() else value


def parse_inr(raw: Optional[str]):
    """'₹1,16,076' -> 116076. Anything not a single rupee amount -> None."""
    if not raw:
        return None
    amounts = _RUPEE.findall(raw)
    return _number(amounts[0]) if len(amounts) == 1 else None


def parse_list_price(old_price: Optional[str]) -> ListPrice:
    if old_price is None:
        return ListPrice(None, None, "absent")
    amounts = _RUPEE.findall(old_price)
    if len(amounts) != 1:
        return ListPrice(None, None, "unparsed")
    pct = _PCT_OFF.search(old_price)
    return ListPrice(_number(amounts[0]), float(pct.group(1)) if pct else None, "parsed")


def normalized_title(text: str) -> str:
    return " ".join(title_tokens(text))


def google_ids(product_id: Optional[str], product_link: Optional[str]) -> dict:
    """Google identifiers as provenance. Never an identity."""
    out = {"product_id": product_id} if product_id else {}
    m = re.search(r"prds=([^&]+)", product_link or "")
    for part in (m.group(1).split(",") if m else []):
        k, _, v = part.partition(":")
        if k in _GOOGLE_ID_KEYS and v:
            out[k] = v
    return out


def observed_day(fetched_at_utc: str) -> str:
    """India calendar date of a UTC fetch time. Derived; never replaces fetched_at."""
    return datetime.fromisoformat(fetched_at_utc).astimezone(IST).date().isoformat()
