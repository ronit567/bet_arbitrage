import math

import pytest

from src.odds_utils import american_to_decimal, decimal_to_american, implied_probability


class TestAmericanToDecimal:
    def test_plus_150(self):
        assert american_to_decimal(150) == pytest.approx(2.50)

    def test_minus_125(self):
        assert american_to_decimal(-125) == pytest.approx(1.80)

    def test_plus_100(self):
        assert american_to_decimal(100) == pytest.approx(2.00)

    def test_minus_100(self):
        assert american_to_decimal(-100) == pytest.approx(2.00)

    def test_minus_200(self):
        assert american_to_decimal(-200) == pytest.approx(1.50)

    def test_plus_200(self):
        assert american_to_decimal(200) == pytest.approx(3.00)

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            american_to_decimal(0)

    def test_between_minus_99_and_plus_99_raises(self):
        with pytest.raises(ValueError):
            american_to_decimal(50)
        with pytest.raises(ValueError):
            american_to_decimal(-50)


class TestDecimalToAmerican:
    def test_roundtrip_plus_150(self):
        assert decimal_to_american(american_to_decimal(150)) == 150

    def test_roundtrip_minus_125(self):
        assert decimal_to_american(american_to_decimal(-125)) == -125

    def test_evens(self):
        # 2.00 decimal is exactly +100; our rule routes >=2.0 to positive
        assert decimal_to_american(2.00) == 100


class TestImpliedProbability:
    def test_evens_is_half(self):
        assert implied_probability(2.00) == pytest.approx(0.50)

    def test_plus_150_implied(self):
        assert implied_probability(american_to_decimal(150)) == pytest.approx(0.40)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            implied_probability(1.0)
