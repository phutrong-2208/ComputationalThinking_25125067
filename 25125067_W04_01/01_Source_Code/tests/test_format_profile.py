from pydantic import ValidationError

from exam_baseline.format_profiles import HCM_DE11_PASSAGES, HCM_DE11_SECTIONS
from exam_baseline.models import (
    Difficulty,
    ExamMatrix,
    GeneratedExam,
    GenerationRequest,
    Question,
    QuestionType,
    SharedPassage,
    Topic,
)
from exam_baseline.validation import ExamValidator


def profile_request():
    return GenerationRequest(
        matrix=ExamMatrix(
            subject="ĐGNL HCM",
            title="Đề luyện tập",
            duration_minutes=150,
            total_points=120.0,
            question_count=120,
            topics=[
                Topic(id=topic_id, name=name, question_count=end - start + 1)
                for start, end, topic_id, name in HCM_DE11_SECTIONS
            ],
            question_type_distribution={QuestionType.MULTIPLE_CHOICE: 120},
            difficulty_distribution={Difficulty.MEDIUM: 120},
        ),
        include_answers=False,
        include_solutions=False,
        format_profile="hcm_dgnl_de11",
    )


def profile_exam(request):
    section_ids = [
        topic_id for start, end, topic_id, _ in HCM_DE11_SECTIONS for _ in range(start, end + 1)
    ]
    return GeneratedExam(
        title=request.matrix.title,
        subject=request.matrix.subject,
        duration_minutes=request.matrix.duration_minutes,
        total_points=120.0,
        instructions="Chọn một đáp án A, B, C hoặc D.",
        questions=[
            Question(
                id=f"q{i}",
                stem=f"Nội dung câu hỏi số {i}?",
                topic_id=section_ids[i - 1],
                question_type=QuestionType.MULTIPLE_CHOICE,
                difficulty=Difficulty.MEDIUM,
                choices={key: f"Lựa chọn {key} cho câu {i}" for key in "ABCD"},
                points=1.0,
            )
            for i in range(1, 121)
        ],
        shared_passages=[
            SharedPassage(
                start_question=start,
                end_question=end,
                text=f"Đoạn thông tin riêng cho nhóm câu {start} đến {end}, gồm dữ kiện và "
                "bối cảnh để thí sinh đọc trước khi trả lời các câu hỏi liên quan.",
            )
            for start, end in HCM_DE11_PASSAGES
        ],
    )


def failed(report):
    return {check.code for check in report.checks if not check.passed}


def test_profile_accepts_matching_structure():
    request = profile_request()
    assert ExamValidator().validate(profile_exam(request), request).passed


def test_profile_rejects_wrong_order_choices_and_passages():
    request = profile_request()
    exam = profile_exam(request)
    exam.questions[0].topic_id, exam.questions[30].topic_id = (
        exam.questions[30].topic_id,
        exam.questions[0].topic_id,
    )
    exam.questions[1].choices = {"A": "a", "B": "b", "C": "c"}
    exam.shared_passages.pop()
    assert {"profile_section_order", "profile_choice_keys", "profile_passage_ranges"} <= failed(
        ExamValidator().validate(exam, request)
    )


def test_profile_rejects_incompatible_matrix():
    request = profile_request()
    data = request.model_dump()
    data["matrix"]["topics"][0]["question_count"] = 29
    data["matrix"]["topics"][1]["question_count"] = 31
    try:
        GenerationRequest.model_validate(data)
    except ValidationError as exc:
        assert "five fixed section counts" in str(exc)
    else:
        raise AssertionError("incompatible matrix was accepted")
