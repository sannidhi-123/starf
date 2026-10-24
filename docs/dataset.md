# STARK Dataset Documentation

## Overview
STARK is evaluated against in-vehicle Controller Area Network (CAN) bus traffic datasets:
1. **Car-Hacking Dataset** (HCRL / Korea University): Captures standard CAN 2.0B traffic under DoS, Fuzzy, Gear Spoofing, and RPM Spoofing attacks recorded from real vehicles (e.g., Hyundai YF Sonata).
2. **OTIDS Dataset** (Oak Ridge National Laboratory): Captures DoS, Fuzzy, and Impersonation attacks, including Remote Transmission Request (RTR) frames.

---

## Fixture Origin (`data/samples/fixture.csv`)
> [!IMPORTANT]
> The raw Car-Hacking dataset was not present in the local repository under `data/raw/car_hacking/`. To ensure fully deterministic testing, validation, and reproducible CI/CD execution without presenting unverified data as real, `data/samples/fixture.csv` is **synthetically generated** with fixed seed `random_state=42`. All rows are explicitly labeled with `source="synthetic"`.

### Fixture Specifications
- **Total Frames**: 5,000 canonical rows
- **Schema Version**: `1.0`
- **Source Label**: `synthetic`
- **Capture**: `fixture`
- **Attack Breakdown**:
  - `normal`: 4,000 frames (`label=0`, `label_quality="frame"`)
  - `dos`: 250 frames (`label=1`, high-frequency injection on arbitration ID `0x000`)
  - `fuzzy`: 250 frames (`label=1`, random CAN IDs and random byte payloads)
  - `gear_spoof`: 250 frames (`label=1`, spoofed transmission payload on ID `0x430`)
  - `rpm_spoof`: 250 frames (`label=1`, spoofed engine RPM payload on ID `0x316`)
- **Missing Payload Rule**: Strict adherence to STARK Rule 1: missing bytes ($DLC < 8$) are padded with `-1` (never `0`).
- **Timestamp Re-basing**: Re-based to start at exactly `0.0` seconds with strictly non-decreasing monotonic timestamps.

---

## Dataset Separation & Training Isolation
Car-Hacking and OTIDS datasets originate from distinct vehicular architectures with differing baud rates, ID allocation schemes, and transmission intervals. Furthermore, OTIDS contains Remote Transmission Request (RTR) frames (`is_remote=True`) and window-level ground truth for fuzzy/impersonation attacks. Consequently, **Car-Hacking and OTIDS are maintained as strictly separate sources and are never merged for model training**.

---

## Memory & Resource Figures
- **Canonical Frame Size**: ~17 columns per frame.
- **5,000-frame fixture RAM footprint**: < 1 MB in memory.
- **Estimated Full Car-Hacking Run**: ~2,000,000+ frames per attack file (~150 MB Parquet, ~300 MB in memory when loaded with optimized canonical dtypes `int8`, `int16`, `float64`, `category`).

