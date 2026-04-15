"""Edge-case tests for JoinKeyResolver with short numeric keys.

Probe M6 regression — verifies that resolve_chain with ['strip_prefix', 'first_5_chars']
correctly zero-pads keys shorter than 5 digits after prefix removal, e.g. 'ID-1234' → '01234'.

Also covers strip_cust_prefix() (J4) and resolve_tcga_id() (M5).
"""

import pytest
from utils.join_key_resolver import JoinKeyResolver


@pytest.fixture
def resolver():
    return JoinKeyResolver()


class TestFirstFiveCharsZeroPad:
    """first_5_chars normalizer must zero-pad keys shorter than 5 digits (M6 edge case)."""

    def test_normal_5digit_key(self, resolver):
        result = resolver.resolve_chain("ID-98765", ["strip_prefix", "first_5_chars"])
        assert result == "98765"

    def test_short_4digit_key_gets_zero_padded(self, resolver):
        # Core M6 edge case: 'ID-1234' must become '01234', not '1234'
        result = resolver.resolve_chain("ID-1234", ["strip_prefix", "first_5_chars"])
        assert result == "01234", f"Expected '01234', got '{result}'"

    def test_short_3digit_key_gets_zero_padded(self, resolver):
        result = resolver.resolve_chain("ID-123", ["strip_prefix", "first_5_chars"])
        assert result == "00123"

    def test_long_key_truncated_to_5(self, resolver):
        result = resolver.resolve_chain("ID-9876543", ["strip_prefix", "first_5_chars"])
        assert result == "98765"

    def test_first_5_chars_standalone_pads_short_input(self, resolver):
        result = resolver.resolve_chain("42", ["first_5_chars"])
        assert result == "00042"


class TestStripCustPrefix:
    """strip_cust_prefix() must handle zero-padded CUST- keys and the all-zero edge case (J4)."""

    def test_standard_cust_dash(self, resolver):
        assert resolver.strip_cust_prefix("CUST-0001001") == 1001

    def test_cust_underscore_delimiter(self, resolver):
        assert resolver.strip_cust_prefix("CUST_0001001") == 1001

    def test_no_leading_zeros(self, resolver):
        assert resolver.strip_cust_prefix("CUST-12345") == 12345

    def test_all_zeros_edge_case(self, resolver):
        # Regression: re.sub(r'^CUST[_-]0*', ...) would strip everything → ValueError.
        # The lookahead fix (?=\d) ensures the last zero is preserved → int('0') = 0.
        assert resolver.strip_cust_prefix("CUST-0000000") == 0

    def test_single_digit(self, resolver):
        assert resolver.strip_cust_prefix("CUST-0000001") == 1


class TestResolveTcgaId:
    """resolve_tcga_id() must convert TCGA-prefixed keys to plain lowercase alphanum (M5)."""

    def test_standard_tcga_key(self, resolver):
        assert resolver.resolve_tcga_id("TCGA-AB-1234") == "ab1234"

    def test_longer_tcga_key(self, resolver):
        assert resolver.resolve_tcga_id("TCGA-XY-9876") == "xy9876"

    def test_prefix_stripped_only_at_start(self, resolver):
        # Anchored removal: 'TCGA-' only stripped from the start, not mid-string.
        result = resolver.resolve_tcga_id("TCGA-TC-GA12")
        assert result == "tcga12"

    def test_output_is_lowercase(self, resolver):
        result = resolver.resolve_tcga_id("TCGA-AB-1234")
        assert result == result.lower()

    def test_output_is_alphanumeric_only(self, resolver):
        result = resolver.resolve_tcga_id("TCGA-AB-1234")
        assert result.isalnum()
