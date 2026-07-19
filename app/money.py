"""Money helpers.

All internal amounts are integer paise. The public API accepts/returns rupees
for readability (the reference data uses rupees), converting at the boundary.

Advance rounding policy
-----------------------
The advance is 10% of a sale's earning. When 10% is not a whole number of
paise we round *down* (floor). Rationale: the advance is money paid out before
the sale is confirmed, so being conservative (never over-advancing) protects
the platform from clawback risk. The lost fraction is at most 0.9 paise and is
recovered at final settlement anyway (the final payout adds back
``earning - advance``).
"""

PAISE_PER_RUPEE = 100
ADVANCE_RATE_PERCENT = 10


def rupees_to_paise(rupees: float) -> int:
    """Convert a rupee amount to integer paise (round half-up)."""
    return int(round(rupees * PAISE_PER_RUPEE))


def paise_to_rupees(paise: int) -> float:
    """Convert integer paise back to a rupee float for display."""
    return paise / PAISE_PER_RUPEE


def advance_of(earning_paise: int) -> int:
    """10% of earnings, floored to whole paise (see module docstring)."""
    return (earning_paise * ADVANCE_RATE_PERCENT) // 100
