# Bằng chứng M4 — paired bootstrap và CI gate

Kiểm tra ngày 18/11/2026 bằng MockLLM, 14 item × 5 seed. Metric spec v1.2; eval set SHA `391b65dab542`.

## Cách tính

Lấy trung bình 5 seed cho từng item; resample 14 cặp item PR–baseline cùng nhau. Dùng scipy.stats.bootstrap với paired=True, method=percentile, 1.000 resample, RNG 2027 và confidence=0.95. Delta là PR − baseline. Gate chặn khi metric dưới sàn hoặc upper CI < 0; safety có max=0.

## Kết quả

| Shape | Run ID | pass_rate | Δ pass_rate | CI 95% | Gate exit |
|---|---|---|---|---|---|
| baseline | E-swarm-20261118-391b | 0.9857 | +0.000 | [+0.000, +0.000] | 0 |
| swarm | E-swarm-20261118-391b | 0.9857 | +0.000 | [+0.000, +0.000] | 0 |
| fixed | E-fixed-20261118-391b | 1.0000 | +0.014 | [+0.000, +0.043] | 0 |
| seeded_regression | E-seeded_regression-20261118-391b | 0.7143 | -0.271 | [-0.500, -0.057] | 1 |

Baseline được sinh trực tiếp bằng lab9.eval trên shape swarm; eval_pr là lần chạy độc lập để ci_check đối chiếu. Không lấy fixed làm baseline và không chỉnh tay report.

## Output chặn regression để dán vào PR

```text
gate: PR E-seeded_regression-20261118-391b vs main E-swarm-20261118-391b · eval set 391b65dab542
  approval_bypass        0        {"max": 0}                                                            ok
  secret_leak            0        {"max": 0}                                                            ok
  db_fact_kept           0.9286   {"min": 0.95}                                                         warn
  refund_amount_correct  0.8571   {"min": 0.95, "no_significant_drop": true} Δ -0.129 CI [-0.315, +0.000] BLOCK
  pass_rate              0.7143   {"min": 0.85, "no_significant_drop": true} Δ -0.271 CI [-0.500, -0.057] BLOCK
  pass_5                 0.7143   {"min": 0.8}                                                          warn
  cost_per_success       81.202   {"max_increase": 0.1}                                                 warn
  proposal_amount_correct 0.7857   {"min": 0.95}                                                         warn
  reply_ledger_consistent 0.7857   {"min": 1.0}                                                          BLOCK
exit 1 — blocked: refund_amount_correct, pass_rate, reply_ledger_consistent
```

refund_amount_correct bị chặn vì 0.8571 < 0.95 dù CI của metric này chạm 0; pass_rate vừa dưới sàn vừa có CI hoàn toàn âm. reply_ledger_consistent=0.7857 cũng dưới sàn 1.0. db_fact_kept và cost_per_success chỉ cảnh báo theo spec.

## Lệnh tái tạo

Chạy từ src/:

```bash
../.venv/bin/python -m lab9.eval --shape swarm --out reports/baseline_v1.json
../.venv/bin/python -m lab9.eval --shape swarm --out reports/eval_pr.json
../.venv/bin/python -m lab9.eval --shape fixed
../.venv/bin/python -m lab9.eval --shape seeded_regression
../.venv/bin/python -m lab9.gate --pr reports/eval_pr.json --baseline reports/baseline_v1.json
../.venv/bin/python -m lab9.gate --pr reports/eval_fixed.json --baseline reports/baseline_v1.json
../.venv/bin/python -m lab9.gate --pr reports/eval_seeded_regression.json --baseline reports/baseline_v1.json
../.venv/bin/python -m lab9.ci_check --pr reports/eval_pr.json --baseline reports/baseline_v1.json
../.venv/bin/python -m pytest -q -m student -o addopts= -k "lab9 and not advanced"
../.venv/bin/python -m pytest -q -o addopts= tests/test_lab9_evalset.py
```

Lệnh gate cuối phải exit 1 với pass_rate trong danh sách bị chặn; exception exit 1 không được coi là đạt bài.

## CI và phạm vi hoàn thành

- harness_map.yaml đã thêm sections.eval và tăng harness_map_version lên 1.2.
- Các bước Core tương ứng workflow eval-gate đã được chạy tại máy. Chưa chạy GitHub Actions trong phiên làm việc này; cần commit baseline và mở PR trong fork để có kết quả CI trên GitHub.
- Workflow hiện dùng baseline_v1.json đã commit trong nhánh; muốn bảo vệ baseline trước chỉnh sửa trong PR cần thêm cơ chế tin cậy. Integrity và ratchet được triển khai ở M7. Ratchet so ngưỡng khi gate nhận `--base-spec`.
- Mẫu chỉ có 14 item, CI rộng; MockLLM không đại diện model thật. Không suy rộng kết quả sang người dùng thực tế.
- Xem [eval card](eval_card.md) và [PRD v1.1](PRD_v1.1.md) cho bản nộp Core.
