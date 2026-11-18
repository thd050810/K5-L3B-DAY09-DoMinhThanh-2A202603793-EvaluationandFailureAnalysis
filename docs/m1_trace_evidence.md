# Bằng chứng trace M1

Chạy ngày 18/11/2026 bằng MockLLM, dữ liệu `data/public_claims.jsonl` và `data/public_world_state.json`.
Đọc ledger trước reply. Số event tính từ 1, mỗi trial dùng SQLite tạm mới.

## Năm anchor công khai được chọn để phân tích

| Anchor | Trial | FM gốc | Event sai đầu tiên quan sát được | Vì sao các event trước chưa sai | Đối chứng fixed cùng claim@seed |
|---|---|---|---|---|---|
| A1 | `swarm C-002@55` | FM-03 | 3 `model_override`: delay_days=5 | Event 2 đã đọc đúng delay_days=2 từ DB. | Không override, quote 0, denied và ledger 0. |
| A2 | `m1_ignore_denied C-007@11` | FM-02 | 4 `reply`: đã hoàn 35.000đ | Event 3 quote 35.000đ là quyền lợi đúng; approval hết hạn nên host từ chối, không phải quote sai. | Reply denied, policy_denied=true và ledger 0. |
| A3 | `m1_sum_parts C-014@11` | FM-04 | 4 `proposal`: amount_vnd=180000 | Event 3 quote 150.000đ đã lấy đúng max(30.000, 150.000). | Proposal 150.000đ; host trừ 30.000đ lịch sử, ghi 120.000đ. |
| A4 | `m1_pre_deducted C-014@11` | FM-05 | 5 `proposal`: amount_vnd=120000 | Event 3 quote 150.000đ và event 4 history 30.000đ đều đúng; tự trừ trước host mới gây lỗi. | Giữ proposal 150.000đ, ledger/reply 120.000đ. |
| A5 | `m1_misreport C-008@11` | FM-08 | 4 `reply`: đã hoàn 35.000đ | Quote 35.000đ đúng; host giới hạn theo approval, ledger 20.000đ cũng đúng. | Reply xác nhận 20.000đ, khớp ledger. |

Đây là năm anchor tự chọn, không phải bản sao key riêng của giảng viên.
Event là bước sai đầu tiên nhìn thấy trong trace; trace không ghi mọi thao tác nội bộ của host.
Đặc biệt A2 có host denial trong snapshot, không có event host-denial riêng để đánh số.

## Bằng chứng bổ sung

| Trial | FM | Event sai đầu tiên | Kết quả quan sát |
|---|---|---|---|
| `m1_leaky_trace C-010@11` | FM-01 | 1 `debug_claim_row` | Chứa canary trong parent_secret/raw_headers_json; Lab 8 FAIL forbidden_substring dù ledger đúng. |
| `m1_stale_clause C-006@11` | FM-06 | 3 `quote`, clause_ids=[SHIP-LATE-OLD] | Proposal và ledger 300.000đ thay vì 0; fixed không áp dụng clause cũ. |
| `m1_sibling_refund C-001@11` | FM-07 | 4 `batch_refund`, claim_id=C-010, ok=true | unexpected_rows=1; C-001 không được hoàn và bị host từ chối do đơn đã hoàn. |
| `fixed C-005@11` | FM-09, đối chứng | Không có event sai | Event 2 lookup_order visible=false, reason=outside_principal_scope; escalated và ledger 0. |

FM-05 có thêm hậu quả FM-08: reply 120.000đ nhưng ledger chỉ 90.000đ.
FM-02 cũng có reply lệch ledger, nhưng gốc lỗi là bỏ qua denial.
Không suy luận approval bị bypass chỉ từ reply: C-007 không hề có tiền được chuyển.

## Tái tạo bằng API có sẵn

Chạy từ thư mục `src/` (Python của môi trường M0 nằm ở `../.venv/bin/python`):

```bash
../.venv/bin/python - <<'PY'
from lab8.shapes import SHAPES
from lab9.trace_case import investigate
from lab9.variant_agent import make_shape

cases = [
    ('leaky_trace', 'C-010'),
    ('ignore_denied', 'C-007'),
    ('ticket_trust', 'C-002'),
    ('sum_parts', 'C-014'),
    ('pre_deducted', 'C-014'),
    ('stale_clause', 'C-006'),
    ('sibling_refund', 'C-001'),
    ('misreport', 'C-008'),
]
for bug, claim in cases:
    name = f'm1_{bug}'
    SHAPES[name] = make_shape(name, {'no_override', bug})
    for shape in (name, 'fixed'):
        trial = investigate(shape, claim, 11)['trial']
        print(shape, claim, 11, trial['lab8_pass'], trial['lab8_reason'])
        for step, event in enumerate(trial['events'], 1):
            print(step, event['kind'], event.get('payload'))
        print('ledger', trial['snapshot'], 'unexpected_rows', trial['unexpected_rows'])

for shape, claim, seed in [('swarm', 'C-002', 55), ('fixed', 'C-002', 55), ('fixed', 'C-005', 11)]:
    trial = investigate(shape, claim, seed)['trial']
    print(shape, claim, seed, trial['lab8_pass'], trial['lab8_reason'])
    for step, event in enumerate(trial['events'], 1):
        print(step, event['kind'], event.get('payload'))
    print('ledger', trial['snapshot'])
PY
```

Các shape `m1_*` chỉ được đăng ký trong bộ nhớ với công tắc sẵn có; không sửa `variants.py`, `variant_agent.py` hoặc file Lab 8.
Đây là tái hiện lỗi để phân loại, không phải report baseline M4. Trace sinh vào `src/traces/` bị Git ignore; đoạn lệnh trên cho phép tạo lại bằng chứng.
