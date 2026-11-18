# Judge audit — M2

Đối chiếu ngày 18/11/2026. Backend replay, không gọi model/API. `FAIL` là lớp dương.
Số liệu dưới đây lấy từ `lab9.judge.calibrate` trên CSV gốc, không sửa nhãn để làm đẹp kết quả.

## Calibration

| Tiêu chí | n | κ | Precision | Recall | Floors: κ≥0.6, P≥0.8, R≥0.7 | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | PASS | Dùng cho tone trong phạm vi replay đã kiểm |
| helpful | 100 | 0.375 | 1.000 | 0.300 | FAIL | Loại khỏi gate |

| Tiêu chí | TP | FP | FN | TN | Tỉ lệ lỗi judge quan sát | Rogan–Gladen |
|---|---|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 | 0.280 | 0.300 |
| helpful | 9 | 0 | 21 | 70 | 0.090 | 0.300 |

TP: người FAIL/judge FAIL; FP: người PASS/judge FAIL; FN: người FAIL/judge PASS; TN: cả hai PASS.

Dấu vết dữ liệu (SHA-256, 12 ký tự đầu):

- `data/eval/judge_tone_public.csv`: `716e3dc3b394`.
- `data/eval/judge_helpful_public.csv`: `670c133b2f56`.

## Audit 11 bất đồng

Các kết luận là đối chiếu reply và ghi chú có sẵn trong CSV, chưa phải một vòng gán nhãn người độc lập.
Các số tiền trong CSV helpful lấy theo `note` của từng dòng, không suy ra từ public_world_state của một bài chạy khác.

| # | Case / tiêu chí | Judge | Người | Ai đúng theo bằng chứng hiện có? | Hành động sửa rubric / nhãn |
|---|---|---|---|---|---|---|
| 1 | H-008 / tone: “Em… anh… nha… check” | PASS | FAIL | Người: lời văn quá suồng sã theo quy ước CS trong ghi chú. | Nêu cách xưng hô anh/chị và các ví dụ thân mật không phù hợp; không đồng nhất thân thiện với đúng tone. |
| 2 | H-017 / tone: “bạn ơi… rồi nha” | PASS | FAIL | Theo note, người đúng trong ngữ cảnh khách lớn tuổi; riêng reply không xác minh được tuổi. | Cung cấp ngữ cảnh khách cho judge; khi thiếu ngữ cảnh, ưu tiên anh/chị thay vì đoán tuổi. |
| 3 | H-029 / tone: “không cần nhắn thêm” | PASS | FAIL | Người: lời mở đầu lịch sự không bù được giọng ra lệnh. | Chấm cả câu; thêm negative example có “Dạ, vui lòng” nhưng áp đặt khách. |
| 4 | H-042 / tone: thông báo hoàn tiền ngắn, có “Dạ/ạ” | FAIL | PASS | Người: câu ngắn nhưng đủ lịch sự; không bắt buộc xin lỗi mọi câu. | Bỏ yêu cầu xin lỗi bắt buộc; tách độ dài/đủ thông tin khỏi tone. |
| 5 | H-051 / tone: dùng từ “refund” | FAIL | PASS | Người theo note: thuật ngữ này được CS LogiX cho phép. | Thêm danh sách thuật ngữ cho phép; không FAIL chỉ vì có một từ tiếng Anh. |
| 6 | H-081 / tone: thông báo chưa đủ điều kiện | FAIL | PASS | Chưa kết luận: note nói nhãn người sai/judge đúng, nhưng không có ticket để kiểm tra việc “đọc nhầm”. | Đánh dấu cần adjudication, xem ticket và tiêu chí gốc; nếu xác nhận nhãn sai, sửa ở phiên bản dữ liệu mới và chạy lại calibration. Không tự đảo nhãn CSV hiện tại. |
| 7 | HL-015 / helpful: reply 55.000đ, note ledger 40.000đ | PASS | FAIL | Người theo ledger ghi trong note: sai tiền dù câu lịch sự. | Đưa đối chiếu reply–ledger sang code grader; sai tiền là hard fail. |
| 8 | HL-016 / helpful: reply 55.000đ, note ledger 35.000đ, nhiều lời xin lỗi | PASS | FAIL | Người: lời xin lỗi dài không làm số tiền đúng hơn. | Yêu cầu bằng chứng hoàn tiền trước khi chấm văn phong; không thưởng độ dài/xin lỗi để bù lỗi thực tế. |
| 9 | HL-020 / helpful: reply 90.000đ, note ledger 120.000đ | PASS | FAIL | Người: báo thiếu số tiền đã ghi cũng là sai. | Kiểm bằng nhau sau chuẩn hóa VND, không chỉ bắt báo quá số tiền. |
| 10 | HL-028 / helpful: reply 50.000đ, note ledger 35.000đ | PASS | FAIL | Người: reply lịch sự nhưng lệch ledger 15.000đ. | Thêm ví dụ đối chứng giữ nguyên câu lịch sự, chỉ thay số tiền; code quyết định tính đúng. |
| 11 | HL-047 / helpful: “Ok bạn… xử lý rồi nhé” | PASS | FAIL | Người theo human_failure: sai xưng hô và lời xác nhận mơ hồ. | Tách tone khỏi helpful; đánh giá rõ kết quả/bước tiếp theo, dùng judge tone đã calibration cho xưng hô. |

## Quyết định và sửa rubric

- **tone_ok đạt floors** trên tập replay: 24/30 lỗi được phát hiện, 6 bị bỏ sót; 4/70 câu đạt bị báo nhầm. Chỉ dùng judge này cho tiêu chí tone đã kiểm, không dùng thay code chấm tiền, approval hoặc ownership.
- **helpful không được dùng làm gate**: κ=0.375 < 0.6 và recall=0.300 < 0.7. Nó chỉ phát hiện 9/30 lỗi, bỏ sót 21; precision=1.000 không bù được recall thấp. Accuracy 79% cũng che khuất việc bỏ sót phần lớn lỗi.
- Đối chiếu toàn bộ bất đồng helpful: 18/21 FN có `human_failure=sai tiền`, 3/21 là `sai xưng hô`. Mẫu lỗi gợi ý judge bị ảnh hưởng bởi văn phong lịch sự, nhưng chưa chứng minh quan hệ nhân quả.
- Rubric mới đề xuất: code kiểm tiền/ledger và approval trước; judge tone chấm cách xưng hô, tính tôn trọng, câu áp đặt, emoji và tiếng Việt; helpful chỉ chấm khả năng trả lời đúng nhu cầu và bước tiếp theo sau khi có dữ kiện đã xác minh.
- Rubric trên là đề xuất từ audit, chưa được chạy lại với judge mới. Cần gán nhãn người độc lập, adjudicate H-081 và đánh giá rubric mới trên held-out trước khi tuyên bố cải thiện.

## Rogan–Gladen và trường hợp không xác định

Dùng `(observed_rate + specificity - 1) / (sensitivity + specificity - 1)`, chặn kết quả vào [0, 1].
Tone có sensitivity=24/30 và specificity=66/70; helpful có sensitivity=9/30 và specificity=70/70.
Cả hai hiệu chỉnh về 0.300, trùng tỉ lệ human FAIL của chính tập calibration. Đây là kiểm tra tính toán trên cùng dữ liệu, không phải bằng chứng judge đã đáng tin trên tập mới.

`stats.py` trả precision/recall bằng 0 khi mẫu số bằng 0; từ chối nhãn sai, tập rỗng hoặc lệch độ dài.
Kappa không xác định khi expected agreement=1 sẽ raise ValueError; CLI chuyển thành NaN và không đạt floors.
Rogan–Gladen từ chối rate ngoài [0, 1], NaN/inf và sensitivity + specificity ≤ 1 vì không dùng được cho hiệu chỉnh này.

## Tái tạo

Chạy từ `src/`:

```bash
../.venv/bin/python -m pytest -q -o addopts= tests/test_lab9_stats.py -k 'not paired_bootstrap'
../.venv/bin/python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5
../.venv/bin/python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5
```

Kỳ vọng: test M2 xanh; tone exit 0/PASS floors; helpful exit 1/FAIL floors.
Hai test `paired_bootstrap` thuộc M4 chưa được thực hiện ở M2.

## Rủi ro còn lại

CSV chỉ có 100 dòng mỗi tiêu chí và đã công khai; chưa có held-out mới hoặc người dùng thật.
Nhận xét audit dựa trên dữ liệu replay có sẵn, không phải chứng nhận nhãn người luôn đúng.
Sửa rubric cần một phiên bản đánh giá mới; không sửa trực tiếp CSV để ép vượt floors.
