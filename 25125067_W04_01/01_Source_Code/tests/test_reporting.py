from exam_baseline.reporting import render_readable_report


def test_success_report_shows_exam_answers_and_mock_disclaimer(exam_dict):
    result = {
        "status": "success",
        "exam": exam_dict,
        "evaluation": {"provider": "mock", "model": "mock-fixture-v1"},
        "validation": {"constraint_satisfaction_rate": 1, "checks": []},
    }
    report = render_readable_report(result, 200)
    assert "không phải kết quả sinh mới từ model" in report
    assert exam_dict["questions"][0]["stem"] in report
    assert "**Đáp án:** B" in report
    assert "100.0%" in report
    assert "không phải tỷ lệ đáp án đúng" in report


def test_constraint_failure_report_exposes_failed_check_without_inventing_exam():
    result = {
        "status": "constraint_failure",
        "validation": {
            "constraint_satisfaction_rate": 0.5,
            "checks": [
                {"code": "question_count", "passed": False, "expected": 4, "actual": 3},
            ],
        },
    }
    report = render_readable_report(result, 200)
    assert "question_count | CHƯA ĐẠT | 4 | 3" in report
    assert "## Đề thi" not in report


def test_422_report_shows_error_location():
    result = {"detail": [{"loc": ["body", "matrix"], "type": "missing"}]}
    report = render_readable_report(result, 422)
    assert "422" in report
    assert '"matrix"' in report and '"missing"' in report
    assert "Lần chạy chưa tạo được đề hợp lệ" in report


def test_provider_failure_report_keeps_error_code():
    report = render_readable_report(
        {
            "status": "provider_failure",
            "error": {"code": "provider_timeout"},
        },
        504,
    )
    assert "provider_timeout" in report
    assert "## Đề thi" not in report
