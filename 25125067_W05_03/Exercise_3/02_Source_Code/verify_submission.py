"""Validate saved evidence offline, without importing agents or calling APIs."""
import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import nbformat
from IPython.core.inputtransformer2 import TransformerManager

from run_course_notebooks import prepare_notebook


def main():
    root = Path(__file__).resolve().parent
    expected = {"L2": 5, "L3": 7, "L4": 7, "L5": 3, "L6": 12}
    receipt = json.loads((root / "student_execution_receipt.json").read_text())
    records = []
    for lesson, count in expected.items():
        folder = "L5_event_driven_no_notebook" if lesson == "L5" else lesson
        notebook = nbformat.read(root / folder / f"{lesson}_completed.ipynb", 4)
        code = [c for c in notebook.cells if c.cell_type == "code"]
        errors = [o for c in code for o in c.get("outputs", []) if o.output_type == "error"]
        assert len(code) == count
        assert all(c.get("execution_count") is not None for c in code)
        assert not errors
        row = next(r for r in receipt["lessons"] if r["lesson"] == lesson)
        assert row["executed_code_cells"] == count and row["error_outputs"] == 0
        records.append({"lesson": lesson, "executed_code_cells": count, "error_outputs": 0})

    transformer = TransformerManager()
    notebooks = list(root.rglob("*.ipynb"))
    cells = 0
    for path in notebooks:
        notebook = nbformat.read(path, 4)
        nbformat.validate(notebook)
        for cell in notebook.cells:
            if cell.cell_type == "code":
                compile(transformer.transform_cell(cell.source), str(path), "exec",
                        flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
                cells += 1
    scripts = list(root.rglob("*.py"))
    for path in scripts:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    l5 = json.loads((root / "L5_event_driven_no_notebook/L5_practice_results.json").read_text())
    assert l5 == receipt["L5_events"]
    assert l5["triggered_runs"] == 2 and l5["report_versions"] == [1, 2]
    assert l5["requirement_versions"] == [1, 2]
    assert l5["final_ticket_status"] == "Analysis Ready" and not l5["human_marked_done"]

    l6 = root / "L6"
    for label, key in [("v1_live", "L6_before"), ("v2_live", "L6_after")]:
        summary = json.loads((l6 / "run_history" / label / "summary.json").read_text())
        assert summary == receipt[key]
        assert len(list((l6 / "run_history" / label).glob("run_*.json"))) == 5
    proposal = SimpleNamespace(**json.loads((l6 / "run_history/proposal_v1_live.json").read_text()))
    tree = ast.parse((root / "hill_climbing.py").read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "apply_change")
    function.returns = None
    for arg in function.args.args:
        arg.annotation = None
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "apply_change", "exec"), namespace)
    baseline = (l6 / "workspace/memories/AGENTS.md").read_text()
    improved = namespace["apply_change"](proposal, baseline)
    assert improved == (l6 / "run_history/v2_live/AGENTS.md").read_text()
    for path in (l6 / "run_history/v2_live").glob("ws_*/memories/AGENTS.md"):
        assert path.read_text() == improved
    source = nbformat.read(l6 / "L6.ipynb", 4)
    once = prepare_notebook(copy.deepcopy(source), "L6")
    twice = prepare_notebook(copy.deepcopy(once), "L6")
    assert [c.source for c in once.cells] == [c.source for c in twice.cells]
    assert any("agents_md=improved_agents_path" in c.source for c in once.cells)

    report = {"status": "passed", "mode": "offline evidence validation",
              "lessons": records, "notebooks_validated": len(notebooks),
              "code_cells_syntax_checked": cells, "python_files_syntax_checked": len(scripts),
              "L5_events_match_receipt": True, "L6_proposal_matches_evaluated_instructions": True,
              "runner_preparation_is_idempotent": True}
    (root / "validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
