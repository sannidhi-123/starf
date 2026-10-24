# STARK Stage 1 Rule Specification

> **Document**: `docs/rule_spec.md`  
> **Author**: Person 2 (Detection Pipeline Module Lead)  
> **Status**: Frozen Design Spec (Stage 1 Deterministic Rules)  
> **Date**: Roadmap Day 3  
> **Related Documents**: [`docs/can_protocol_primer.md`](file:///Users/sannidhichouthayi/Documents/starf/docs/can_protocol_primer.md), [`config/rules.yaml`](file:///Users/sannidhichouthayi/Documents/starf/config/rules.yaml)

---

## 1. Overview & Architecture Role

Stage 1 is the high-throughput, deterministic first layer of the STARK intrusion detection pipeline. Operating directly on incoming CAN frames and their accompanying causal feature vectors, Stage 1 evaluates every frame against seven strictly defined protocol and temporal rules in $< 0.1\,\text{ms}$.

### 1.1 Core Principles
1. **Deterministic Protocol Invariants**: Stage 1 enforces hard physical and protocol boundaries. High-priority violations (e.g. unknown arbitration IDs or physical transmission impossibilities) cannot be overridden by Stage 2 machine learning.
2. **Causal Stream Evaluation**: Every rule operates strictly on past and current frame state ($t \le t_{\text{current}}$). Future lookahead is strictly prohibited.
3. **Four-Tier Threshold Hierarchy**: Thresholds are established with the following strict priority:
   - **Tier 1 (Domain Constraints)**: Non-negotiable physical/protocol boundaries (e.g., $\text{DLC} \in [0, 8]$, physical bit-time transmission floor $\approx 0.20\,\text{ms}$).
   - **Tier 2 (Per-ID Normal Baselines)**: Statistical percentiles computed by the profiler from benign baseline traffic (e.g., `p01_dt`, `p99_dt`, `p995_rep`, `p99_hamming`, `modal_dlc`).
   - **Tier 3 (Global Bus Percentiles)**: Bus-wide statistical distributions from normal traffic (e.g., `p999` message count in a 50ms window).
   - **Tier 4 (Tuned Multipliers)**: Multipliers tuned strictly on the validation partition (never hardcoded, never tuned on test data; e.g., `r2_factor`, `r7_factor`).

---

## 2. Severity Weights & Verdict Arbitration

### 2.1 Fixed Rule Severity Table

Each rule evaluates independently to a boolean trigger state. When triggered, it produces an individual rule verdict and contributes its fixed severity weight:

| Rule ID | Rule Name | Output Verdict | Severity Weight ($w_r$) | Target Threat Category |
|:---:|---|:---:|:---:|---|
| **R1** | Unknown CAN ID | `VIOLATION` | **3** | Rogue ECU Insertion / Unauthorized OBD-II Device |
| **R2** | Impossible Inter-Arrival | `VIOLATION` | **3** | Direct Masquerade Injection / Dual-Transmitter Contention |
| **R3** | Bus Flooding | `VIOLATION` | **3** | Denial of Service (DoS) / Bus Saturation (`0x000` Abuse) |
| **R4** | DLC Violation | `SUSPECT` | **2** | Protocol Fuzzing / Malformed Frame Injection |
| **R5** | ID Repetition Burst | `SUSPECT` | **2** | Replay Attack / Sensor State Freeze / Masquerade |
| **R6** | Suspicious Payload Jump | `SUSPECT` | **2** | Telemetry Spoofing / Discontinuous Actuator Override |
| **R7** | Message Silence / Timeout | `SUSPECT` | **1** | Bus-Off Attack / Node Isolation / Hardware Disconnect |

### 2.2 Composite Verdict Logic

Let $\mathcal{R}_{\text{fired}} \subseteq \{\text{R1}, \dots, \text{R7}\}$ be the set of rules that fired on the current frame.  
The total Stage 1 score is defined as:

$$\text{rule\_score} = \sum_{r \in \mathcal{R}_{\text{fired}}} w_r$$

The overall Stage 1 verdict ($\mathcal{V}_{\text{Stage1}}$) is arbitrated as follows:

$$\mathcal{V}_{\text{Stage1}} = \begin{cases}
\textbf{VIOLATION} & \text{if } \exists r \in \mathcal{R}_{\text{fired}} \text{ such that } w_r = 3 \quad (\text{R1, R2, or R3 fired}) \\
\textbf{SUSPECT} & \text{else if } \text{rule\_score} \ge 2 \quad (\text{any } w=2 \text{ rule fired, or multiple } w=1) \\
\textbf{CLEAN} & \text{otherwise} \quad (\text{rule\_score} \le 1)
\end{cases}$$

*Note*: If only R7 fires ($\text{rule\_score} = 1$), it registers as informational/warning telemetry and passes as `CLEAN` unless compounded by another anomaly or elevated to `SUSPECT` by persistent watchdog evaluation in the state profiler.

---

## 3. Detailed Specification for Rules R1 – R7

---

### Rule 1 (R1): Unknown CAN ID

* **Rule ID**: `R1`
* **Rule Name**: `unknown_can_id`
* **Target Exploit**: Rogue hardware insertion, unauthorized OBD-II scanners, diagnostic gateway compromise.
* **Severity Weight**: `3`
* **Rule Verdict**: `VIOLATION`
* **Input Feature(s)**:
  * `can_id` (`int` or hex integer format, e.g. `0x140` / `320`)
* **Exact Trigger Condition**:
  ```python
  can_id not in config.id_whitelist
  ```
* **Threshold Source**:
  * **Source 1 (Domain Constraint)** & **Source 2 (Per-ID Baseline)**: The vehicle communication database (DBC) or the empirical set of all arbitration IDs observed during benign baseline profiling ($\mathcal{W}_{\text{allowed}}$).
* **Reason String Template**:
  ```python
  f"unknown CAN ID 0x{can_id:03X} not in authorized whitelist"
  ```
* **Protocol Grounding**: CAN bus topology is static and defined at manufacturing time. Because CAN lacks dynamic addressing, any unseen ID is physical proof of unauthorized hardware broadcasting on the bus.

---

### Rule 2 (R2): Impossible Inter-Arrival Time

* **Rule ID**: `R2`
* **Rule Name**: `impossible_inter_arrival`
* **Target Exploit**: Masquerade injection, frame collision injection, high-frequency overriding.
* **Severity Weight**: `3`
* **Rule Verdict**: `VIOLATION`
* **Input Feature(s)**:
  * `can_id` (`int`)
  * `dt_same_id` (`float`, elapsed time in seconds since the previous frame with this identical CAN ID)
* **Exact Trigger Condition**:
  ```python
  (config.is_periodic.get(can_id, True)) and (
      dt_same_id < max(
          config.physical_min_dt,  # Hard physical transmission floor: 0.00020 s (0.20 ms)
          config.p01_dt[can_id] * config.r2_factor
      )
  )
  ```
* **Threshold Source**:
  * **Source 1 (Domain Constraint)**: `physical_min_dt = 0.00020` seconds (at 500 kbps, a standard 8-byte frame requires $\approx 220 - 270\,\mu\text{s}$ on the wire).
  * **Source 2 (Per-ID Baseline)**: `p01_dt[can_id]` — 1st percentile of inter-arrival time for this ID during normal operation.
  * **Source 4 (Tuned Multiplier)**: `r2_factor` — validation-tuned multiplier (nominal range: `0.15` to `0.30`).
* **Reason String Template**:
  ```python
  f"impossible inter-arrival dt={dt_same_id*1000:.3f}ms for ID 0x{can_id:03X} below learned floor {threshold*1000:.3f}ms (p01={p01*1000:.3f}ms, r2_factor={r2_factor})"
  ```
* **Protocol Grounding**: An authentic ECU transmits periodic messages via a single-threaded cyclic timer interrupt. If two messages with the same ID arrive faster than physically permissible or significantly faster than the nominal cycle, two distinct transmitters are concurrently broadcasting on that ID.

---

### Rule 3 (R3): Bus Flooding

* **Rule ID**: `R3`
* **Rule Name**: `bus_flooding`
* **Target Exploit**: Denial of Service (DoS) attack, high-priority arbitration starvation (`0x000` flooding).
* **Severity Weight**: `3`
* **Rule Verdict**: `VIOLATION`
* **Input Feature(s)**:
  * `msg_rate_50ms` (`float`, total bus message rate in frames per second, calculated over the trailing 50ms sliding window: $N_{\text{frames\_50ms}} / 0.050$)
* **Exact Trigger Condition**:
  ```python
  msg_rate_50ms > config.r3_global_rate
  ```
* **Threshold Source**:
  * **Source 1 (Domain Constraint)**: Physical maximum bus capacity (at 500 kbps, maximum theoretical throughput is $\approx 4,000\,\text{fps}$; nominal OEM utilization is 30%–50% $\approx 1,200 - 2,000\,\text{fps}$).
  * **Source 3 (Global Percentile)**: `p999` of rolling 50ms message rate derived across all normal training sessions.
  * **Source 4 (Tuned Parameter)**: `r3_global_rate` — set at or slightly above `p999_msg_rate_50ms` (e.g., $2,500\,\text{fps}$).
* **Reason String Template**:
  ```python
  f"bus flooding detected: message rate {msg_rate_50ms:.1f} fps exceeds global threshold {r3_global_rate:.1f} fps"
  ```
* **Protocol Grounding**: CAN bitwise arbitration allows dominant-bit streams to monopolize the transceiver bus line. Flooding forces legitimate safety-critical ECUs into continuous arbitration loss, resulting in vehicle system paralysis.

---

### Rule 4 (R4): DLC Violation

* **Rule ID**: `R4`
* **Rule Name**: `dlc_violation`
* **Target Exploit**: Protocol fuzzing, buffer overflow boundary testing, malformed frame synthesis.
* **Severity Weight**: `2`
* **Rule Verdict**: `SUSPECT`
* **Input Feature(s)**:
  * `can_id` (`int`)
  * `dlc` (`int`, Data Length Code reported in the frame header)
* **Exact Trigger Condition**:
  ```python
  (dlc < 0 or dlc > 8) or (dlc != config.modal_dlc.get(can_id, config.modal_dlc_default))
  ```
* **Threshold Source**:
  * **Source 1 (Domain Constraint)**: $\text{DLC} \in [0, 8]$ (CAN 2.0B physical payload constraint).
  * **Source 2 (Per-ID Baseline)**: `modal_dlc[can_id]` — the fixed, mode payload length observed for this ID in normal vehicle profiling.
* **Reason String Template**:
  ```python
  f"DLC violation for ID 0x{can_id:03X}: observed dlc={dlc} does not match expected {expected_dlc} (domain: [0,8])"
  ```
* **Protocol Grounding**: In OEM vehicle architecture, signal packing is fixed at firmware compile time. A valid ECU never varies its payload length during operation. Deviations denote synthetic or corrupted packet injection.

---

### Rule 5 (R5): ID Repetition Burst

* **Rule ID**: `R5`
* **Rule Name**: `id_repetition_burst`
* **Target Exploit**: Replay attacks, masquerade injection with static payload, frozen actuator tampering.
* **Severity Weight**: `2`
* **Rule Verdict**: `SUSPECT`
* **Input Feature(s)**:
  * `can_id` (`int`)
  * `id_repetition_count` (`int`, consecutive count of frames for this specific CAN ID having byte-for-byte identical payloads `d0..d7`)
* **Exact Trigger Condition**:
  ```python
  id_repetition_count > config.p995_rep.get(can_id, config.default_max_repetition)
  ```
* **Threshold Source**:
  * **Source 2 (Per-ID Baseline)**: `p995_rep[can_id]` — 99.5th percentile of consecutive identical payload counts observed in normal traffic. (For IDs with dynamic counters, $p_{99.5} = 1$; for static status IDs, $p_{99.5}$ represents normal idle repetition).
* **Reason String Template**:
  ```python
  f"repetition burst for ID 0x{can_id:03X}: {id_repetition_count} consecutive identical payloads exceeds threshold {p995_rep}"
  ```
* **Protocol Grounding**: Authentic dynamic frames incorporate rolling alive counters ($0 \to 15$) and checksums. Replay attackers repeatedly inject static frame snapshots at high speed, creating an unnatural sequence of identical payloads.

---

### Rule 6 (R6): Suspicious Payload Jump

* **Rule ID**: `R6`
* **Rule Name**: `payload_jump`
* **Target Exploit**: Sensor spoofing, false telemetry injection, drive-by-wire step-function override.
* **Severity Weight**: `2`
* **Rule Verdict**: `SUSPECT`
* **Input Feature(s)**:
  * `can_id` (`int`)
  * `hamming_prev_same_id` (`int`, bitwise Hamming distance between the current 64-bit payload and the preceding payload of the same CAN ID, $\in [0, 64]$)
* **Exact Trigger Condition**:
  ```python
  hamming_prev_same_id > config.p99_hamming.get(can_id, config.default_max_hamming)
  ```
* **Threshold Source**:
  * **Source 2 (Per-ID Baseline)**: `p99_hamming[can_id]` — 99th percentile of bitwise Hamming distance between consecutive frames of this ID under normal vehicle operating dynamics.
* **Reason String Template**:
  ```python
  f"suspicious payload jump for ID 0x{can_id:03X}: Hamming distance {hamming_prev_same_id} bits exceeds threshold {p99_hamming} bits"
  ```
* **Protocol Grounding**: Physical vehicle components (wheel speed, throttle, steering) possess mechanical inertia and follow continuous Newtonian physics. Discontinuous jumps across consecutive frames violate physical rate-of-change limits.

---

### Rule 7 (R7): Message Silence / Timeout

* **Rule ID**: `R7`
* **Rule Name**: `message_silence`
* **Target Exploit**: Bus-off attack, ECU power harness disconnection, node isolation exploit.
* **Severity Weight**: `1`
* **Rule Verdict**: `SUSPECT`
* **Input Feature(s)**:
  * `can_id` (`int`)
  * `dt_same_id` (`float`, elapsed time in seconds since the previous frame with this identical CAN ID)
* **Exact Trigger Condition**:
  ```python
  (config.is_periodic.get(can_id, False)) and (
      dt_same_id > (config.p99_dt[can_id] * config.r7_factor)
  )
  ```
* **Threshold Source**:
  * **Source 2 (Per-ID Baseline)**: `p99_dt[can_id]` — 99th percentile of inter-arrival time from normal traffic (representing the nominal cycle period $T_{\text{nominal}}$).
  * **Source 4 (Tuned Multiplier)**: `r7_factor` — validation-tuned watchdog multiplier (nominal range: `3.0` to `5.0` times normal period).
* **Reason String Template**:
  ```python
  f"message silence timeout for ID 0x{can_id:03X}: elapsed {dt_same_id*1000:.1f}ms exceeds watchdog threshold {threshold*1000:.1f}ms (p99={p99*1000:.1f}ms, r7_factor={r7_factor})"
  ```
* **Protocol Grounding**: Authentic periodic ECUs broadcast heartbeat signals continuously. If an expected periodic ID ceases transmission, the transmitting node has either lost power or has been driven into the Bus-Off state by an attacker exploiting error counters.

---

## 4. Feature Registry Dependencies

The Stage 1 Rule Engine reads six specific features from the incoming data stream. The table below maps each rule's requirements to the formal 24-feature vector being developed by Person 1:

| Feature Identifier | Data Type | Units / Range | Consuming Rules | Verification Status |
|---|:---:|:---:|:---:|:---:|
| `can_id` | `int` | `0x000`–`0x7FF` (or 29-bit) | R1, R2, R4, R5, R6, R7 | **CONFIRMED** (Raw frame header) |
| `dlc` | `int` | `0` to `8` | R4 | **CONFIRMED** (Raw frame header) |
| `dt_same_id` | `float` | Seconds ($\ge 0.0$) | R2, R7 | **PENDING PERSON 1 CONFIRMATION** |
| `msg_rate_50ms` | `float` | Frames / second ($\ge 0.0$) | R3 | **PENDING PERSON 1 CONFIRMATION** |
| `id_repetition_count` | `int` | Counts ($\ge 0$) | R5 | **PENDING PERSON 1 CONFIRMATION** |
| `hamming_prev_same_id`| `int` | Bits ($0$ to $64$) | R6 | **PENDING PERSON 1 CONFIRMATION** |

### Critical Items to Verify with Person 1 Before Day 7 & 9
1. **`dt_same_id` Units**: Spec assumes **seconds** (`float`). If Person 1 outputs milliseconds (`ms`), multipliers and physical floors must scale by $10^3$.
2. **`msg_rate_50ms` vs. `msg_count_50ms`**: Spec assumes normalized rate (frames/sec over 50ms window). If Person 1 outputs raw count in window ($N$), condition will compare against count threshold ($N > \text{threshold}$).
3. **`id_repetition_count` State**: Verify whether repetition tracking resets to `0` or `1` upon payload divergence, and confirm whether it tracks identical payloads *per ID* or across *global* consecutive frames. (Stage 1 requires *per ID* identical payload repetition).
4. **`hamming_prev_same_id` Scope**: Confirm that Hamming distance is computed against the *previous frame of the same ID*, rather than the physically adjacent frame on the bus (which will almost always have a different ID and non-comparable payload layout).
