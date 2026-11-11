# Exercise 3 — Loop Engineering with LangChain Deep Agents

**MSSV:** 25125067  
**Ngày thực hành:** 11/11/2026 (UTC+7)  
**Khóa học:** [DeepLearning.AI — Loop Engineering](https://learn.deeplearning.ai/courses/loop-engineering-with-langchain-deep-agents/lesson/mosoyz/deep-agent-primer)

Đã chạy trực tiếp các bài thực hành miễn phí trong môi trường của khóa học,
lưu notebook có output và các báo cáo sinh ra. Video được bỏ qua theo yêu cầu.
Coding lab chấm điểm và quiz yêu cầu Pro vẫn bị khóa; bộ bài này không xác nhận
hoàn thành hai mục đó hoặc được cấp chứng chỉ.

## Nội dung đã làm

| Bài | Thực hành | Ô code đã chạy | Kết quả |
| --- | --- | ---: | --- |
| L2 | Deep Agent Primer: đọc skills và viết bốn dạng thơ | 5 | Bốn file thơ và trace |
| L3 | Agent Loop: phân tích yêu cầu, phục hồi sau lỗi edit | 7 | 9 model turns, 17 trace steps |
| L4 | Verification Loop: chấm báo cáo bằng rubric | 7 | `satisfied`, một lần chấm |
| L5 | Event-Driven Loop: khởi chạy phân tích rồi sửa requirement | 3 | Hai report, ticket `Analysis Ready` |
| L6 | Learning Loop: đề xuất sửa instruction và so sánh hai batch | 12 | Clarity/depth 20% → 100% trên 5 tài liệu |

Tổng cộng **34 ô code**, không có output lỗi notebook trong năm file
`*_completed.ipynb`. Lỗi công cụ trung gian trong trace L3 được agent xử lý
và được giữ lại làm bằng chứng. Điểm L6 là kết quả trên mẫu nhỏ của bài tập,
không phải đánh giá tổng quát trên dữ liệu mới.

## Cấu trúc

- `01_Notes/Notes.md`: ghi chú, giải thích từng loop và kết quả quan sát.
- `02_Source_Code/L2`, `L3`, `L4`, `L6`: notebook gốc, notebook đã chạy,
  helpers, instruction files và các kết quả.
- `02_Source_Code/L5_event_driven_no_notebook`: mã Flask mô phỏng do khóa học
  cung cấp, bài thực hành bổ sung `event_practice.py`, `L5_completed.ipynb`,
  dữ liệu hai sự kiện và trang ticket đã render.
- `02_Source_Code/student_execution_receipt.json` và `.html`: bảng tổng hợp
  được tạo từ notebook và trace đã lưu; đây là biên bản thực hành tự tổng hợp.
- `02_Source_Code/L6/run_history/v1_live`, `v2_live`: kết quả chạy mới.
  Các thư mục `v1`, `v2` là dữ liệu tham khảo đi kèm khóa học.
- `03_Screenshots`: ảnh chụp thật của trang khóa học khi lưu kết quả và báo cáo.
  Ảnh chỉ hiển thị một phần output; xem notebook và JSON để đọc đầy đủ.
- `Lab05-Loop Engineering.pdf`: đề bài được cung cấp.

## AI đã hỗ trợ như thế nào

Codex hỗ trợ thao tác trên trang học, tải tài liệu, chạy các notebook, đọc trace,
viết ghi chú, tạo bài thực hành sự kiện L5 và kiểm tra bộ file. AI cũng viết
runner lưu output và sửa phần đánh giá L6: lưu instruction `improved` của chính
lần chạy vào `run_history/v2_live/AGENTS.md`, rồi dùng đúng file này cho batch
sau. Bản notebook L6 chạy thành công có sửa đổi đó; notebook nguồn cũng được
sửa để lần chạy tiếp theo dùng cùng logic.

Mã gốc, instruction, rubric và dữ liệu tham khảo thuộc khóa học DeepLearning.AI /
LangChain. Các phần bổ sung và ghi chú có AI hỗ trợ như mô tả ở trên. Các model
trong môi trường khóa học sinh thơ, báo cáo, điểm rubric và đề xuất instruction;
đây không phải những output do sinh viên tự viết thủ công.

## Mở bài và chạy lại

Mở năm notebook `*_completed.ipynb` để xem kết quả đã lưu, không cần gọi API.
Các lần chạy đã ghi nhận dùng model OpenAI do môi trường khóa học cấu hình:
`openai:gpt-5.4-mini`, và analyst L6 dùng `openai:gpt-5.5`.
Không có API key hoặc file `.env` trong bài nộp.

Để chạy lại trên máy riêng, dùng Python **3.12 trở lên**, cài dependencies và
cấu hình `OPENAI_API_KEY` trong môi trường hoặc file `.env` ở `02_Source_Code`:

```powershell
cd 02_Source_Code
python -m pip install -r requirements.txt
python run_course_notebooks.py --lessons L2 L3 L4 L6
cd L5_event_driven_no_notebook
python event_practice.py
```

Runner nhận `--model provider:model_id` nếu muốn đổi model; cần cài adapter
tương ứng và dùng model ID hợp lệ của tài khoản. Không xác nhận đã chạy Gemini
cho bộ bài này. Chạy lại sẽ tạo model calls mới và có thể ghi đè file kết quả;
hành vi và điểm số có thể khác do model không tất định.

Kiểm tra bộ bài **offline**, không gọi model:

```powershell
cd 02_Source_Code
python verify_submission.py
```

Kiểm tra này đối chiếu số ô chạy/lỗi, cú pháp notebook và Python, trace, sự kiện
L5, instruction thật của batch L6 và dữ liệu trong receipt. Kết quả được lưu
trong `validation_report.json`.
