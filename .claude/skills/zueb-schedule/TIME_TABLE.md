# Staggered-Time Rules

The helper returns raw schedule only. You must infer concrete class time in your response using this reference, not by assuming fixed `3-4` times.

## Batch By Location

| Batch | Location Rule |
|------|---------------|
| First | `1#实验楼`, `2#教学楼`, `3#行政楼`, `4#实验楼`, `工程训练中心` |
| Second | `5#实验楼`, `6#教学楼`, `13#教学楼` |
| Third | `7#教学楼`, `8#教学楼` |
| Fourth | `10#教学楼`, `11#教学楼`, `12#教学楼` |

Matching rules:
- Normalize full-width symbols (`＃` -> `#`) and ignore spaces.
- Treat `X号教学楼` and `X#教学楼` as equivalent.
- Prefer exact building number matching (`10/11/12` must not be mistaken as `1`).

## Period Time Table

| Period | First Batch | Second Batch | Third Batch | Fourth Batch |
|------|-------------|--------------|-------------|--------------|
| 1 | 08:00-08:45 | 08:00-08:45 | 08:00-08:45 | 08:00-08:45 |
| 2 | 08:55-09:40 | 08:55-09:40 | 08:55-09:40 | 08:55-09:40 |
| 3 | 10:00-10:45 | 10:10-10:55 | 10:20-11:05 | 10:30-11:15 |
| 4 | 10:55-11:40 | 11:05-11:50 | 11:15-12:00 | 11:25-12:10 |
| 5 | 14:00-14:45 | 14:00-14:45 | 14:00-14:45 | 14:00-14:45 |
| 6 | 14:55-15:40 | 14:55-15:40 | 14:55-15:40 | 14:55-15:40 |
| 7 | 16:00-16:45 | 16:00-16:45 | 16:00-16:45 | 16:00-16:45 |
| 8 | 16:55-17:40 | 16:55-17:40 | 16:55-17:40 | 16:55-17:40 |
| 9 | 18:20-19:05 | 18:20-19:05 | 18:20-19:05 | 18:20-19:05 |
| 10 | 19:15-20:00 | 19:15-20:00 | 19:15-20:00 | 19:15-20:00 |
| 11 (optional) | 12:20-13:05 | 12:20-13:05 | 12:20-13:05 | 12:20-13:05 |
| 12 (optional) | 13:05-13:50 | 13:05-13:50 | 13:05-13:50 | 13:05-13:50 |

## Time Derivation Procedure

For each course:
1. Determine batch from `skdd`.
2. Parse period numbers from `jcxx` (support ranges like `3-4`, list forms like `1,2`, and mixed text).
3. Map each period to the table above.
4. Output course time range from the first period start to the last period end.
5. If location cannot be mapped to a batch, clearly say the exact time cannot be confirmed and still show `jcxx`.
