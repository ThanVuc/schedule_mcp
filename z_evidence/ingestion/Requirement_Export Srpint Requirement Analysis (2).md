# Source File

Requirement_Export Srpint Requirement Analysis (2).docx

This content is extracted from files. Structure may be imperfect. Interpret intelligently.

# 1. Invariant Rules

- Export chỉ chứa 1 sprint.

- Mỗi task xuất hiện 1 lần duy nhất.

- completed_at = NULL → NOT_DONE.

- completed_at != NULL → DONE.

- story_point:

- ≥ 0 → hợp lệ

- NULL → UNESTIMATED (không tính metric)

- Task chỉ đóng góp 1 lần tại completed_at.

- Không phân bổ story point theo nhiều ngày.

- Cột ngày = [sprint_start → sprint_end].

- Chỉ task có story_point != NULL được tính vào metric.

- SPILLOVER: completed_at > sprint_end.

# 2. Decision Table

## 2.1 Base Classification

## Table 1

| SP | completed_at | due_date | Result |
| --- | --- | --- | --- |
| NULL | NULL | any | NOT_DONE_UNESTIMATED |
| NULL | ✔ | any | DONE_UNESTIMATED |
| ✔ | NULL | any | NOT_DONE |
| ✔ | ✔ | NULL | DONE |
| ✔ | ✔ | ✔ | Check deadline |

## 2.2 Deadline

## Table 2

| Condition | Result |
| --- | --- |
| completed_at < due_date | EARLY |
| completed_at = due_date | ON_TIME |
| completed_at  > due_date | LATE |

## 2.3 Sprint Scope

## Table 3

| Condition | Result |
| --- | --- |
| completed_at ≤ sprint_end | IN_SPRINT |
| completed_at > sprint_end | SPILLOVER |

## 2.4 Final Status

## Table 4

| Condition | Status |
| --- | --- |
| NOT_DONE | NOT_DONE |
| DONE + no SP | DONE_UNESTIMATED |
| DONE + no due | DONE |
| DONE + EARLY | DONE_EARLY |
| DONE + ON_TIME | DONE_ON_TIME |
| DONE + LATE | DONE_LATE |
| DONE + SPILLOVER | DONE_SPILLOVER |

# 3. Behavior Rules

## 3.1 Table Structure

Mỗi row gồm:

- Task name

- Assignee

- Story point

- Completed_at

- Daily columns

## 3.2 Fill Daily Cells (Task Level)

Điền SP vào 1 ô duy nhất nếu:

- completed_at != NULL

- story_point != NULL

- completed_at ∈ sprint

→ Fill tại cột ngày completed_at

Ngược lại → để trống toàn bộ daily cells

## 3.3 Coloring (chỉ ô completion)

## Table 5

| Status | Color |
| --- | --- |
| DONE_EARLY | Blue/Green |
| DONE_ON_TIME | Green |
| DONE_LATE | Red |
| DONE_SPILLOVER | Dark Red |
| DONE_UNESTIMATED | Yellow |
| NOT_DONE | None |

## 3.4 Total Section (Burndown)

## 3.4.1 Definitions

- Total_SP = SUM(SP WHERE SP != NULL)

- Total_Days = số ngày trong sprint

- Completed_SP[day] = tổng SP hoàn thành tại ngày đó

## 3.4.2 Expected (Ideal Burndown)

Giảm tuyến tính:

Expected_day_n = Total_SP - (Total_SP / Total_Days) * n

- Day 0 = Total_SP

- Day cuối = 0

## 3.4.3 Actual (Real Burndown)

Remaining thực tế:

Remaining = Total_SP

For each day:

Remaining -= Completed_SP[day]

Actual_day = Remaining

## 3.4.4 Rules

- Expected và Actual phải có cùng số cột ngày

- Day 0 luôn = Total_SP

- Không có giá trị NULL

- Actual chỉ giảm khi có task DONE

## 3.5 Metrics

- Total Estimated
= SUM(SP WHERE SP != NULL)

- Total Completed
= SUM(SP WHERE completed_at != NULL)

- Completion Rate
= completed / estimated

- Spillover
= SUM(SP WHERE completed_at > sprint_end)

- Unestimated Count
= COUNT(SP = NULL)

## 3.6 Sorting

ORDER BY

completed_at IS NULL,

completed_at ASC

## 3.7 Edge Cases

### Task hoàn thành ngoài sprint

- Không fill daily columns

- Vẫn tính:

- Total Completed

- Spillover

### Task không có story point

- Không tính metric

- Vẫn hiển thị

- Có thể highlight riêng

# 4. Principles

1 task = 1 completion = 1 contribution

Progress chỉ được ghi nhận khi task DONE

# 5. Summary

- Không dùng worklog

- Không chia nhỏ story point

- Không fake progress

- Dựa hoàn toàn vào completed_at

- Excel phản ánh:

- Completion thực tế

- Burndown (Expected vs Actual)
