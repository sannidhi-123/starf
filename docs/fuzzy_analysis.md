# Fuzzy held-out evaluation

## Setup and counts

This analysis uses the fixture's leave-one-attack-out split. When `fuzzy` is held out, the model trains on 2,800 normal frames and 750 frames from the other attack types (3,550 total); the test fold contains 1,200 normal and 250 fuzzy frames (1,450 total). The fuzzy type is absent from the fit fold by design. The three random forest seeds are 42, 7, and 123.

With SMOTE disabled, the fit counts remain 2,800 normal / 750 attack. With SMOTE enabled, only the fit fold changes, to 2,800 normal / 2,800 attack. Validation and test stay at their original class counts. No features were changed.

## Detection and probability evidence

At the default 0.5 threshold, fuzzy detection across seeds is 0.236, 0.308, and 0.284 without SMOTE (mean 0.276; range 0.236–0.308). Each result uses 250 fuzzy and 1,200 normal test frames, with 0 false alarms. With SMOTE, rates are 0.200, 0.264, and 0.180 (mean 0.215; range 0.180–0.264), also with 0 false alarms. Thus SMOTE does not improve fuzzy detection in these runs.

For seed 42, held-out fuzzy probabilities have median 0.26; 19.2% of the 250 fuzzy frames are within 0.1 of the 0.5 threshold. Across seeds, medians are 0.26, 0.275, and 0.32 and the near-threshold fractions are 19.2%, 19.6%, and 22.0%. Most held-out fuzzy probabilities are below the decision boundary, so the main issue is systematic under-scoring rather than probabilities clustering tightly at 0.5. This is consistent with a model that has no fuzzy examples in its training fold: separation from normal on selected feature percentiles does not teach a binary model how the unseen fuzzy class compares with the other known attack classes.

## Validation threshold check

Thresholds were selected only on a chronological validation tail containing known training classes. For each seed, validation contains 560 normal and 150 known attack frames; the held-out test remains 1,200 normal and 250 fuzzy frames. The selection maximized validation recall while requiring validation false alarm rate not to exceed its rate at threshold 0.5. Validation selected thresholds reached 100% recall with 0% false alarms, both with and without SMOTE.

Those thresholds do not transfer to the unseen fuzzy test class: detection was 0/250 (0%) with 0/1,200 false alarms for every seed, in both SMOTE configurations. Validation threshold tuning therefore did not improve held-out fuzzy detection. Lowering the threshold based on the test fold would be test leakage and is not done here.

## Conclusion

The unresolved limitation is attack-type generalization: the fuzzy class is absent from training, and the learned scores are generally too low for its frames. The standard chronological split separately has no fuzzy frames in its test partition; its accuracy equals the all-normal baseline and its false negative rate is 1.0. The current evidence does not identify a faulty feature, so the feature set remains unchanged. Addressing this limitation requires representative fuzzy training data or a separately validated novelty-detection approach, followed by evaluation on a held-out capture.
