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

### Context & Objective
Provide an end-to-end integration path:
`CAN frames → StreamingFeatures → Stage 1 RuleEngine → Stage 2 ML → Hybrid Fusion → Severity Scorer → SQLite Alerts`.

### Stage 2 ML Deterministic Stub
- **Rationale**: The production ML model (LightGBM multi-class classifier trained by Person 3) is scheduled for Day 16 integration. In Day 15 (demo/pipeline sprint), a deterministic stub `Stage2Model` in `src/stark/ml/predict.py` provides realistic outputs without introducing large binary model weight artifacts.
- **Behavior**:
  - `can_id == 0` or `dt_same_id < 0.0005s` maps to `"dos"` with 0.93 probability.
  - All other frames default to `"normal"` with 0.97 probability.
  - Optional seed support is provided for random smoke testing.
  - Interface `predict(vector) -> (str, dict[str, float])` matches the production model contract identically, ensuring a zero-refactor swap on Day 16.

### Hybrid Fusion Arbitration Matrix
- **Deterministic vs Statistical Arbitration**:
  - Deterministic Stage 1 violations (weight 3 hard violations: R1 unseen ID, R2 physical impossible dt, R4 DLC mismatch) take absolute precedence; if Stage 2 corroborates, Stage 1 claims the detection. If Stage 2 disagrees, label defaults to `"dos"` (or Stage 1 rule classification) with stage marked as `"stage1_override"`.
  - Suspect evaluations (weight 2: R3 bus flooding, R5 repetition, R6 payload anomaly) are arbitrated based on Stage 2 ML confidence:
    - If Stage 2 attack confidence $p \ge 0.85$, fused decision is `(Stage 2 attack, stage="stage2", p)`.
    - If Stage 2 attack confidence $0.50 \le p < 0.85$, fused decision is `(Stage 2 attack, stage="hybrid", p)`.
    - If Stage 2 predicts `"normal"`:
      - If suspect rule persists across frames ($\ge 3$ consecutive suspect frames or $\ge 3$ distinct CAN IDs in a 50ms window), fused decision triggers `"suspect_persistent"` at severity 45.
      - If isolated, the frame is filtered as `"normal"`.
  - Clean Stage 1 frames: ML is sampled or bypasses inference. If ML flags an attack with high confidence ($p \ge 0.90$), it is accepted as `"stage2"`; otherwise it passes as benign `"normal"`.
- **Severity Scoring**:
  - Severity is mapped onto a 0–100 scale: `low` (<30), `medium` (30–59), `high` (60–84), `critical` (85–100).
  - High confidence attacks combined with Stage 1 hard rule violations reach Critical severity (90–100).
  - Stage 2 alone without Stage 1 rule violation is capped at Medium (55) unless corroborated by persistence.

### Causal Streaming Features
- **Strict Causality**: Real-time vehicle ECUs cannot peek into future CAN frames. `StreamingFeatures` maintains internal rolling state per run (`_last_seen_time`, `_last_payload`, `_rolling_window`, `_consecutive_same_payload`).
- **Feature Computation**:
  - `dt_same_id`: Computed strictly against the previous timestamp recorded for that specific `can_id`. None on first observation.
  - `msg_rate_50ms`: Count of frames within $(t - 0.050, t]$ using an internal causal deque.
  - `payload_hamming_distance`: Bitwise XOR Hamming distance between current payload and immediately preceding payload for the same `can_id`.
  - State is strictly per-run and is reset via `StreamingFeatures.reset()` when initiating new runs.
