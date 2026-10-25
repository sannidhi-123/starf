# Architectural & Tuning Decisions Log

## 2026-10-24: Stage 1 Rule Threshold Tuning (Day 12)

### Context & Goal
Calibrate Stage 1 deterministic rule thresholds to achieve a False Positive Rate (FPR) < 2.0% strictly on the validation partition (`fixture.csv`, time-ordered 70/15/15 split). Evaluation was conducted strictly on the validation split; neither the test split nor OTIDS benchmarks were touched.

### Threshold Parameter Calibration
A grid search was executed over the tunable global thresholds in `config/rules.yaml`:
- `r2_factor` grid: `[0.3, 0.4, 0.5, 0.6, 0.7]`
- `r7_factor` grid: `[3.0, 4.0, 5.0, 6.0, 8.0]`
- `r3_global_rate`: verified at `15.0` fps (derived from the 99.9th percentile of normal traffic 50ms window rates).

### Threshold Comparison

| Parameter | Old Value | New Tuned Value | Description |
| :--- | :--- | :--- | :--- |
| `r2_factor` | `0.5` | `0.4` | Lower-bound multiplier for 1st percentile inter-arrival time `p01_dt` (R2: impossible inter-arrival floor) |
| `r7_factor` | `5.0` | `4.0` | Upper-bound multiplier for 99th percentile inter-arrival time `p99_dt` (R7: message silence watchdog) |
| `r3_global_rate` | `15.0` | `15.0` | 50ms window rate limit in fps (R3: bus flooding rule) |

### Validation Metrics Before & After

| Metric | Before Tuning | After Tuning | Status |
| :--- | :--- | :--- | :--- |
| **Validation FPR** | `1.31%` (8 FP / 612 normal) | `1.31%` (8 FP / 612 normal) | **Passed** (< 2.0% requirement) |
| **Attack Recall** | N/A (0 attacks in validation split) | N/A (0 attacks in validation split) | Consistent |
| **Filtering Rate** | `98.69%` | `98.69%` | Maintained high filtering throughput |
| **Median Latency** | `~0.015 ms / frame` | `~0.015 ms / frame` | Ultra-low real-time deterministic budget |
| **R2 False Triggers** | `0` | `0` | 0 false flags at tighter factor 0.4 |
| **R7 False Triggers** | `0` | `0` | 0 false flags at tighter factor 4.0 |

### Reasoning
- `r2_factor = 0.4` narrows the inter-arrival tolerance safely above the physical transmission minimum (`physical_min_dt = 0.00020 s`) while guarding against injection bursts with zero false triggers on benign traffic.
- `r7_factor = 4.0` provides a tightened silence watchdog threshold compared to the loose default (5.0), while comfortably accommodating natural bus jitter without false alarms.
- The resulting FPR of 1.31% meets the Day 12 success criterion (< 2.0% validation FPR) with 98.69% of frames cleanly filtered.

## 2026-10-25: Hybrid Fusion & Stage 2 Demo Stub (Day 15)

Day 15 (demo sprint): Stage2 is a deterministic stub; real LightGBM from Person 3 replaces it.
