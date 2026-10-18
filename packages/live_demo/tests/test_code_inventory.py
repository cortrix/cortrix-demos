import unittest

from cortrix_live_demo.code_inventory import inventory


class InventoryTests(unittest.TestCase):
    def test_inventory_is_complete_and_uses_only_package_relative_pointers(self):
        result = inventory()
        self.assertFalse(result["warnings"])
        self.assertNotIn("baseline_snapshot", result)
        self.assertEqual(sum(item["code_lines"] for item in result["responsibilities"]), result["counts"]["application"]["code_lines"])
        for item in result["files"]:
            self.assertNotIn("source_path", item)
            self.assertFalse(item["path"].startswith("/"))
            for region in item["source_ranges"]:
                self.assertFalse(region["source_ref"].startswith("/"))


if __name__ == "__main__":
    unittest.main()
