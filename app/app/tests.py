"""
Sample tests
"""
from django.test import SimpleTestCase

from app import sample_calc_test


class ClassCalc(SimpleTestCase):
    """Test the calc module."""

    def test_add_numbers(self):
        """Test adding numbers together."""
        res = sample_calc_test.add(10, 1)

        self.assertEqual(res, 11)

    def test_subtract_numbers(self):
        """Test subtracting numbers."""
        res = sample_calc_test.subtract(10, 1)

        self.assertEqual(res, 9)
