"""Print 10th/50th/90th percentiles of model features for normal vs fuzzy frames."""

import numpy as np
import pandas as pd

from stark.features.build import build_feature_matrix
from stark.schema import cast_canonical_df

df = cast_canonical_df(pd.read_csv("data/samples/fixture.csv"))
X, y, _ = build_feature_matrix(df)
types = df["attack_type"].to_numpy()

np.set_printoptions(precision=2, suppress=True, linewidth=150)
for kind in ["normal", "fuzzy"]:
    print(f"{kind} (rows: 10th, 50th, 90th percentile)")
    print(np.percentile(X[types == kind], [10, 50, 90], axis=0))
    print()