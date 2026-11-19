"""Small-cell suppression (project rule 1).

Any count below the threshold is written as "<10". This is applied literally,
so zero is also written as "<10" (see DECISIONS.md D004).
"""
from __future__ import annotations

THRESHOLD = 10
SMALL = "<10"


def to_int(value) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def count(value, threshold: int = THRESHOLD) -> str:
    """Display form of a count. Empty string means 'not available'."""
    n = to_int(value)
    if n is None:
        return ""
    return f"<{threshold}" if n < threshold else str(n)


def completeness(num_rows, num_nulls, floor: float = 0.60, threshold: int = THRESHOLD):
    """Return (nulls_display, non_null_pct_display, flag) without revealing a small count.

    flag is one of: ok, under, indeterminate, no_stats.
    When a count is suppressed, the percentage is given as a bound that does
    not let the reader recover the count.
    """
    n, nulls = to_int(num_rows), to_int(num_nulls)
    if n is None or nulls is None:
        return "", "", "no_stats"
    if n < threshold:
        return "suppressed", "suppressed", "indeterminate"
    nulls = min(max(nulls, 0), n)
    non_null = n - nulls
    top = threshold - 1  # largest value a suppressed count can take
    if nulls < threshold:
        bound = (n - top) / n
        flag = "ok" if bound >= floor else "indeterminate"
        return f"<{threshold}", f">={100 * bound:.1f}", flag
    if non_null < threshold:
        bound = top / n
        flag = "under" if bound < floor else "indeterminate"
        return "suppressed", f"<={100 * bound:.1f}", flag
    pct = non_null / n
    return str(nulls), f"{100 * pct:.1f}", "ok" if pct >= floor else "under"
