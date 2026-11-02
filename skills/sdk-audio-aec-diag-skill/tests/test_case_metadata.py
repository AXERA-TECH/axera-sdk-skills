"""Keep evaluation metadata outside the runtime installation."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CaseMetadataTests(unittest.TestCase):


    def test_metadata_never_installed_with_skill(self):
        spec = importlib.util.spec_from_file_location("case_test_install", ROOT / "scripts/install.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            skill = module.install(Path(directory) / "bundle")
            self.assertFalse(list(skill.rglob("oracle.yaml")))
            self.assertFalse(list(skill.rglob("case.yaml")))
            self.assertFalse(list(skill.rglob("reproducer.patch")))


if __name__ == "__main__":
    unittest.main()
