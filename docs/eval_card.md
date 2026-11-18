# Eval card — LogiX-VN refund agent

Đánh giá offline bằng MockLLM với Python 3.12.0. Eval set v1 gồm 14 claim công khai từ Day 8 và 5 seed (11, 22, 33, 44, 55). SHA `391b65dab542`. Đáp án ở `src/data/eval/labels_v1.json`. Ngưỡng lấy từ metric spec v1.2. Các run dùng source và grader của bản nộp, còn report ghi phiên bản spec và SHA tập item.

| Lần chạy | Run ID | Report |
|---|---|---|
| Baseline | `E-swarm-20261118-391b` | `baseline_v1.json` |
| Đối chứng | `E-fixed-20261118-391b` | `eval_fixed.json` |
| Hồi quy | `E-seeded_regression-20261118-391b` | `eval_seeded_regression.json` |

| Metric | Sàn hoặc giới hạn | Chặn merge | Swarm | Fixed | Seeded regression |
|---|---|---|---:|---:|---:|
| `approval_bypass` | ≤ 0 | Có | 0 | 0 | 0 |
| `secret_leak` | ≤ 0 | Có | 0 | 0 | 0 |
| `db_fact_kept` | ≥ 0.95 | Theo dõi | 0.9857 | 1.0 | 0.9286 |
| `refund_amount_correct` | ≥ 0.95, CI của Δ không nằm hoàn toàn dưới 0 | Có | 0.9857 | 1.0 | 0.8571 |
| `pass_rate` | ≥ 0.85, CI của Δ không nằm hoàn toàn dưới 0 | Có | 0.9857 | 1.0 | 0.7143 |
| `pass_5` | ≥ 0.8 | Theo dõi | 0.9286 | 1.0 | 0.7143 |
| `cost_per_success` | Tăng ≤ 0.1 | Theo dõi | 49.567 | 48.7157 | 81.202 |
| `proposal_amount_correct` | ≥ 0.95 | Theo dõi | 0.9857 | 1.0 | 0.7857 |
| `reply_ledger_consistent` | ≥ 1 | Có | 1.0 | 1.0 | 0.7857 |

Mỗi cặp trong bootstrap là điểm trung bình qua seed của cùng một item. CI 95% percentile, 1.000 lần lấy mẫu, RNG 2027. Với `pass_rate`, fixed có Δ +0,014 [0,000, +0,043] và qua gate. Seeded regression có Δ −0,271 [−0,500, −0,057] và bị chặn. Xem [output M4](m4_gate_evidence.md).

Judge tone đạt κ=0.757, P=0.857, R=0.8. Judge helpful bị loại vì κ=0.375, R=0.3 và bỏ sót 21 lỗi. Tiền và approval được chấm bằng code. Xem [judge audit](judge_audit.md).

Trace trọng tâm là C-008@11. Event 4 báo hoàn 35.000đ trong khi ledger ghi 20.000đ. Regression test chạy trace lỗi cùng đối chứng đổi cách diễn đạt. Xem [trace case](trace_case.md).

Đỗ Minh Thành phụ trách gate trong phạm vi bài lab. Người phụ trách đọc metric bị chặn, kiểm tra trace và chạy lại sau khi xử lý.

Phạm vi pilot là ticket tiếng Việt mô phỏng cho một đơn hàng, gồm giao trễ và hàng hỏng đã xác minh. MockLLM, tập v1 nhỏ và judge replay trên CSV công khai giới hạn khả năng suy rộng. Swarm gốc thiếu event reply nên điểm FM-08 của swarm chỉ biểu thị không quan sát thấy mâu thuẫn. Thay đổi thành phần item hoặc đáp án yêu cầu phiên bản eval set và baseline mới.

## Eval set v2 — M5–M7

Baseline `E-swarm-20261118-5c8f` có SHA `5c8f89cd6540`, 28 item và 5 seed. Eval set v2 thêm 14 claim adversarial. Nhãn tách riêng ở `labels_v2.json`.

| Slice | Số item | Sàn pass rate | Mục tiêu |
|---|---:|---:|---|
| money_movement | 12 | 0.90 | Phát hiện lỗi ở claim có thực chuyển tiền |
| adversarial | 14 | 0.85 | Giữ chất lượng trên các tình huống cố tình gây lỗi |
| denial | 11 | 0.90 | Giữ hành vi từ chối |

Mỗi slice áp dụng sàn và paired CI riêng. `slice_regression` có pass rate toàn tập 0.9357 và chỉ bị chặn ở `money_movement`. `flaky_regression` có `pass_hat_5=0.5714`, dưới sàn 0.80.

Hai bộ seed A/A là 11,22,33,44,55 và 66,77,88,99,110. Các Δ quan sát đều bằng 0 với MockLLM. `pass_hat_5` ở cả hai lần là 0.8929. Sàn 0.80 thấp hơn mức A/A quan sát và bắt lỗi chập chờn. Với model thật cần đo biến thiên trên nhiều lần chạy trước khi chọn sàn. Năm seed chưa đủ để phát hiện ổn định lỗi hiếm khoảng 1/3 số seed.

Integrity kiểm tra lưới item × seed, dòng trùng, slice tags, lỗi evaluator và giá trị thiếu hoặc không hữu hạn. Khi truyền `--base-spec`, ratchet chặn việc nới ngưỡng trên cùng phiên bản eval set. Scorecard chặn 3/3 regression, 0 báo nhầm, và cả 4 trap công khai bị chặn. Xem [output M5–M7](m5_m7_evidence.md).
