"""Leave-one-attack-out evaluation on the STARK fixture.

For each attack type, train on normal traffic plus the other attack types,
then test on held-out normal traffic plus the held-out attack type.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from stark.features.build import build_feature_matrix
from stark.schema import cast_canonical_df

SEED = 42
ATTACKS = ["dos", "fuzzy", "gear_spoof", "rpm_spoof"]

df = cast_canonical_df(pd.read_csv("data/samples/fixture.csv"))
normal = df[df["label"] == 0].sort_values("timestamp")
attacks = df[df["label"] == 1]

# Normal traffic: first 70% for training, last 30% for testing (time-ordered).
cut = int(len(normal) * 0.7)
normal_train = normal.iloc[:cut]
normal_test = normal.iloc[cut:]

print(f"{'held-out attack':<16} {'detected':>10} {'false alarms':>14}")
for held in ATTACKS:
    atk_train = attacks[attacks["attack_type"] != held]
    atk_test = attacks[attacks["attack_type"] == held]

    train = pd.concat([normal_train, atk_train]).sort_values("timestamp")
    test = pd.concat([normal_test, atk_test]).sort_values("timestamp")

    # Baseline is fit on training normal frames only, then reused for test.
    X_tr, y_tr, baseline = build_feature_matrix(train)
    X_te, y_te, _ = build_feature_matrix(test, baseline=baseline)

    model = RandomForestClassifier(
        n_estimators=100,
        class_weight="balanced",
        random_state=SEED,
        n_jobs=-1,
    )
    model.fit(X_tr, y_tr)
    y_pred = model.predict(X_te)

    detected = float(np.mean(y_pred[y_te == 1] == 1))
    false_alarms = float(np.mean(y_pred[y_te == 0] == 1))
    print(f"{held:<16} {detected:>10.3f} {false_alarms:>14.3f}")