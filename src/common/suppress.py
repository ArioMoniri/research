"""Small-cell suppression (project rule 1).

Any count below the threshold is written as "<10". This is applied literally,
so zero is also written as "<10" (see DECISIONS.md D004).
"""
from __future__ import annotations

THRESHOLD = 10
SMALL = "<10"


def is_small(value) -> bool:
    """True for a value that arrived already suppressed (for example from the bridge)."""
    return isinstance(value, str) and value.strip().startswith("<")


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
    if is_small(value):
        return f"<{threshold}"
    n = to_int(value)
    if n is None:
        return ""
    return f"<{threshold}" if n < threshold else str(n)


def completeness(num_rows, num_nulls, floor: float = 0.60, threshold: int = THRESHOLD,
                 nearly_all_null: bool = False):
    """Return (nulls_display, non_null_pct_display, flag) without revealing a small count.

    flag is one of: ok, under, indeterminate, no_stats.
    When a count is suppressed, the percentage is given as a bound that does
    not let the reader recover the count.
    """
    if is_small(num_rows):
        return "suppressed", "suppressed", "indeterminate"
    n = to_int(num_rows)
    if n is not None and n >= threshold:
        if nearly_all_null:   # the source withheld the null count: fewer than 10 non-null
            num_nulls = n
        elif is_small(num_nulls):
            num_nulls = 0     # any value under the threshold gives the same bound
    nulls = to_int(num_nulls)
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
