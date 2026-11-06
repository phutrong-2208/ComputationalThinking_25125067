import json
import subprocess
import sys
from pathlib import Path

from exam_baseline.latex_export import latex_text


def test_latex_text_escapes_prose_and_preserves_math():
    assert latex_text(r"Tỉ lệ 50% & $x_1+2$ là đúng") == (r"Tỉ lệ 50\% \& $x_1+2$ là đúng")


def test_cli_exports_three_tex_files_with_template_and_material(tmp_path):
    root = Path(__file__).parents[1]
    case = root / "examples/mini/01_text"
    material = tmp_path / "material.txt"
    material.write_text("Nguồn kiến thức cho đề mới", encoding="utf-8")
    output = tmp_path / "run"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "exam_baseline.mini_cli",
            "--request",
            str(case / "input.json"),
            "--fixture",
            str(case / "composer_fixture.json"),
            "--template",
            str(root / "examples/latex_template.tex"),
            "--material",
            str(material),
            "--prompt",
            "Tăng tính thực tiễn",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    paths = json.loads(result.stdout)["latex"]
    assert set(paths) == {"exam", "answer_key", "answer_sheet"}
    exam = (output / "de_thi.tex").read_text(encoding="utf-8")
    key = (output / "dap_an.tex").read_text(encoding="utf-8")
    sheet = (output / "phieu_tra_loi.tex").read_text(encoding="utf-8")
    assert "\\begin{document}" in exam and "\\textbf{Câu 1.}" in exam
    assert "\\textbf{Câu 1:" in key
    assert "Số báo danh" in sheet
    assert "%% ASTRA_BODY %%" not in exam
    assert "Nguồn kiến thức cho đề mới" not in exam
