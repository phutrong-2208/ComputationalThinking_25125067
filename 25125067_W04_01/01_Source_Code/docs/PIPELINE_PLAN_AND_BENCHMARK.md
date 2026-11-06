# Pipeline bốn agent — native LaTeX, một phản hồi rồi người dùng duyệt

Workflow `cisr-v3`, thay chính sách PNG/hex và vòng sửa của `cisr-v2`.
Bản kế hoạch dài/ngắn cũ giữ làm tài liệu lịch sử; policy dưới đây là hiện hành.

## Bốn agent và Orchestrator

| Agent | Input | Output |
| --- | --- | --- |
| Composer | Ma trận, nguồn, yêu cầu; feedback Reviewer nếu có | Nội dung đề có cấu trúc, công thức LaTeX, spec hình |
| Illustrator | Nội dung học sinh + spec; không nhận đáp án | `IllustrationBook`: code TikZ/PGFPlots cho từng hình |
| Solver | File LaTeX đã ghép + đề học sinh, code hình | `SolutionBook`: giải độc lập, đáp án, khả năng giải được |
| Reviewer | Cùng file LaTeX, ma trận và lời giải Solver | `ReviewReport`: lỗi có vị trí/bằng chứng và yêu cầu sửa |

Bốn lớp agent ở `pipeline/agents.py`, prompt riêng, provider/model cấu hình riêng.
Có thể dùng cùng một model để khởi đầu; mỗi agent vẫn là lượt gọi độc lập.
Orchestrator là Python: giao tiếp giữa các agent, kiểm schema/budget/hash và ghép đề.
ID/revision/hash do Orchestrator gắn; agent chỉ trả nội dung, tránh lỗi chép hash.
Lỗi format mức minor cũng có thể yêu cầu Composer sửa qua đúng một feedback.
Response từng stage lưu riêng trong `_internal/` để chẩn đoán, không đưa vào đề học sinh.
Không cần thêm một model chỉ để điều phối.

```text
Composer → Illustrator → ghép native LaTeX → Solver → Reviewer (một lượt)
                                                        |
                                      có lỗi: feedback một lần về Composer
                                                        |
                            Composer → Illustrator → ghép → Solver kiểm lại
                                                        |
                                    DỪNG → NGƯỜI DÙNG KIỂM TRA BẰNG MẮT
```

Không có lỗi thì chuyển thẳng sang người dùng. Có lỗi thì feedback luôn đi về Composer,
kể cả issue ban đầu chỉ vào lời giải hoặc hình. Không sửa riêng Solver rồi gọi Reviewer
lại. Reviewer không chạy lượt hai; callback Composer đúng một lần, không retry callback.
Nếu callback không tạo được draft đúng cấu trúc thì báo lỗi, giữ artifact nội bộ, không
bịa một file cuối. JSON/schema của C/I/S ban đầu có thể sửa tối đa một lần theo config;
Reviewer không retry kể cả trả sai schema. `max_repair_rounds` cố định bằng 1, không nhận 2.

Bình thường **4 calls**, có feedback **7 calls**, chưa tính sửa schema/format. `max_provider_calls`
mặc định 12, deadline 120 giây/call và 600 giây/run; mọi call/failure có trace.
Sau sửa, revision tăng, code hình và solution cũ mất hiệu lực. Review ở revision 1 chỉ
là bản góp ý lịch sử, không được ghi thành review của revision 2.

## Input, merge và đầu ra

Dùng input JSON mini hiện tại, thêm `workflow` nếu cần. JSON là contract nội bộ, không
phải đề cuối. Template tùy chọn: một `%% ASTRA_BODY %%` trong body; body không chứa đề mẫu.
Công thức dùng `$...$`, `\(...\)` hoặc `\[...\]`. Native code chỉ gồm một tikzpicture
cho mỗi hình; hỗ trợ PGFPlots axis, addplot biểu thức/toạ độ, draw/node/coordinate.
Chặn input file, addplot table/graphics/gnuplot, directlua, macro/loop và lệnh ngoài tập
hỗ trợ. Compiler chạy no-shell-escape. Kiểm tĩnh không chứng minh mọi source biên dịch được.

Orchestrator ghép text Composer và code Illustrator thành `merged.tex` trước khi Solver
được gọi. Hash được tính từ chính file nguồn đã ghép; review còn gắn hash của lời giải.
Solver không nhận đáp án Composer, bank, evidence hay context riêng. Code hình của
Illustrator là dữ kiện của đề nên được gửi cho Solver; không giả vờ đó là ảnh đã render.
S/R kiểm tra toán và source, chưa tự xác nhận bố cục/nhãn PDF bằng vision.

Đầu ra chính **một `de_thi.tex` có TikZ/PGFPlots đọc/sửa được**, không PNG, hex, Lua hay
file ảnh phụ thuộc. Biên dịch bằng **XeLaTeX hoặc LuaLaTeX**. CLI `--compile` yêu cầu có
compiler terminal và compile thành công. Editor Codex có compiler riêng, không phụ thuộc
việc PATH có cài TeX. Không có compile thành công thì status chỉ là `static`.

Mọi đề xuất ra đều `quality_decision=pending_human_review`, `human_review_required=true`.
`_internal/human_review.md` ghi các điểm Reviewer/Solver nêu, cùng request/draft từng revision,
`illustrations.json`, `merged.tex`, solutions, review và trace. Không gửi `_internal/` cho
học sinh. API V2 trả file `.tex` cùng header yêu cầu human review; không coi HTTP 200 là
người dùng đã duyệt hoặc máy xác nhận chất lượng thị giác.

## Cấu hình và tối ưu sau này

```json
"workflow": {
  "composer": {"model": "MODEL_COMPOSER"},
  "illustrator": {"model": "MODEL_ILLUSTRATOR"},
  "solver": {"model": "MODEL_SOLVER"},
  "reviewer": {"model": "MODEL_REVIEWER"},
  "max_repair_rounds": 1,
  "max_provider_calls": 12
}
```

Tên trên là placeholder, thay bằng model được tài khoản cấp quyền hoặc bỏ các object
đó để kế thừa `.env`. Các vai trò có thể inject provider khác nhau bằng Python; CLI
hiện dùng chung endpoint/key. Vision không bắt buộc cho workflow source hiện tại.
Có thể thử model nhẹ cho Illustrator, model mạnh hơn cho Solver/Reviewer, CAS cho phép
tính, chia đề dài theo nhóm câu và cache theo hash. Chỉ tối ưu sau benchmark; không thay
policy một feedback và bước người dùng kiểm tra bằng mắt. Giá/token kế thừa `.env` hoặc
ghi đè hai trường input/output_price_per_million theo role; thiếu usage/giá là unknown.

## Benchmark

```powershell
.\.venv-win\Scripts\python.exe -m exam_baseline.pipeline.benchmark --manifest examples/pipeline/pilot.json --output runs/benchmark/pilot
```

Pilot có **10 request synthetic × 2 repeats × 2 hệ thống** = 40 attempts. Mặc định replay
không gọi API: chỉ kiểm plumbing/validator/trace. Thêm `--mode live` mới đo model thật;
giữ cùng request và ghi config/model. Đề hình tách track; baseline text không hỗ trợ hình.

Lưu `attempts.jsonl`, `attempts.csv`, `metrics.json` và artifacts từng attempt. Sáu nhóm:
đạt ma trận; độ đúng câu; hình dùng được; recall/precision/false alarm của Reviewer;
median/max latency; calls/tokens/cost coverage. Failed attempts không bị loại khỏi mẫu số.
Độ đúng/hình/defect cần nhãn độc lập, mặc định là `null`, không lấy Reviewer làm gold.
Nhãn người chấm đưa qua `--human-labels labels.json`, không đi vào prompt:

```json
{
  "pipeline/text_01/1": {
    "requested_questions": 4, "correct_questions": 3,
    "required_figures": 0, "usable_figures": 0,
    "gold_defects": 1, "true_positive_defects": 1, "predicted_defects": 2,
    "clean_case": false, "false_alarm": false
  }
}
```

Ví dụ số liệu trên là minh họa, không phải nhãn có sẵn. Báo tỷ lệ được chấm cùng các
điểm chất lượng, không suy rộng điểm subset thành cả bộ test.

Bộ Reviewer riêng có **10 clean/10 seeded sai key số học**, gold chỉ ở evaluator:

```powershell
.\.venv-win\Scripts\python.exe -m exam_baseline.pipeline.reviewer_benchmark --output runs/benchmark/reviewer
```

Mặc định replay để kiểm scorer. Thêm `--mode live` đo model thật trên bộ hẹp này. Scorer
match code + question ID; chưa thay thế người chấm evidence hay các lỗi nội dung/hình
phức tạp. Không dùng kết quả replay để tuyên bố Reviewer bắt lỗi tốt.
