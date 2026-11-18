"""Shared timing and overlap rules for editorial selections."""
from itertools import product

MIN_FINAL_SECONDS = 40.0
DEFAULT_RELATED_WINDOW_SECONDS = 600.0


def duration(ranges):
    return round(sum(end - start for start, end in ranges), 3)


def shared_duration(left, right):
    return sum(max(0, min(b, d) - max(a, c)) for (a, b), (c, d) in product(left, right))
