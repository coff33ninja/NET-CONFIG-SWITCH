import unittest
import sys
import os

# Adjust the Python path to include the project root directory
# This allows 'from network_manager import ...' to work when tests are run from the root
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from network_manager import validate_ip


class TestValidateIP(unittest.TestCase):
    """Unit tests for the validate_ip function in network_manager.py."""

    def test_valid_ips(self):
        """Test that common valid IP addresses are correctly validated."""
        valid_ips = [
            "192.168.1.1",
            "0.0.0.0",
            "255.255.255.255",
            "10.0.0.1",
            "172.16.0.1",
        ]
        for ip in valid_ips:
            with self.subTest(ip=ip):
                self.assertTrue(validate_ip(ip), f"Expected {ip} to be valid.")

    def test_invalid_ips_format(self):
        """Test IP addresses with incorrect formatting."""
        invalid_ips_format = [
            "192.168.1",  # Too few octets
            "a.b.c.d",  # Non-numeric characters
            "1.2.3.4.5",  # Too many octets
            "192.168..1",  # Empty octet
            "192 .168.1.1",  # Spaces
            ".1.2.3.4",  # Leading dot
        ]
        for ip in invalid_ips_format:
            with self.subTest(ip=ip):
                self.assertFalse(
                    validate_ip(ip), f"Expected {ip} to be invalid due to format."
                )

    def test_invalid_ips_range(self):
        """Test IP addresses with octets out of the 0-255 range."""
        invalid_ips_range = [
            "192.168.1.256",  # Octet > 255
            "300.0.0.1",  # First octet > 255
            "1.2.3.999",  # Last octet > 255
            "-1.2.3.4",  # Negative number (though regex might catch as non-digit first)
        ]
        for ip in invalid_ips_range:
            with self.subTest(ip=ip):
                self.assertFalse(
                    validate_ip(ip), f"Expected {ip} to be invalid due to range."
                )

    def test_empty_string_is_valid(self):
        """Test that an empty string is considered valid (as per current function logic)."""
        self.assertTrue(validate_ip(""), "Empty string should be considered valid.")

    def test_none_is_valid(self):
        """Test that None is considered valid (as per current function logic 'if not ip')."""
        self.assertTrue(validate_ip(None), "None should be considered valid.")


if __name__ == "__main__":
    unittest.main()

# To run tests:
# 1. Navigate to the project root directory in your terminal.
# 2. Execute the command: python -m unittest discover tests
#    Alternatively, to run this specific file: python -m unittest tests.test_network_manager
#
# Ensure that the project root is in PYTHONPATH if running from outside,
# or that the test runner configuration handles it. The sys.path modification
# at the top of this file attempts to handle this for direct execution.
