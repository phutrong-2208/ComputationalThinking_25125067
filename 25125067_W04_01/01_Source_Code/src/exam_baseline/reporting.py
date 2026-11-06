"""Human-readable Vietnamese reports for saved API responses; no model calls."""

import json
from typing import Any


def table_value(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return text[:300].replace("|", "\\|").replace("\n", " ")


def render_readable_report(result: dict[str, Any], http_status: int) -> str:
    status = result.get("status", "request_failure")
    evaluation = result.get("evaluation") or {}
    offline = evaluation.get("provider") == "mock"
    lines = [
        "# Kết quả chạy thử sinh đề",
        "",
        f"- HTTP: **{http_status if http_status else 'không có phản hồi'}**",
        f"- Trạng thái: **{status}**",
        f"- Provider: `{evaluation.get('provider', 'không có')}`",
        f"- Model: `{evaluation.get('model', 'không có')}`",
        f"- Mã lần chạy: `{evaluation.get('run_id', 'không có')}`",
        "",
    ]
    if offline:
        lines += [
            "> Đây là đề MẪU từ mock, không phải kết quả sinh mới từ model.",
            "",
        ]
    if status == "success":
        lines += [
            "Tất cả kiểm tra tự động đã đạt. Nội dung, đáp án và độ khó vẫn cần người đọc duyệt.",
            "",
        ]
    elif status == "constraint_failure":
        lines += ["Đã có đề, nhưng còn yêu cầu chưa đạt. Xem bảng kiểm tra ở dưới.", ""]
    else:
        lines += ["Lần chạy chưa tạo được đề hợp lệ. Xem chi tiết lỗi ở cuối file.", ""]

    exam = result.get("exam")
    if exam:
        lines += [
            "## Đề thi",
            "",
            f"**{exam['title']}**",
            "",
            f"Môn: {exam['subject']} · Thời gian: {exam['duration_minutes']} phút · "
            f"Tổng điểm khai báo: {exam['total_points']}",
            "",
            exam["instructions"],
            "",
        ]
        for index, question in enumerate(exam["questions"], start=1):
            lines += [
                f"### Câu {index} — {question['points']} điểm",
                "",
                question["stem"],
                "",
            ]
            for key, choice in question.get("choices", {}).items():
                lines.append(f"- **{key}.** {choice}")
            if question.get("choices"):
                lines.append("")
            lines += [
                f"- Mã câu: `{question['id']}`",
                f"- Chủ đề: `{question['topic_id']}`",
                f"- Loại câu: `{question['question_type']}`",
                f"- Nhãn độ khó: `{question['difficulty']}`",
                f"- Nguồn câu: `{question.get('source_question_id') or 'không dẫn nguồn'}`",
                "",
                f"**Đáp án:** {question.get('answer') or 'Không được trả về.'}",
                "",
                f"**Lời giải:** {question.get('solution') or 'Không được trả về.'}",
                "",
            ]
    report = result.get("validation")
    if report:
        rate = report["constraint_satisfaction_rate"]
        lines += [
            "## Kiểm tra tự động",
            "",
            f"Tỷ lệ đạt: **{rate:.1%}**. Đây là tỷ lệ kiểm tra cấu trúc/nhãn, "
            "không phải tỷ lệ đáp án đúng.",
            "",
            "| Kiểm tra | Kết quả | Yêu cầu | Thực tế |",
            "| --- | --- | --- | --- |",
        ]
        for check in report["checks"]:
            cells = [
                table_value(check["code"]),
                "ĐẠT" if check["passed"] else "CHƯA ĐẠT",
                table_value(check.get("expected")),
                table_value(check.get("actual")),
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines += [
            "",
            "## Phần bạn cần đọc và đánh giá",
            "",
            "- Câu hỏi có đúng kiến thức và rõ nghĩa không?",
            "- Đáp án/lời giải có đúng không?",
            "- Chủ đề, mục tiêu học tập và mức dễ/vừa/khó có phù hợp thực tế không?",
            "- Các câu có lặp ý không? Thời gian làm bài có hợp lý không?",
            "- Các yêu cầu viết bằng ngôn ngữ tự nhiên có được đáp ứng không?",
            "",
            "Các lưu ý chi tiết do backend trả về:",
            "",
        ]
        lines += [f"- {item}" for item in report.get("semantic_review_required", [])]
        lines.append("")
    if evaluation:
        usage = evaluation.get("usage") or {}
        lines += [
            "## Thông số lần chạy",
            "",
            f"- Phiên bản prompt: `{evaluation.get('prompt_version')}`",
            f"- Thời gian gọi model: {evaluation.get('generation_latency_ms')} ms",
            f"- Tổng thời gian xử lý: {evaluation.get('total_latency_ms')} ms",
            f"- Input tokens: {usage.get('input_tokens')}",
            f"- Output tokens: {usage.get('output_tokens')}",
            f"- Chi phí ước lượng: {evaluation.get('estimated_cost_usd')} USD",
            "",
            "`null`/`None` nghĩa là không có số liệu. Chi phí dựa trên giá trong cấu hình; "
            "số 0 không xác nhận tài khoản đang ở Free Tier.",
            "",
        ]
    error = result.get("error") or result.get("detail")
    if error:
        lines += [
            "## Chi tiết lỗi",
            "",
            "```json",
            json.dumps(error, ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    if result.get("warnings"):
        lines += ["## Lưu ý của backend", ""]
        lines += [f"- {warning}" for warning in result["warnings"]]
        lines.append("")
    lines += [
        "## File đi kèm",
        "",
        "- [response.json](response.json): toàn bộ phản hồi gốc, không rút gọn.",
        "- [request.json](request.json): dữ liệu đầu vào đã gửi cho lần chạy này.",
        "",
    ]
    return "\n".join(lines)
