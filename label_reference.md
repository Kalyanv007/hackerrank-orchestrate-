# Label Reference — `dataset/sample_claims.csv`

Source: 20 labeled rows in `dataset/sample_claims.csv`. Frequencies below are **observed counts in this 20-row sample**, not the full allowed vocabulary — see the "not observed" lines under each section for values that are valid per `problem_statement.md` but never appear here. Treat unobserved-but-allowed values as still in play for `claims.csv` (44 rows); do not assume the sample is exhaustive.

---

## `issue_type` (n=20)

| Value | Count |
|---|---|
| `broken_part` | 3 |
| `crack` | 3 |
| `dent` | 3 |
| `unknown` | 3 |
| `none` | 2 |
| `scratch` | 2 |
| `crushed_packaging` | 1 |
| `stain` | 1 |
| `torn_packaging` | 1 |
| `water_damage` | 1 |

**Not observed in sample** (allowed per spec): `glass_shatter`, `missing_part`

---

## `severity` (n=20)

| Value | Count |
|---|---|
| `medium` | 11 |
| `low` | 4 |
| `none` | 2 |
| `unknown` | 2 |
| `high` | 1 |

**Not observed in sample:** none — all 5 allowed values appear at least once.

---

## `claim_status` (n=20)

| Value | Count |
|---|---|
| `supported` | 13 |
| `contradicted` | 5 |
| `not_enough_information` | 2 |

**Not observed in sample:** none — all 3 allowed values appear at least once.

---

## `object_part` (n=20, all objects combined)

| Value | Count |
|---|---|
| `front_bumper` | 2 |
| `rear_bumper` | 2 |
| `screen` | 2 |
| `seal` | 2 |
| `contents` | 1 |
| `corner` | 1 |
| `door` | 1 |
| `headlight` | 1 |
| `hinge` | 1 |
| `keyboard` | 1 |
| `package_corner` | 1 |
| `package_side` | 1 |
| `side_mirror` | 1 |
| `trackpad` | 1 |
| `unknown` | 1 |
| `windshield` | 1 |

### `object_part` broken down by `claim_object`

**car** (n=8 rows)

| Value | Count |
|---|---|
| `front_bumper` | 2 |
| `rear_bumper` | 2 |
| `door` | 1 |
| `headlight` | 1 |
| `side_mirror` | 1 |
| `windshield` | 1 |

Not observed for car: `hood`, `fender`, `quarter_panel`, `body`, `unknown`

**laptop** (n=6 rows)

| Value | Count |
|---|---|
| `screen` | 2 |
| `corner` | 1 |
| `hinge` | 1 |
| `keyboard` | 1 |
| `trackpad` | 1 |

Not observed for laptop: `lid`, `port`, `base`, `body`, `unknown`

**package** (n=6 rows)

| Value | Count |
|---|---|
| `seal` | 2 |
| `contents` | 1 |
| `package_corner` | 1 |
| `package_side` | 1 |
| `unknown` | 1 |

Not observed for package: `box`, `label`, `item`

---

## Notes

- `claim_object` distribution underlying the above: `car`=8, `laptop`=6, `package`=6 (n=20).
- `risk_flags` and `evidence_standard_met`/`valid_image` are not included here (not requested), but were already profiled in the earlier analysis — let me know if you want them added to this file in the same format.
- These are sample-set frequencies only, useful as a rough prior for severity/claim_status base rates, but `issue_type` and `object_part` should still be predicted per-row from the actual image content — they should not be inferred from this distribution.
