import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import claimcheck


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        write(os.path.join(self.root, "real.py"), "x = 1\n")
        write(os.path.join(self.root, "docs", "guide.md"),
              "# Guide\n\n## Install Steps\n\nBody.\n")
        write(os.path.join(self.root, "README.md"), "\n".join([
            "# Project",
            "",
            "See [the guide](docs/guide.md) and [install](docs/guide.md#install-steps).",
            "Run `real.py` to start.",
            "External [site](https://example.com/nope) is ignored.",
            "Anchor to [top](#project).",
            "",
        ]))

    def tearDown(self):
        self.tmp.cleanup()

    def findings(self):
        return claimcheck.run(self.root)


class TestClean(Fixture):
    def test_clean_repo_has_no_findings(self):
        self.assertEqual(self.findings(), [])

    def test_main_returns_zero(self):
        self.assertEqual(claimcheck.main(["--root", self.root]), 0)


class TestBroken(Fixture):
    def break_readme(self, extra):
        with open(os.path.join(self.root, "README.md"), "a", encoding="utf-8") as fh:
            fh.write(extra)

    def test_missing_linked_file(self):
        self.break_readme("\n[gone](docs/missing.md)\n")
        kinds = [f["kind"] for f in self.findings()]
        self.assertIn("missing-file", kinds)

    def test_missing_anchor_same_file(self):
        self.break_readme("\n[nowhere](#no-such-heading)\n")
        kinds = [f["kind"] for f in self.findings()]
        self.assertIn("missing-anchor", kinds)

    def test_missing_anchor_other_file(self):
        self.break_readme("\n[bad](docs/guide.md#nope)\n")
        kinds = [f["kind"] for f in self.findings()]
        self.assertIn("missing-anchor", kinds)

    def test_missing_inline_path(self):
        self.break_readme("\nEdit `src/ghost.py` before running.\n")
        kinds = [f["kind"] for f in self.findings()]
        self.assertIn("missing-path", kinds)

    def test_main_returns_one(self):
        self.break_readme("\n[gone](gone.md)\n")
        self.assertEqual(claimcheck.main(["--root", self.root]), 1)

    def test_finding_has_line_number(self):
        self.break_readme("\n[gone](gone.md)\n")
        found = [f for f in self.findings() if f["kind"] == "missing-file"]
        self.assertTrue(found and found[0]["line"] >= 2)


class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(claimcheck.slugify("Install Steps"), "install-steps")

    def test_punctuation_removed(self):
        self.assertEqual(claimcheck.slugify("What's new?"), "whats-new")


if __name__ == "__main__":
    unittest.main()

class TestCodeSpansIgnored(Fixture):
    def test_link_inside_inline_code_is_an_example_not_a_claim(self):
        with open(os.path.join(self.root, "README.md"), "a", encoding="utf-8") as fh:
            fh.write("\nExample: `[x](docs/nope.md)` written in code.\n")
        self.assertEqual(self.findings(), [])
