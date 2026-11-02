import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SdkBuildSkillTests(unittest.TestCase):
    def test_skill_card_exists_and_fields(self):
        skill_card = ROOT / "skill-card.md"
        self.assertTrue(skill_card.is_file())
        text = skill_card.read_text(encoding="utf-8")
        self.assertIn("sdk-bsp-sdk-build", text)
        self.assertIn("platforms", text)

    def test_skill_frontmatter(self):
        skill_md = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        parts = skill_md.split("---")
        self.assertGreaterEqual(len(parts), 3)
        frontmatter = parts[1]
        self.assertIn("name: sdk-bsp-sdk-build", frontmatter)
        self.assertIn("description:", frontmatter)

    def test_routing_yaml_content(self):
        routing_text = (ROOT / "routing.yaml").read_text(encoding="utf-8")
        self.assertIn("platforms:", routing_text)
        self.assertIn("id: m57", routing_text)
        self.assertIn("id: ax637", routing_text)

    def test_platform_docs_and_references(self):
        self.assertTrue((ROOT / "platforms/m57.md").is_file())
        self.assertTrue((ROOT / "platforms/ax637.md").is_file())
        self.assertTrue((ROOT / "reference/m57/_index.md").is_file())
        self.assertTrue((ROOT / "reference/ax637/_index.md").is_file())

    def test_evals_tasks_yaml_content(self):
        ax637_tasks = (ROOT / "evals/ax637/tasks.yaml").read_text(encoding="utf-8")
        m57_tasks = (ROOT / "evals/m57/tasks.yaml").read_text(encoding="utf-8")
        self.assertIn("tasks:", ax637_tasks)
        self.assertIn("tasks:", m57_tasks)

    def test_suite_yaml_cases_exist(self):
        suite_text = (ROOT / "evals/suite.yaml").read_text(encoding="utf-8")
        self.assertIn("cases:", suite_text)
        case_dirs = ["full-axp-build-m57", "standalone-kernel-build-ax637", "disable-optee-build-ax637", "list-supported-platforms-m57"]
        for case in case_dirs:
            case_dir = ROOT / "evals/cases" / case
            self.assertTrue((case_dir / "case.yaml").is_file(), f"Missing case.yaml for {case}")
            self.assertTrue((case_dir / "assert.sh").is_file(), f"Missing assert.sh for {case}")


if __name__ == "__main__":
    unittest.main()
