This benchmark pack targets the `top-ledger` Trino connection.

Design goals:
- use fixed historical dates so gold answers are stable
- stay partition-pruned on `block_date`
- prefer questions that reflect the existing knowledge vault examples
- keep gold SQL practical enough to execute repeatedly during scoring

Files:
- `cases.yaml`: core benchmark cases
- `cases_complex.yaml`: harder multi-step and multi-join cases
- `cases_hard.yaml`: intentionally difficult cases with dedup, exclusion, and higher-cost reasoning
- `cases_full.yaml`: combined suite
