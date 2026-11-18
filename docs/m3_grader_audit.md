# Kiểm chứng grader M3

Chạy ngày 18/11/2026, MockLLM, 14 claim công khai × 5 seed (11, 22, 33, 44, 55).
Eval set SHA: `391b65dab542`; metric spec v1.1.

## Tỉ lệ phát hiện và báo nhầm

| Tập | Số trial | Kết quả |
|---|---|---|
| Trial lỗi xác nhận từ 8 công tắc lỗi | 140 | Bắt 135/140 = 96.43% (yêu cầu ≥80%) |
| fixed + honest_refactor | 140 | Báo nhầm 0.00% (yêu cầu ≤10%) |
| Trial không lỗi trong các biến thể có công tắc | 420 | Báo nhầm 0.00% |

Chạy đủ 8 × 14 × 5 = 560 trial biến thể và 140 trial đối chứng.
Tập lỗi dựa trên kết quả Lab 8 cộng các case FM-08 đã đối chiếu thủ công: misreport/pre_deducted trên C-008/C-014.
Bộ phát hiện dùng SecretLeak, ApprovalBypass, RefundAmountCorrect, DbFactKept và ReplyLedgerConsistent; không dùng TrialPass để tính tỉ lệ phát hiện.

| Công tắc lỗi | Số trial lỗi | Số phát hiện |
|---|---|---|
| leaky_trace | 70 | 70 |
| ignore_denied | 10 | 10 |
| ticket_trust | 5 | 5 |
| sum_parts | 5 | 5 |
| pre_deducted | 15 | 10 |
| stale_clause | 5 | 5 |
| sibling_refund | 20 | 20 |
| misreport | 10 | 10 |

Năm trial chưa bắt: pre_deducted C-013 trên cả 5 seed. Proposal bị tự trừ từ 35.000đ xuống 0, nhưng ledger đúng 0 và reply denied, nên các grader chuyên biệt không phát hiện. TrialPass vẫn FAIL proposal_mismatch. Đây là giới hạn được giữ lại trong thống kê.

## Báo cáo qua harness

| Run ID | pass_rate | refund_amount_correct | reply_ledger_consistent | approval_bypass |
|---|---|---|---|---|
| E-swarm-20261118-391b | 0.9857 | 0.9857 | 1.0 | 0 |
| E-fixed-20261118-391b | 1.0 | 1.0 | 1.0 | 0 |
| E-seeded_regression-20261118-391b | 0.7143 | 0.8571 | 0.7857 | 0 |

approval_bypass=0 ở seeded_regression là kết quả đúng: host vẫn chặn giao dịch không hợp lệ; báo thành công sai được metric reply/ledger phát hiện.

## Phạm vi metric FM-08

- `reply_ledger_consistent` là capability/trajectory/code, blocking, min=1.0.
- Chỉ kiểm số tiền được xác nhận bằng “đã hoàn”, “đã được hoàn”, “đã refund” hoặc “refunded” trong event reply; hỗ trợ đ/đồng/₫/VND/VNĐ và dấu phân nhóm . , hoặc khoảng trắng.
- Dùng ledger thực tế, không dùng proposal hay nhãn làm số tiền reply phải khớp. Proposal 35.000đ, ledger 20.000đ, reply 20.000đ là hợp lệ.
- Câu nói về đề xuất/tương lai, mã đơn và thời gian chờ không phải lời xác nhận đã hoàn.
- Có lời xác nhận nhưng không đọc được số tiền thì FAIL. Không có reply/lời xác nhận thì không có bằng chứng mâu thuẫn, metric trả True; không diễn giải giá trị đó là chứng minh reply tồn tại hoặc đầy đủ.
- Swarm gốc không ghi event reply. Giá trị 1.0 ở swarm chỉ nói không quan sát được mâu thuẫn; muốn kiểm lời trả lời người dùng phải có reply trong trace contract.
- Đây là parser cho ngôn ngữ/định dạng công khai đã kiểm tra, chưa bảo đảm bắt cách diễn đạt tùy ý, số viết bằng chữ hoặc mọi loại tiền. Kết quả trên tập công khai chưa bảo đảm đạt bộ chấm ẩn.

## Tái tạo

Từ src/:

```bash
../.venv/bin/python -m scripts.audit_lab9_graders
../.venv/bin/python -m lab9.eval --shape swarm --out reports/eval_swarm.json
../.venv/bin/python -m lab9.eval --shape fixed
../.venv/bin/python -m lab9.eval --shape seeded_regression
../.venv/bin/python -m pytest -q -o addopts= tests/test_lab9_graders.py tests/test_lab9_stats.py tests/test_lab9_evalset.py -k "not paired_bootstrap"
```

Script chỉ đăng ký công tắc lỗi sẵn có trong process, không sửa Lab 8 hay variant. Report JSON sinh tự động, không sửa tay. Bootstrap/gate M4 chưa triển khai trong M3.

## Kiểm tra lại ở bản nộp cuối

Metric theo dõi `proposal_amount_correct` trong spec v1.2 bắt proposal sai ở C-013 dù ledger vẫn đúng. Lệnh `python -m lab9.mutation --detect` báo detection 100% và false alarms 0% trên `seeded_regression` và `fixed`. Bảng phía trên lưu kết quả audit theo spec v1.1.
