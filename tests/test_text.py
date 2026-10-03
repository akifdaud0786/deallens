import pytest

from deallens.text import inr


@pytest.mark.parametrize("value,expected", [
    (72800, "₹72,800"), (116076, "₹1,16,076"), (233011, "₹2,33,011"), (999, "₹999"),
    (72051.94, "₹72,051.94"), (108554.33, "₹1,08,554.33"), (72853.0, "₹72,853"),
])
def test_inr_uses_indian_digit_grouping(value, expected):
    assert inr(value) == expected
