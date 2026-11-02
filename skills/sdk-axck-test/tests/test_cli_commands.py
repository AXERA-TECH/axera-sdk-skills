import unittest
import subprocess
import sys
import os

class TestCliCommands(unittest.TestCase):
    def test_cli_help(self):
        """Verify CLI help contains new subcommands."""
        cli_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "cli.py")
        res = subprocess.run(
            [sys.executable, cli_path, "--help"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("single-case", res.stdout)
        self.assertIn("run-scenario", res.stdout)
        self.assertIn("stress", res.stdout)

if __name__ == "__main__":
    unittest.main()
