import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from mcp import Client

from server import CSVLabError, create_server, profile_file


class CSVLabTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "inside.csv").write_text("item,qty\npen,2\npen,2\npad,\n", encoding="utf-8")

    def test_profile_and_duplicate_count(self):
        report = profile_file(self.root, "inside.csv", 1024)
        self.assertEqual(report["rows"], 3)
        self.assertEqual(report["duplicate_rows"], 1)
        self.assertEqual(report["missing_by_column"]["qty"], 1)
        self.assertEqual(report["numeric_columns"]["qty"]["mean"], 2.0)

    def test_rejects_paths_outside_root(self):
        outside = self.root.parent / "outside.csv"
        outside.write_text("a\n1\n", encoding="utf-8")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        with self.assertRaises(CSVLabError):
            profile_file(self.root, "../outside.csv", 1024)
        with self.assertRaises(CSVLabError):
            profile_file(self.root, str(outside), 1024)
        (self.root / "link.csv").symlink_to(outside)
        with self.assertRaises(CSVLabError):
            profile_file(self.root, "link.csv", 1024)

    def test_size_limit_and_invalid_config(self):
        with self.assertRaisesRegex(CSVLabError, "exceeds"):
            profile_file(self.root, "inside.csv", 5)
        with self.assertRaises(CSVLabError):
            create_server(self.root, 0)

    def test_large_finite_values_and_private_root_errors(self):
        (self.root / "large.csv").write_text("value\n1e308\n1e308\n", encoding="utf-8")
        self.assertEqual(profile_file(self.root, "large.csv", 1024)["numeric_columns"]["value"]["mean"], 1e308)
        with self.assertRaises(CSVLabError) as caught:
            profile_file(self.root, "missing.csv", 1024)
        self.assertNotIn(str(self.root), str(caught.exception))

    def test_in_memory_mcp_tool(self):
        server = create_server(self.root, 1024)

        async def check():
            async with Client(server) as client:
                good = await client.call_tool("profile_csv", {"file_path": "inside.csv"})
                self.assertFalse(good.is_error)
                self.assertEqual(json.loads(good.content[0].text)["rows"], 3)
                bad = await client.call_tool("profile_csv", {"file_path": "../outside.csv"})
                self.assertTrue(bad.is_error)

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
