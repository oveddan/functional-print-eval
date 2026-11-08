"""The assumption tolerance: answer from the nearest print rather than "not graded" when a size is close to one
that was printed (Dan, 2026-11-08: "answer it unless we definitely can't tell", "only if it makes sense").

A size within ASSUMED_WITHIN of a printed size takes that print's result, and the finding says which print it was
assumed from, so a verdict that rests on an assumption is always told apart from one that rests on a print. Midway
between two prints that disagree, the tighter one decides. Further than that from every print stays not graded.
"""
ASSUMED_WITHIN = 0.2  # mm: about one printed line's worth of error on a hole, and two of coupon B's 0.1 mm steps


def nearest(value: float, records: list[tuple[float, object]]) -> tuple[float, object] | None:
    """The (size, result) printed nearest to `value`, the tighter one on a tie, or None if none is within
    ASSUMED_WITHIN."""
    if not records:
        return None
    size, result = min(records, key=lambda record: (round(abs(record[0] - value), 6), record[0]))
    return (size, result) if abs(size - value) <= ASSUMED_WITHIN + 1e-9 else None


def note(size: float, unit: str = " mm") -> str:
    return f"assumed from the {size:g}{unit} print, within the {ASSUMED_WITHIN} mm assumption tolerance"
