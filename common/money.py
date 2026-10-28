"""Money helpers. Money is always Decimal, never float."""
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

TWO_PLACES = Decimal("0.01")
HUNDRED = Decimal("100")


def round2(value) -> Decimal:
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def split_inclusive_line(rate: Decimal, quantity: int, gst_rate: Decimal) -> dict:
    """Tax split for a GST-inclusive line (intra-state: CGST + SGST).

    gross = rate * qty; taxable = round2(gross / (1 + gst/100)); tax = gross - taxable.
    Tax is halved; any odd paisa goes to CGST.
    """
    gross = round2(Decimal(rate) * quantity)
    taxable = round2(gross / (Decimal(1) + Decimal(gst_rate) / HUNDRED))
    tax = gross - taxable
    sgst = (tax / 2).quantize(TWO_PLACES, rounding=ROUND_DOWN)
    cgst = tax - sgst
    return {"taxable_value": taxable, "cgst": cgst, "sgst": sgst, "line_total": gross}
