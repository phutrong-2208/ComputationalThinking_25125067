"""Execute the course notebooks and retain real outputs, including failures.

Run from this directory with a configured API key, for example:
    python run_course_notebooks.py --lessons L4 L6
    python run_course_notebooks.py --lessons L3 --model provider:model_id
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import nbformat
from nbclient import NotebookClient


def prepare_notebook(notebook, lesson, model=None):
    """Keep the course logic, with one fix to the learning-loop comparison."""
    export_markers = (
        "course_materials.zip", "contains L2/L2.ipynb:",
        "Full course materials packaged:", "# Student execution batch:",
        "# Student event-driven practice:", "# Student completion export:",
    )
    notebook.cells = [cell for cell in notebook.cells
                      if not any(marker in cell.source for marker in export_markers)]
    if lesson == "L6":
        for cell in notebook.cells:
            if cell.cell_type != "code":
                continue
            if ("improved = apply_change(change, baseline)" in cell.source
                    and "improved_agents_path =" not in cell.source):
                cell.source += (
                    "\n# Evaluate the change proposed in THIS run.\n"
                    "improved_agents_path = Path('run_history/v2_live/AGENTS.md')\n"
                    "if USE_LIVE_LLM:\n"
                    "    improved_agents_path.parent.mkdir(parents=True, exist_ok=True)\n"
                    "    improved_agents_path.write_text(improved, encoding='utf-8')\n"
                )
            cell.source = cell.source.replace(
                'agents_md=Path("run_history/v2/AGENTS.md")',
                "agents_md=improved_agents_path",
            )
    if model:
        for cell in notebook.cells:
            if cell.cell_type == "code":
                cell.source = cell.source.replace("openai:gpt-5.4-mini", model)
                cell.source = cell.source.replace("openai:gpt-5.5", model)
    return notebook


def run_lessons(root, lessons, model=None, timeout=1800):
    root = Path(root).resolve()
    records = []
    manifest = root / "execution_manifest.json"
    if manifest.is_file():
        records = json.loads(manifest.read_text(encoding="utf-8"))
    current = []
    for lesson in lessons:
        if lesson not in {"L2", "L3", "L4", "L6"}:
            raise ValueError(f"Unknown lesson: {lesson}")
        folder = root / lesson
        notebook = prepare_notebook(nbformat.read(folder / f"{lesson}.ipynb", as_version=4), lesson, model)
        output = folder / f"{lesson}_completed.ipynb"
        record = {
            "lesson": lesson,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "mode": "live",
            "model_override": model,
            "notebook": str(output.relative_to(root)),
            "status": "running",
        }
        print(f"START {lesson}", flush=True)

        def cell_started(cell, cell_index, **_):
            if cell.cell_type == "code":
                print(f"  {lesson} cell {cell_index}", flush=True)

        try:
            NotebookClient(
                notebook, timeout=timeout, kernel_name="python3",
                resources={"metadata": {"path": str(folder)}},
                on_cell_start=cell_started,
            ).execute()
            record["status"] = "passed"
        except Exception as error:
            record["status"] = "failed"
            record["error_type"] = type(error).__name__
            print(f"FAILED {lesson}: {type(error).__name__}", flush=True)
        finally:
            nbformat.write(notebook, output)
            record["finished_at"] = datetime.now(timezone.utc).isoformat()
            record["executed_cells"] = sum(
                cell.cell_type == "code" and cell.get("execution_count") is not None
                for cell in notebook.cells
            )
            record["error_outputs"] = sum(
                out.output_type == "error"
                for cell in notebook.cells for out in cell.get("outputs", [])
            )
            records.append(record)
            current.append(record)
            manifest.write_text(json.dumps(records, indent=2), encoding="utf-8")
            print(f"FINISH {lesson}: {record['status']}; {record['executed_cells']} code cells", flush=True)
    return current


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lessons", nargs="+", choices=["L2", "L3", "L4", "L6"], default=["L4", "L6"])
    parser.add_argument("--model", help="Optional LangChain provider:model ID.")
    args = parser.parse_args()
    from dotenv import load_dotenv
    explicit_env = os.getenv("GEMINI_ENV_FILE")
    if explicit_env:
        load_dotenv(explicit_env, override=False)
    root = Path(__file__).resolve().parent
    load_dotenv(root / ".env", override=False)
    records = run_lessons(root, args.lessons, model=args.model)
    return 0 if all(record["status"] == "passed" for record in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
