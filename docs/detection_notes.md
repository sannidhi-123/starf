# STARK Detection Pipeline — Engineering Reference Notes (Day 1)

> **Author**: Person 2 (Detection Pipeline Module Lead)  
> **Scope**: Stage 1 Rule Engine, Hybrid Fusion, Severity Scoring, Alerting, Pipeline Orchestration, Detection APIs  
> **Status**: Working reference document for the 28-day roadmap.

---

## 1. Stage 1 Deterministic Rule Engine (The 7 Rules)

Stage 1 is the high-throughput, low-latency (< 0.1ms/frame) deterministic filter running directly on incoming CAN frames. It prevents normal cyclic traffic from overloading the Stage 2 neural network and catches immediate protocol violations with mathematical certainty.

| Rule ID | Name | Trigger Condition & Description | Target Attack / Threat | Severity Weight ($w_{r}$) |
|---|---|---|---|---|
| **R1** | **Unknown Arbitration ID** | $\text{ID} \notin \mathcal{W}_{\text{allowed}}$<br/>Observed arbitration ID is absent from the vehicle profile's authorized CAN ID whitelist. | Rogue ECU insertion, aftermarket OBD-II dongle exploit, diagnostic gateway compromise. | **1.0 (CRITICAL)** |
| **R2** | **Impossible Inter-Arrival** | $\Delta t = t_i - t_{i-1} < \Delta t_{\text{min}}$ (per ID or physical bus)<br/>Time elapsed since previous frame of this ID is strictly below physical transmission/propagation limits (e.g. $< 0.2\text{ms}$). | Direct frame injection, electrical bus collisions, transceiver glitches. | **0.85 (HIGH)** |
| **R3** | **Flooding / Frequency Exceeded** | $f_{\text{window}}(\text{ID}) > f_{\text{max}}$ or $\text{Count}_{\text{window}} > N_{\text{threshold}}$<br/>Message transmission frequency within sliding window exceeds baseline burst thresholds (e.g. > 3x normal cyclic rate). | Denial of Service (DoS) attack, arbitration saturation (e.g. `0x000` priority abuse). | **0.90 (CRITICAL)** |
| **R4** | **DLC Compliance Violation** | $\text{DLC} \notin [0, 8]$ or $\text{DLC} \neq \text{DLC}_{\text{expected}}(\text{ID})$<br/>Data Length Code violates standard CAN specification bounds or deviates from OEM message definition map. | Fuzzing attacks, frame length spoofing, malformed packet injection. | **0.70 (MEDIUM/HIGH)** |
| **R5** | **Repetition Burst** | $\text{Payload}_i == \text{Payload}_{i-1} == \dots == \text{Payload}_{i-k}$ with $\Delta t \le \Delta t_{\text{nominal}}$ and count $k > K_{\text{max}}$<br/>Static payload repeated identical byte-for-byte across consecutive transmissions at high frequency. | Replay attack, frozen sensor failure, masquerade injection. | **0.55 (MEDIUM)** |
| **R6** | **Payload Jump (Rate of Change)** | $\|\text{Signal}_i - \text{Signal}_{i-1}\| > \Delta \text{Val}_{\text{max}}$ or bit-flip Hamming distance $H(d_i, d_{i-1}) > H_{\text{max}}$<br/>Discontinuous physical sensor jump (e.g. wheel speed jumping from 30 km/h to 180 km/h in 10ms). | Sensor spoofing, false telemetry injection, drive-by-wire tampering. | **0.80 (HIGH)** |
| **R7** | **Message Silence / Timeout** | $\Delta t_{\text{since\_last}} > \tau_{\text{timeout}} = M \times T_{\text{cycle}}$ (e.g. $M = 3$ to $5$)<br/>Expected periodic CAN message fails to appear within maximum acceptable cycle timeout window. | Bus-off attack, ECU power disconnection, denial of safety service. | **0.45 (MEDIUM/LOW)** |

---

## 2. Hybrid Fusion Priority Table (7-Row Logic)

Hybrid fusion arbitrates between Stage 1 deterministic rule outputs and Stage 2 neural network classification. It resolves conflicts, filters false alarms, and produces confirmed, attributed incident classifications.

| Row | Stage 1 (Deterministic) | Stage 2 (Neural Network) | Final Decision | Attribution Category | Rationale & Handling |
|:---:|---|---|---|---|---|
| **1** | **Critical Violation** (R1/R3) | **High Anomaly** ($S_{\text{ML}} \ge \theta_{\text{high}}$) | **CONFIRMED ATTACK (CRITICAL)** | DoS / Unauthorized Injection | **Dual Confirmation**: Both physical protocol and statistical temporal models agree with high confidence. Immediate critical alarm. |
| **2** | **Hard Violation** (R1/R4/R2) | **Normal / Low Score** ($S_{\text{ML}} < \theta_{\text{low}}$) | **CONFIRMED ATTACK (HIGH/CRITICAL)** | Protocol Violation / Fuzzing / Rogue Node | **Rule Override**: Hard physical invariants (e.g. non-existent CAN ID or invalid DLC) cannot be vetoed by ML. Prevents ML false negatives from masking direct protocol exploits. |
| **3** | **Soft Suspicious** (R5/R6 timing/payload jitter) | **High Anomaly** ($S_{\text{ML}} \ge \theta_{\text{high}}$) | **CONFIRMED ATTACK (HIGH)** | Spoofing / Advanced Replay | **ML Confirmation**: The subtle temporal or multi-frame anomaly suspected by Stage 1 is verified by the deep sequential model (LSTM/GRU/1D-CNN). |
| **4** | **Soft Suspicious** (R2/R5 boundary jitter) | **Normal** ($S_{\text{ML}} < \theta_{\text{low}}$) | **BENIGN / NORMAL (SUPPRESSED)** | Benign Jitter / False Alarm | **False Alarm Filter**: Transient electrical bus jitter or benign driving transients flagged by heuristic thresholds are filtered out by Stage 2, preventing driver alert fatigue. |
| **5** | **Clean / Compliant** (No rule triggered) | **High Anomaly** ($S_{\text{ML}} \ge \theta_{\text{high}}$) | **CONFIRMED ATTACK (HIGH)** | Stealth Spoofing / Semantic Attack | **Stealth Detection**: Individual frames obey standard CAN syntax (valid ID, DLC, cyclic time), but multi-frame correlation contains adversarial dynamics detected only by deep temporal embeddings. |
| **6** | **Clean / Compliant** | **Normal** ($S_{\text{ML}} < \theta_{\text{low}}$) | **NORMAL (PASS-THROUGH)** | Normal Baseline Traffic | **Fast Path**: High-volume normal traffic passes through with minimal overhead, logged to background telemetry metrics. |
| **7** | **Timeout / Silence** (R7) | **Ambiguous / Inactive** | **DIAGNOSTIC WARNING (MEDIUM)** | Hardware Fault / Malfunction / Bus-Off | **Fault Isolation**: Silence without high injection anomaly scores typically indicates ECU harness failure, electrical disconnection, or physical bus-off state rather than cyber compromise. |

---

## 3. Severity Scoring Model

The severity scoring engine evaluates confirmed anomalies to assign actionable response tiers for vehicle telemetry and alerting:

### Mathematical Formula

$$\text{SeverityScore} = \min\left(1.0, \; S_{\text{base}} + w_{\text{rule}} \cdot R_{\text{weight}} + w_{\text{conf}} \cdot C_{\text{ML}} + w_{\text{persist}} \cdot P_{\text{burst}}\right)$$

Where:
- $S_{\text{base}} \in [0.10, 0.30]$: Baseline safety weight tied to the CAN ID criticality (e.g. Steering/Brakes = $0.30$, Powertrain = $0.20$, Infotainment/Body = $0.10$).
- $w_{\text{rule}} = 0.35$: Weight allocated to the Stage 1 rule violation severity $R_{\text{weight}} \in [0.0, 1.0]$.
- $w_{\text{conf}} = 0.35$: Weight allocated to the Stage 2 ML anomaly confidence score $C_{\text{ML}} \in [0.0, 1.0]$.
- $w_{\text{persist}} = 0.20$: Weight allocated to the temporal persistence factor $P_{\text{burst}} \in [0.0, 1.0]$:
  $$P_{\text{burst}} = \min\left(1.0, \; \frac{N_{\text{anomalous\_frames\_in\_window}}}{N_{\text{window\_capacity}}}\right)$$

### Classification Threshold Tiers

| Calculated Score Range | Severity Level | System Response & Vehicle Action |
|---|---|---|
| **$[0.00, 0.30)$** | **LOW** | Informational event log. Update sliding baseline statistics; no driver notification. |
| **$[0.30, 0.60)$** | **MEDIUM** | Warning flag. Store telemetry snapshot; aggregate in monitoring dashboard for diagnostic review. |
| **$[0.60, 0.85)$** | **HIGH** | Security alert raised. Display warning on diagnostic cluster; throttle non-critical bus traffic. |
| **$[0.85, 1.00]$** | **CRITICAL** | Immediate intrusion alert. Trigger safe-mode fallback / fail-operational ECU policy and store forensic log. |

---

## 4. Interfaces & Dependencies (Contract Notes)

### Person 1 Dependencies
- **`FeatureState` (`src/stark/features/state.py`)**: Expects a 24-feature causal vector per frame containing:
  - Timestamp, $\Delta t$, rolling frequency (50ms, 100ms, 500ms windows),
  - Inter-arrival jitter ($\sigma_{\Delta t}$),
  - Payload entropy (Shannon byte entropy $0.0 - 8.0$),
  - Payload Hamming distance to previous frame,
  - Cyclic counter progression and checksum validity flags.
- **Fixture (`data/samples/fixture.csv`)**: Currently using synthetic placeholder generated on Day 1. Will replace with Person 1's frozen Car-Hacking dataset once landed.

### Person 3 Dependencies
- **ML Inference Service (`src/stark/ml/` / `backend/app/modules/ml/service.py`)**:
  - Input: batch of normalized feature vectors or suspicious frame IDs.
  - Output: `anomaly_score` (float $0.0 - 1.0$), `confidence` ($0.0 - 1.0$), and `predicted_class` (`DoS`, `Fuzzy`, `Spoofing`, `Replay`, `Malfunction`, `Normal`).

---

## 5. Day 1 Verification Checklist

- [x] Python 3.12 virtual environment initialized (`.venv`)
- [x] Backend dependencies installed (`fastapi`, `uvicorn`, `pydantic-settings`, `sqlalchemy`, `aiosqlite`, `pytest`, `pytest-asyncio`, etc.)
- [x] Package importability verified:
  - `python -c "import stark; print(stark.__file__)"` $\rightarrow$ OK (`src/stark/__init__.py`)
  - `python -c "import app; print(app.__file__)"` $\rightarrow$ OK (`backend/app/__init__.py`)
- [x] Test suite passing: 7 tests passed in 0.28s (`backend/tests/test_detection_schemas.py`, `backend/tests/test_health.py`)
- [x] Synthetic placeholder CAN traffic fixture generated at `data/samples/fixture.csv` (4,081 rows: 2,880 normal, 1,201 DoS attack injection)
- [x] Architectural discrepancies documented for team sync on Day 2.
