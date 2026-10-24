# CAN 2.0B Protocol Fundamentals & Attack Grounding

> **Document**: `docs/can_protocol_primer.md`  
> **Author**: Person 2 (Detection Pipeline Module Lead)  
> **Target Audience**: STARK Engineering Team, Evaluators, and Automotive Security Researchers  
> **Date**: Roadmap Day 2  
> **Purpose**: Establish the physical, architectural, and mathematical foundations of Controller Area Network (CAN 2.0B) communication, grounding each of the 7 Stage 1 deterministic rules in protocol mechanics rather than arbitrary heuristic thresholds.

---

## 1. CAN 2.0B Protocol Fundamentals

The Controller Area Network (CAN) is a robust, multi-master serial bus standard designed by Robert Bosch GmbH in the 1980s for automotive applications. Standardized under **ISO 11898-1** (data link layer) and **ISO 11898-2** (high-speed physical layer), CAN provides low-latency communication among Electronic Control Units (ECUs) without a central host computer. Understanding its physical layer, arbitration, and scheduling mechanics reveals why in-vehicle networks are uniquely vulnerable to cyber attacks—and why specific physical anomalies serve as undeniable attack indicators.

```
       +-------------------------------------------------------------+
       |                     CAN Differential Bus                    |
       |  CAN_H -------------------------------------------- CAN_H   |
       |  CAN_L -------------------------------------------- CAN_L   |
       +-------+--------------------+--------------------+-----------+
               |                    |                    |
         +-----+----+         +-----+----+         +-----+----+
         |   ECU 1  |         |   ECU 2  |         | Rogue /  |
         | (Engine) |         | (Brakes) |         | OBD-II   |
         +----------+         +----------+         +----------+
```

### 1.1 Physical Layer & Differential Signaling

Modern automotive CAN buses operate at baud rates up to **500 kbps** (high-speed CAN) or **1 Mbps**. Signaling is differential over a twisted pair designated **CAN_H** (High) and **CAN_L** (Low), terminated at both ends with $120\,\Omega$ split resistors:
* **Recessive State (Logic '1')**: Both lines float at approximately $2.5\,\text{V}$ ($\Delta V = V_{\text{CAN\_H}} - V_{\text{CAN\_L}} \approx 0\,\text{V}$). A node asserting a recessive bit applies no active drive.
* **Dominant State (Logic '0')**: Transceivers drive $V_{\text{CAN\_H}}$ up to $\approx 3.5\,\text{V}$ and pull $V_{\text{CAN\_L}}$ down to $\approx 1.5\,\text{V}$ ($\Delta V \approx 2.0\,\text{V}$).

Because any transmitter driving dominant pulls the entire physical bus to logic `'0'`, the bus behaves as a distributed **Wired-AND** gate (logic `'0'` dominates logic `'1'`).

```
Bus State:   Dominant ('0')              Recessive ('1')
CAN_H:       3.5V  ---------\            2.5V  -----------------
                              \
CAN_L:       1.5V  ---------/            2.5V  -----------------
             Diff: ~2.0V                 Diff: ~0.0V
```

### 1.2 Non-Destructive Bitwise Arbitration & Message Priority

CAN eliminates transmission collisions through **Bitwise Non-Destructive Arbitration**:
1. When the bus is idle, multiple ECUs may transmit simultaneously at the Start-of-Frame (SOF).
2. During the transmission of the Arbitration Field (the CAN Identifier), every transmitting node reads back the physical voltage of the bus bit-by-bit.
3. If Node A transmits a recessive `'1'` but senses a dominant `'0'` on the bus line, Node A concludes that a higher-priority message is contesting the bus.
4. Node A immediately ceases transmission and drops back to receive mode without corrupting the winning transmitter's message.

```
Time Bit:      1 (SOF)   2 (ID bit 1)   3 (ID bit 2)   4 (ID bit 3)
Node A (0x0C):    0            0              0              1 (recessive) -> Loses! Drops to RX
Node B (0x08):    0            0              0              0 (dominant)  -> Wins! Continues TX
Bus Output:       0            0              0              0
```

#### Why Lower Numeric ID Wins the Bus
Because dominant bits represent logic `'0'`, an identifier with more leading zeros asserts dominant voltages longer than an identifier with leading ones. Thus, **numerically smaller IDs have higher priority**. An arbitration ID of `0x000` asserts dominant bits across its entire identifier field, unconditionally preempting all other traffic on the bus.

#### Standard (11-bit) vs. Extended (29-bit) Identifiers
* **CAN 2.0A (Standard Frame)**: Uses an **11-bit Identifier** (`0x000` to `0x7FF`), providing 2,048 possible priority addresses. Widely used for powertrain, chassis, and core safety systems.
* **CAN 2.0B (Extended Frame)**: Uses a **29-bit Identifier** (`0x00000000` to `0x1FFFFFFF`), split into an 11-bit base identifier, an Extended Identifier flag (IDE bit), and an 18-bit identifier extension. Standardized in commercial vehicles (SAE J1939) and diagnostic services, providing over 536 million priority combinations.

### 1.3 Data Length Code (DLC) and Frame Geometry

A classic CAN 2.0B Data Frame is structured as follows:

```
+-----+----------------------+-----+----+------+--------------------+----------+-----+-----+
| SOF |  Arbitration Field   | IDE | r0 | DLC  |     Data Field     |   CRC    | ACK | EOF |
|1 bit| 11 or 29 bits + RTR  |1 bit|1bit|4 bits| 0 to 8 bytes (D0-7)| 16 bits  |2bits|7bits|
+-----+----------------------+-----+----+------+--------------------+----------+-----+-----+
```

* **Data Length Code (DLC)**: A 4-bit field designating the number of data bytes in the Data Field. Valid values are integer values from **0 to 8**. (While values 9–15 are permissible in the framing syntax, they map to an 8-byte payload limit in receiver interpretation).
* **OEM Specification Constraints**: In production vehicles, each CAN ID corresponds to a specific ECU message defined in an OEM database (DBC file). An ECU is programmed to broadcast an immutable payload length (e.g., Engine Speed `0x316` is strictly 8 bytes). Any variation in DLC on that ID represents a violation of OEM architecture.

### 1.4 Real-Time Scheduling and Message Periodicity

In passenger vehicles, the vast majority of intra-vehicular CAN communication is **strictly cyclic (periodic)**:
* **RTOS Task Execution**: Automotive ECUs run real-time operating systems (AUTOSAR or OSEK/VDX) driven by hardware timer interrupts. Tasks are scheduled in fixed deterministic loops:
  * Powertrain / Transmission: 10 ms cycle
  * ABS / Stability Control: 20 ms cycle
  * Climate / Instrument Cluster: 100 ms – 500 ms cycle
* **Predictable Inter-Arrival Time ($\Delta t$)**: Under normal driving conditions, the time difference $\Delta t = t_i - t_{i-1}$ between consecutive frames of a given ID is centered around its nominal cycle period ($T_{\text{nominal}}$) with negligible jitter ($\sigma \le 1.0\,\text{ms}$) induced solely by higher-priority bus arbitration.
* **Why Periodicity Enables Detection**: Unlike Ethernet or general IP networks where packet arrivals are stochastic and bursty, CAN's cyclic determinism guarantees that **temporal deviations are physical anomalies**. When inter-arrival times deviate significantly, it is a physical certainty that either the ECU's execution environment has malfunctioned or an external device is manipulating the bus.

### 1.5 The Core Architectural Vulnerabilities of CAN

CAN 2.0B was engineered in an era when vehicle electronics were isolated physical circuits. Consequently, the protocol lacks basic security primitives:

```
+-----------------------------------+-------------------------------------------------------------+
| Architectural Property            | Security Implication / Exploitation Vector                  |
+-----------------------------------+-------------------------------------------------------------+
| 1. Broadcast Medium               | Every ECU receives every message. Eavesdropping and frame   |
|                                   | sniffing require no elevated network privileges.            |
| 2. No Sender Identification       | Frames identify DATA (e.g. "engine RPM"), not the source.  |
|                                   | There is no hardware MAC or IP address. Any node can send   |
|                                   | any CAN ID at any time.                                     |
| 3. No Authentication or Integrity | No digital signatures or cryptographic hashes. CRC-15 only  |
|                                   | detects random electrical noise, not adversarial injection. |
| 4. Priority-Biased Arbitration    | Dominant bits always silence recessive bits. An attacker    |
|                                   | transmitting 0x000 can perpetually paralyze the bus.       |
| 5. Cleartext Payloads              | Raw telemetry bytes are unencrypted and easily decoded.     |
+-----------------------------------+-------------------------------------------------------------+
```

Once an adversary obtains bus access—via the mandatory legislated **OBD-II port**, compromised telematics/infotainment units (IVI), Bluetooth, or cellular gateways—they can execute:
* **Spoofing / Masquerade**: Injecting fabricated control frames (e.g., false steering angle commands).
* **Flooding / DoS**: Transmitting maximum-priority frames to monopolize the bus.
* **Fuzzing**: Flooding random IDs and payloads to induce ECU resets or actuator faults.
* **Replay Attacks**: Capturing valid historical bus traces and retransmitting them verbatim.

---

## 2. Why Each Stage 1 Rule Works: CAN-Level Reasoning

STARK's Stage 1 Deterministic Rule Engine enforces strict protocol, temporal, and physical invariants directly on the frame stream. Below is the technical justification for each rule, demonstrating why a trigger constitutes a valid attack signal rather than an arbitrary heuristic threshold.

```
                             Raw CAN Frame Stream
                                      │
            ┌─────────────────────────┴─────────────────────────┐
    Protocol Invariants                               Temporal & Physical Invariants
    ├─ R1: Authorized ID Whitelist                    ├─ R2: Minimum Frame Timing (Δt_min)
    └─ R4: DLC Compliance                             ├─ R3: Bus Capacity & Saturation Limit
                                                      ├─ R5: Payload Entropy & Repetition
                                                      ├─ R6: Physical Plant Rate-of-Change
                                                      └─ R7: Watchdog Cycle Timeout
```

---

### Rule 1 (R1): Unknown Arbitration ID

$$\text{Trigger: } \text{ID} \notin \mathcal{W}_{\text{allowed}}$$

#### CAN-Level Reasoning
In modern automotive architectures, the bus topology is statically engineered: every legitimate ECU and corresponding CAN ID is exhaustively specified in the OEM's network communication database (DBC). CAN does not feature dynamic host configuration, service discovery, or ad-hoc node registration. An ID absent from the vehicle profile's authorized whitelist ($\mathcal{W}_{\text{allowed}}$) physically cannot originate from factory-installed ECUs running verified firmware. Its appearance is a conclusive indicator of a rogue hardware connection (e.g., an unauthorized OBD-II telemetry logger, a compromised gateway bridge, or an illicit hardware implant).

#### Attack Context
Fuzzing attacks, penetration testing scanners, and unconfigured aftermarket OBD-II dongles blindly generate random or standard diagnostic identifiers (e.g., `0x7DF`, `0x7E0`) on operational chassis or powertrain buses where they do not belong.

---

### Rule 2 (R2): Impossible Inter-Arrival Time

$$\text{Trigger: } \Delta t = t_i - t_{i-1} < \Delta t_{\text{min}}$$

#### CAN-Level Reasoning
At the physical bit level on a standard 500 kbps CAN bus, a single bit requires $2.0\,\mu\text{s}$. A complete CAN 2.0B frame with an 8-byte payload, CRC, ACK, inter-frame space, and worst-case bit stuffing spans approximately **111 to 135 bit times**, establishing a hard physical transmission floor of **$\approx 220\,\mu\text{s}$ to $270\,\mu\text{s}$**. Furthermore, an authentic ECU generates a specific ID via a dedicated periodic RTOS software timer (e.g., $T_{\text{nominal}} = 20\,\text{ms}$). 

If two frames carrying the identical CAN ID appear within $\Delta t < \Delta t_{\text{min}}$ (e.g., $< 0.5\,\text{ms}$ or $< 5\%\text{ of } T_{\text{nominal}}$), they physically cannot both originate from the genuine single-threaded ECU task. This condition mathematically proves that **two independent transmitters are contending for that ID**—the legitimate ECU alongside an adversarial node injecting spoofed frames onto the physical bus.

```
Legitimate ECU:  [Frame 1 (t=0ms)] ----------------------------------------> [Frame 2 (t=20ms)]
Attacker Node:                 \--> [Spoofed Frame (t=0.3ms)] (COLLISION INJECTION)
Inter-Arrival:                 Δt = 0.3ms  <<<  20ms nominal  ==> R2 CRITICAL TRIGGER!
```

#### Attack Context
In order to override legitimate vehicle behavior (such as acceleration or braking), a masquerade attacker cannot prevent the authentic ECU from transmitting; instead, they must inject malicious messages at an elevated frequency to ensure recipient ECUs process the spoofed payload. This concurrent transmission causes the observed inter-arrival time to collapse to sub-millisecond intervals.

---

### Rule 3 (R3): Overall Bus Message Rate Spike (Flooding / DoS)

$$\text{Trigger: } f_{\text{window}}(\text{bus}) > f_{\text{max}} \quad \text{or} \quad f_{\text{window}}(\text{ID}) > f_{\text{burst}}$$

#### CAN-Level Reasoning
Total bus throughput on a 500 kbps CAN network is mathematically capped at approximately **4,000 frames/second** (assuming standard 8-byte frames under back-to-back transmission). OEM network architects intentionally budget baseline vehicle bus load between **30% and 50% utilization** (~1,200 to 2,000 frames/sec) to provide sufficient idle bus margins and guarantee worst-case latencies for lower-priority safety frames during peak driving events. 

An abrupt surge in aggregate message frequency—or a burst of an individual ID exceeding its configured limits—violates the engineered bus capacity. Because of CAN's bitwise arbitration, high-frequency dominant transmissions monopolize the transceiver state, starving legitimate ECUs of arbitration wins and driving the physical bus to saturation.

#### Attack Context
Denial-of-Service (DoS) attacks systematically inject zero-dominant frames (`0x000`) or high-priority messages back-to-back with zero delay, exhausting the bus bandwidth and preventing emergency brake or steering control frames from completing arbitration.

---

### Rule 4 (R4): DLC Compliance Violation

$$\text{Trigger: } \text{DLC} \notin [0, 8] \quad \text{or} \quad \text{DLC} \neq \text{DLC}_{\text{expected}}(\text{ID})$$

#### CAN-Level Reasoning
In classical CAN 2.0B, the Data Length Code specifies an integer payload length between 0 and 8 bytes. In automotive manufacturing, every message ID has a rigid, static signal layout defined in the DBC file; an ECU's transmission buffer and serialization routine are compiled with fixed lengths. For instance, a vehicle speed message is permanently configured as an 8-byte frame. 

An ECU never dynamically varies its payload length during normal operation. A frame observed with an out-of-spec DLC ($> 8$), or a DLC deviating from the vehicle profile's expected value for that specific ID, indicates synthetic packet construction. Such packets are generated by external software or fuzzing utilities that fail to emulate the OEM's static transmission constraints.

#### Attack Context
Automated fuzzing tools randomly alter packet fields to trigger buffer overflows or parsing exceptions in recipient ECU transceivers, frequently emitting frames with truncated or oversized DLC values.

---

### Rule 5 (R5): ID Repetition Burst

$$\text{Trigger: } \text{Payload}_i == \text{Payload}_{i-1} == \dots == \text{Payload}_{i-k} \quad \text{with} \quad k > K_{\text{max}} \;\land\; \Delta t \le \Delta t_{\text{nominal}}$$

#### CAN-Level Reasoning
Under normal operation, periodic CAN messages exhibit dynamic byte entropy. Modern automotive networks implement End-to-End (E2E) protection profiles (AUTOSAR E2E Profile 1/2) that embed a **monotonically increasing rolling alive counter** (e.g., 4 bits incrementing $0 \to 15$) and a dynamic **CRC checksum** in the payload of every periodic frame. Even in a stationary vehicle with idling sensors, the rolling counter ensures consecutive payloads are never bitwise identical.

A sustained burst of consecutive frames sharing byte-for-byte identical payloads indicates an artificial transmission stream. Such streams lack valid rolling counter state transitions and betray an attacker replaying captured frames or blindly overriding sensor states.

```
Legitimate Transmission:
Frame 1: [0x1A 0x44 0x00 0x82 0x01 (Counter=1) (CRC=0x9F)]
Frame 2: [0x1A 0x44 0x00 0x82 0x02 (Counter=2) (CRC=0xA4)]  <-- Byte variation!

Replay / Synthetic Injection:
Frame 1: [0x1A 0x44 0x00 0x82 0x01 (Counter=1) (CRC=0x9F)]
Frame 2: [0x1A 0x44 0x00 0x82 0x01 (Counter=1) (CRC=0x9F)]  <-- Identical clone!
Frame 3: [0x1A 0x44 0x00 0x82 0x01 (Counter=1) (CRC=0x9F)]  ==> R5 TRIGGER!
```

#### Attack Context
In replay and simple injection attacks, adversaries capture a single high-impact frame (e.g., "unlock doors" or "engine stop") and inject it in a rapid burst without recalculating live checksums or advancing sequence counters.

---

### Rule 6 (R6): Suspicious Payload Jump (Rate-of-Change Invariant)

$$\text{Trigger: } |\text{Signal}_i - \text{Signal}_{i-1}| > \Delta \text{Val}_{\text{max}} \quad \text{or} \quad \text{Hamming}(d_i, d_{i-1}) > H_{\text{max}}$$

#### CAN-Level Reasoning
CAN payloads transmit measurements of real-world mechanical, thermal, and electrical systems. Physical systems possess inertia, friction, and thermal capacitance governed by Newtonian mechanics:
* A vehicle moving at $50\,\text{km/h}$ cannot physically accelerate to $180\,\text{km/h}$ over a $10\,\text{ms}$ sampling window ($\Delta t$).
* Steering wheel angles, coolant temperatures, and wheel speeds change smoothly across consecutive discrete sampling intervals.

When an adversary injects falsified telemetry to spoof control systems (e.g., injecting zero wheel speed while in motion to induce ABS lockup), the forged frames create a discontinuous step function relative to preceding legitimate telemetry. This abrupt jump violates physical rate-of-change limits ($\Delta \text{Val} / \Delta t$).

#### Attack Context
Spoofing attacks targeting drive-by-wire subsystems directly overwrite target sensor bytes with extreme static values to manipulate actuator responses, producing unmistakable payload discontinuities.

---

### Rule 7 (R7): Message Silence / Timeout

$$\text{Trigger: } \Delta t_{\text{elapsed}} > \tau_{\text{timeout}} = M \times T_{\text{nominal}} \quad (M \ge 3)$$

#### CAN-Level Reasoning
Every critical ECU on a vehicle network maintains a heartbeat broadcast. Safety-critical recipient nodes run internal watchdog timers programmed to enter a fail-safe state if an expected periodic message is absent for more than $3\times$ to $5\times$ its cycle time. 

If an authorized periodic ID ceases transmission on the physical bus, it indicates that the transmitting node has been silenced. In an adversarial context, this is achieved via a **Bus-Off Attack**: the attacker injects targeted dominant bits during the recessive portions of the victim's transmission, forcing the victim's internal Transmit Error Counter (TEC) past the protocol limit of 255 and driving it into the **Bus-Off state**, physically disconnecting it from the network.

```
Victim ECU TX:         ... 1 1 0 1 (Recessive) ...
Attacker Injection:    ... 1 1 0 0 (Dominant)  ...
Victim senses Bit Error -> Increments Transmit Error Counter (TEC += 8)
When TEC > 255          -> Victim enters BUS-OFF (Isolated from bus!)
Result on Bus:         Target CAN ID goes completely SILENT ==> R7 TRIGGER!
```

#### Attack Context
Bus-Off attacks deliberately knock safety ECUs (e.g., ADAS radar, Electronic Stability Control) offline to disable collision mitigation or prevent an authentic node from contesting an attacker's spoofed replacement messages.

---

## 3. Summary Matrix: Protocol Invariants & Stage 1 Defense

| Rule ID | Rule Name | Enforced Invariant | Target Threat / Exploit | Severity | Stage 2 ML Synergy |
|:---:|---|---|---|:---:|---|
| **R1** | **Unknown CAN ID** | Closed DBC namespace constraint | Rogue ECU insertion, foreign OBD-II dongle, diagnostic breach | **CRITICAL (1.0)** | ML cannot override. Immediate hard alarm. |
| **R2** | **Impossible Inter-Arrival** | Physical transmission duration & single-threaded ECU task timing | Masquerade injection, dual-transmitter contention | **HIGH (0.85)** | Confirmed by ML sequence models; suppresses minor transceiver jitter. |
| **R3** | **Bus Flooding** | Maximum physical bus capacity (4,000 fps @ 500 kbps) | DoS attack, arbitration priority saturation (`0x000`) | **CRITICAL (0.90)** | Evaluates sustained burst length and network degradation. |
| **R4** | **DLC Violation** | Static OEM message frame geometry & CAN 2.0B limits | Protocol fuzzing, buffer overflow probes, malformed frames | **HIGH (0.70)** | ML cannot override hard protocol violations. |
| **R5** | **Repetition Burst** | Natural signal variance & E2E rolling counter progression | Replay attack, frozen sensor failure, state override | **MEDIUM (0.55)** | Stage 2 verifies if static payload matches benign stationary state. |
| **R6** | **Payload Jump** | Mechanical plant inertia & continuity ($\Delta v / \Delta t$) | Sensor spoofing, false telemetry injection, drive-by-wire override | **HIGH (0.80)** | Deep sequential model confirms whether transient is road bump or exploit. |
| **R7** | **Message Silence** | Real-time periodic heartbeat & watchdog constraints | Bus-off attack, node isolation, severed wiring harness | **MEDIUM (0.45)** | Isolates cyber bus-off exploits from benign ignition shut-off. |

---

## 4. Architectural Notes & Open Discussion Items for Day 3

As we prepare to draft the formal Stage 1 Rule Specification (`config/rules.yaml` schema and detection algorithms) on Day 3, the following technical considerations and edge cases must be coordinated across the STARK engineering team:

1. **Handling Event-Triggered (Aperiodic) IDs vs. Periodic IDs**:
   * *Problem*: While powertrain/chassis frames are strictly periodic, certain body/comfort frames (e.g., door locks, turn signals, hazard lights) are event-driven.
   * *Impact on Rules*: R2 (impossible $\Delta t$) and R7 (silence timeout) will trigger false alarms on aperiodic IDs if evaluated against rigid cyclic baselines.
   * *Proposed Spec*: The baseline profiler (`src/stark/baseline/profiler.py`) must flag each ID as either `PERIODIC` or `EVENT_TRIGGERED`. R7 will be deactivated for event-triggered IDs, and R2 will enforce only the physical transceiver limit ($\Delta t_{\text{min}} \approx 0.25\,\text{ms}$) rather than nominal cycle proportions.

2. **DBC Signal Decoding vs. Raw Bitwise Payload Jump (R6)**:
   * *Problem*: Full physical signal validation (e.g. converting raw bytes to $\text{km/h}$) requires proprietary OEM DBC files that vary by vehicle make and model.
   * *Proposed Spec*: For Phase 1, implement R6 using a combination of **Bitwise Hamming Distance** ($H(d_i, d_{i-1}) > H_{\text{max}}$) and **Unsigned Big-Endian Integer deltas** over consecutive payloads. This provides DBC-agnostic anomaly detection that flags extreme byte transitions across any vehicle platform.

3. **DLC 9–15 Classical CAN Edge Cases (R4)**:
   * *Problem*: The CAN 2.0B framing specification permits DLC values 9 through 15 (which hardware controllers clamp to an 8-byte payload).
   * *Proposed Spec*: Enforce two-tier checking in R4: (a) a strict bound $\text{DLC} \le 8$, and (b) exact matching against the observed baseline length ($\text{DLC} == \text{DLC}_{\text{expected}}$). Any frame with $\text{DLC} > 8$ or differing from the baseline is flagged.

4. **Minimum Inter-Arrival Limit ($\Delta t_{\text{min}}$) Definition**:
   * *Problem*: Should $\Delta t_{\text{min}}$ be a global constant (e.g., physical transmission time of $\approx 0.25\,\text{ms}$) or an ID-specific fractional threshold (e.g., $\Delta t < 0.2 \times T_{\text{nominal}}$)?
   * *Proposed Spec*: Use a dual-condition test: $\Delta t < \max(\Delta t_{\text{physical\_floor}}, \; \alpha \cdot T_{\text{nominal}}(\text{ID}))$, where $\Delta t_{\text{physical\_floor}} = 0.20\,\text{ms}$ and $\alpha = 0.15$.

---

> *With the completion of this protocol primer, the CAN physical and data link layer foundations are established. The detection pipeline module has mathematical and protocol grounding to draft the formal rule specifications on Day 3 and begin rule implementations on Day 7.*
