"""Text helpers shared across modules: title tokenization and INR display formatting (no domain policy)."""
import re

_INVISIBLE = dict.fromkeys(map(ord, "‎‏​‌‍﻿­"), None)


def title_tokens(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[A-Z0-9]+", (text or "").translate(_INVISIBLE).upper()))


def inr(x) -> str:
    """Display an INR amount with Indian digit grouping: 116076 -> '₹1,16,076'."""
    whole, _, frac = (f"{x:.2f}" if not float(x).is_integer() else f"{int(x)}").partition(".")
    head, tail = whole[:-3], whole[-3:]
    groups = re.findall(r"\d{1,2}(?=(?:\d{2})*$)", head) if head else []
    return "₹" + ",".join(groups + [tail]) + (f".{frac}" if frac and frac != "00" else "")
