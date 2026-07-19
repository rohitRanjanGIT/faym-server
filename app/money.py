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
