from decimal import Decimal as D

import pytest

from common.money import split_inclusive_line


@pytest.mark.parametrize(
    "rate,qty,gst,taxable,cgst,sgst,total",
    [
        ("118.00", 2, "18", "200.00", "18.00", "18.00", "236.00"),
        ("9.50", 2, "18", "16.10", "1.45", "1.45", "19.00"),
        ("105.00", 1, "5", "100.00", "2.50", "2.50", "105.00"),
        ("50.00", 3, "0", "150.00", "0.00", "0.00", "150.00"),
        ("10.00", 1, "18", "8.47", "0.77", "0.76", "10.00"),  # odd paisa -> CGST
    ],
)
def test_split_inclusive_line(rate, qty, gst, taxable, cgst, sgst, total):
    m = split_inclusive_line(D(rate), qty, D(gst))
    assert m == {"taxable_value": D(taxable), "cgst": D(cgst), "sgst": D(sgst), "line_total": D(total)}
    assert m["taxable_value"] + m["cgst"] + m["sgst"] == m["line_total"]
