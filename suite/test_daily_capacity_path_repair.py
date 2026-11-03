"""Regression test for saved plan paths pointing to a previous extracted release."""
import ast
from pathlib import Path


def test_stale_saved_capacity_path_falls_back_to_bundled_workbook(tmp_path):
    app = Path(__file__).parents[1] / "apps" / "daily" / "daily_planner_app.py"
    tree = ast.parse(app.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_repair_capacity_path")
    namespace = {"Path": Path, "_resolve_central": lambda _name: None, "__file__": str(app)}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(app), "exec"), namespace)
    bundled = Path(__file__).parents[1] / "apps" / "daily" / "CAPACITY_DATABASE.xlsx"
    assert bundled.is_file()
    stale = tmp_path / "rc14" / "apps" / "daily" / "CAPACITY_DATABASE.xlsx"
    result = namespace["_repair_capacity_path"](stale)
    assert result == bundled.resolve()


def test_valid_custom_capacity_path_is_preserved(tmp_path):
    app = Path(__file__).parents[1] / "apps" / "daily" / "daily_planner_app.py"
    tree = ast.parse(app.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_repair_capacity_path")
    namespace = {"Path": Path, "_resolve_central": lambda _name: None, "__file__": str(app)}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(app), "exec"), namespace)
    chosen = tmp_path / "approved_capacity.xlsx"
    chosen.write_bytes(b"test")
    assert namespace["_repair_capacity_path"](chosen) == chosen.resolve()
