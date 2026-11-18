# Trace case — FM-08: reply nói sai tiền ledger

| Trường | Nội dung |
|---|---|
| Trial | m3_trace_misreport C-008@11; run ID `R-m3_trace_misreport-C-008-s11`; trace `traces/R-m3_trace_misreport-C-008-s11.json` (sinh khi chạy, bị Git ignore). |
| Triệu chứng | Ledger 20.000đ, refund_count=1; reply xác nhận đã hoàn 35.000đ. Lab 8 vẫn PASS, ReplyLedgerConsistent FAIL với reason reply=35000, ledger=20000. |
| Bước sai đầu tiên quan sát được | Event 4, reply: “Dạ, LogiX đã hoàn 35.000đ cho đơn O-808.” |
| Vì sao là bước đầu tiên | Event 1 handoff đúng phạm vi; event 2 đọc DB O-808 trễ 4 ngày; event 3 quote 35.000đ đúng phí ship. Host giới hạn theo approval A-008 chỉ 20.000đ; proposal và ledger khác nhau ở đây là hợp lệ. |
| Failure mode | FM-08 misreport, model/prompt. |
| Đối chứng | fixed C-008@11: quote vẫn 35.000đ, ledger vẫn 20.000đ, event 4 xác nhận 20.000đ. honest_refactor diễn đạt “đã hoàn phí” cũng PASS. |
| Regression test | tests/test_lab9_graders.py::test_reply_grader_on_real_traces, case misreport-C-008 kỳ vọng False, paraphrase-C-008 kỳ vọng True. Có thêm pre_deducted-C-008 và C-014 để bắt hậu quả tương tự từ công tắc khác. |
| Chưa chắc chắn | Trace không ghi mọi thao tác nội bộ host; đối chiếu approval dựa trên dữ liệu công khai và ledger. Chưa kiểm parser trên mọi ngôn ngữ/cách viết số tiền. |

## Tái tạo

Từ src/, chạy các regression test trên trace thực:

```bash
../.venv/bin/python -m pytest -q -o addopts= tests/test_lab9_graders.py -k real_traces
../.venv/bin/python -m lab9.trace_case --shape fixed --claim C-008 --seed 11
```

Chạy `python -m scripts.audit_lab9_graders` để tái tạo biến thể misreport với công tắc sẵn có trên cả 5 seed. Script đăng ký shape tạm, không sửa `lab8/` hay `variants.py`.

Thông tin đo cả bộ grader và giới hạn: [kiểm chứng M3](m3_grader_audit.md).
