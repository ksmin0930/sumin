"""월말 잔고는 다른 기준월과 절대 함께 집계되지 않도록 검증한다."""
import ast
from pathlib import Path
import unittest

import pandas as pd


def load_helpers():
    tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    wanted = {"norm", "find_col", "month_label", "month_key", "input_frame_for_month"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    module = ast.Module(body=nodes, type_ignores=[])
    namespace = {"pd": pd, "re": __import__("re"), "Iterable": __import__("typing").Iterable}
    exec(compile(ast.fix_missing_locations(module), "app.py", "exec"), namespace)
    return namespace["input_frame_for_month"]


class MonthScopingTest(unittest.TestCase):
    def test_input_snapshot_is_limited_to_its_archive_month(self):
        input_frame_for_month = load_helpers()
        source = pd.DataFrame(
            {
                "기준월": ["2026-04", "2026-05", "2026-06", "2026-07"],
                "대분류": ["보통예금"] * 4,
                "금액": [100, 200, 300, 400],
            }
        )

        july = input_frame_for_month(source, "2026-07")

        self.assertEqual(july["기준월"].tolist(), ["2026-07"])
        self.assertEqual(july["금액"].sum(), 400)

    def test_input_without_a_month_column_fails_closed(self):
        input_frame_for_month = load_helpers()
        source = pd.DataFrame({"대분류": ["보통예금"], "금액": [999999999]})

        self.assertTrue(input_frame_for_month(source, "2026-07").empty)
