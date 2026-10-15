import os
import unittest
from unittest.mock import patch

from app import create_app


class ApplicationConfigurationTests(unittest.TestCase):
    def test_missing_secret_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "SECRET_KEY"):
                create_app()

    def test_test_configuration_can_supply_secret_and_database(self):
        app = create_app({
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE": ":memory:",
        })
        self.assertEqual(app.config["SECRET_KEY"], "test-secret")
        self.assertTrue(app.config["_DATABASE_PATH"].endswith(":memory:"))


if __name__ == "__main__":
    unittest.main()
