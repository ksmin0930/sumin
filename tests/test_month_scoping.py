"""월말 잔고는 다른 기준월과 절대 함께 집계되지 않도록 검증한다."""
import ast
from pathlib import Path
import unittest

import pandas as pd


def load_helpers():
    tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    wanted = {
        "norm", "find_col", "month_label", "month_key", "money", "filter_month",
        "input_frame_for_month", "flagged_fund_amount", "dashboard_fund_metrics",
    }
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    module = ast.Module(body=nodes, type_ignores=[])
    namespace = {
        "pd": pd, "re": __import__("re"), "Iterable": __import__("typing").Iterable,
        "OPERATING_RESTRICTED_DEPOSITS": ("청년육성적립금", "생산안정적립금", "농업살림기금"),
    }
    exec(compile(ast.fix_missing_locations(module), "app.py", "exec"), namespace)
    return namespace["input_frame_for_month"]


def load_metric_helpers():
    tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    wanted = {
        "norm", "find_col", "month_label", "month_key", "money", "filter_month",
        "flagged_fund_amount", "category_amount", "operating_restricted_deposit_amount",
        "dashboard_fund_metrics",
    }
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    module = ast.Module(body=nodes, type_ignores=[])
    namespace = {
        "pd": pd, "re": __import__("re"), "Iterable": __import__("typing").Iterable,
        "OPERATING_RESTRICTED_DEPOSITS": ("청년육성적립금", "생산안정적립금", "농업살림기금"),
    }
    exec(compile(ast.fix_missing_locations(module), "app.py", "exec"), namespace)
    return namespace["dashboard_fund_metrics"]


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

    def test_y_n_changes_update_restricted_and_available_cards(self):
        dashboard_fund_metrics = load_metric_helpers()
        source = pd.DataFrame(
            {
                "기준월": ["2026-07"] * 6 + ["2026-06"],
                "대분류": ["보통예금", "보통예금", "보통예금", "보통예금", "정기예금", "미수금", "보통예금"],
                "세부항목": ["운영계좌", "농업살림기금", "생산안정적립금", "청년육성적립금", "정기예금", "회비미수금", "이전달 항목"],
                "금액": [100_000_000, 20_000_000, 30_000_000, 40_000_000, 200_000_000, 50_000_000, 999_999_999],
                "용도제한여부": ["N", "Y", "Y", "Y", "Y", "N", "Y"],
                "운영가능차감여부": ["N", "Y", "Y", "Y", "N", "N", "Y"],
            }
        )

        restricted, available = dashboard_fund_metrics(
            source, "2026-07", 1, 2
        )

        self.assertEqual(restricted, 290_000_000)
        self.assertEqual(available, 150_000_000)
