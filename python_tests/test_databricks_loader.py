"""Tests hors reseau : validation et reprise du chargement mensuel."""
import csv
import json
import re
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from databricks_loader import SCHEMAS, TABLES, load_csvs, normalize_value


class FakeClient:
    prefix = "`workspace`.`boucherie_raw`"

    def __init__(self):
        self.tables = {f"{self.prefix}.`{name}`": [{"source_month": "2025-12-01"}, {"source_month": "2026-01-01"}] for name in TABLES.values()}
        self.published = []
        self.fail_upload = False
        self.fail_second_publish = False

    def execute(self, sql, parameters=None):
        if sql.startswith("DESCRIBE TABLE"):
            kind = next(kind for kind, name in TABLES.items() if sql.endswith(f"`{name}`"))
            return SCHEMAS[kind]
        if sql.startswith("DESCRIBE DETAIL"):
            return [["delta"]]
        if sql.startswith("CREATE TABLE"):
            self.tables[sql.split()[2]] = []
        elif sql.startswith("DROP TABLE"):
            self.tables.pop(sql.split()[-1], None)
        elif "REPLACE WHERE" in sql:
            target, source = sql.split()[2], sql.split()[-1]
            if self.fail_second_publish and "raw_sales_lines" in target:
                raise RuntimeError("Publication interrompue")
            months = re.findall(r"DATE '([0-9-]+)'", sql)
            self.tables[target] = [r for r in self.tables[target] if r["source_month"] not in months] + list(self.tables[source])
            self.published.append(target)
        elif sql.startswith("INSERT INTO"):
            if self.fail_upload and "sales_lines" in sql:
                raise RuntimeError("Upload interrompu")
            self.tables[sql.split()[2]].extend(json.loads(parameters[0]["value"]))
        elif sql.startswith("SELECT CAST"):
            table = sql.split(" FROM ")[1].split()[0]
            months = re.findall(r"DATE '([0-9-]+)'", sql)
            rows = self.tables[table]
            return list(Counter(row["source_month"] for row in rows if not months or row["source_month"] in months).items())
        else:
            raise AssertionError(sql)
        return []


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = []
        for kind, schema in SCHEMAS.items():
            row = {name: {"bigint": "1", "double": "1.25", "decimal(24,4)": "3.5", "string": "Côte d'agneau", "timestamp": "2026-01-02 10:30:00", "date": "2026-01"}[datatype] for name, datatype in schema}
            path = self.root / f"{kind}_2026_01.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            self.manifest.append({"kind": kind, "path": str(path), "rows": 1})

    def test_repeat_preserves_other_months_and_accents(self):
        client = FakeClient()
        load_csvs(self.manifest, self.root, client)
        load_csvs(self.manifest, self.root, client)
        for rows in client.tables.values():
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["source_month"], "2025-12-01")
            self.assertEqual(rows[1]["customer_name"], "Côte d'agneau")

    def test_upload_failure_leaves_both_targets_unchanged(self):
        client = FakeClient()
        before = json.dumps(client.tables, sort_keys=True)
        client.fail_upload = True
        with self.assertRaises(RuntimeError):
            load_csvs(self.manifest, self.root, client)
        self.assertEqual(json.dumps(client.tables, sort_keys=True), before)
        self.assertFalse(client.published)

    def test_partial_publication_can_be_replayed(self):
        client = FakeClient()
        client.fail_second_publish = True
        with self.assertRaises(RuntimeError):
            load_csvs(self.manifest, self.root, client)
        client.fail_second_publish = False
        load_csvs(self.manifest, self.root, client)
        self.assertTrue(all(len(rows) == 2 for rows in client.tables.values()))

    def test_invalid_counts_do_not_write(self):
        self.manifest[0]["rows"] = 2
        client = FakeClient()
        with self.assertRaises(ValueError):
            load_csvs(self.manifest, self.root, client)
        self.assertFalse(client.published)

    def test_missing_month_pair_fails(self):
        with self.assertRaises(ValueError):
            load_csvs(self.manifest[:1], self.root, FakeClient())

    def test_fractional_discount_preserved_and_month_converted(self):
        self.assertEqual(normalize_value("2026-01", "date", "source_month"), "2026-01-01")
        self.assertEqual(normalize_value("000123", "bigint", "ticket_id"), "123")
        self.assertEqual(normalize_value("3.5", "decimal(24,4)", "discount_percent"), "3.5")
        with self.assertRaises(ValueError):
            normalize_value("3.55555", "decimal(24,4)", "discount_percent")
        with self.assertRaises(ValueError):
            normalize_value("2.5", "bigint", "discount_percent")
        with self.assertRaises(ValueError):
            normalize_value("NaN", "double", "net_amount_ttc")


if __name__ == "__main__":
    unittest.main()
