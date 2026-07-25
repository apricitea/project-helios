"""Two independently-calibrated binary classifiers: churn and late-payment risk.

Mirrors a real production lesson: a shared multiclass score space conflates
distinct risk types and produces poorly-calibrated joint predictions.
Decomposing into independent binary classifiers lets each optimize its own
decision boundary and threshold, at the cost of training two models instead
of one.

Usage:
    uv run python -m project_helios.model.train --train-date 2026-06-20
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from project_helios.model.dataset import CATEGORICAL_COLUMNS, FEATURE_COLUMNS, build_training_frame
from project_helios.warehouse.db import get_connection

SEED = 42
MODEL_COLUMNS = FEATURE_COLUMNS + CATEGORICAL_COLUMNS


@dataclass(frozen=True)
class TrainResult:
    label: str
    auc: float
    brier_score: float
    n_train: int
    n_holdout: int
    feature_importances: dict[str, float]


def _build_pipeline() -> Pipeline:
    preprocess = ColumnTransformer(
        [("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_COLUMNS)],
        remainder="passthrough",
    )
    model = HistGradientBoostingClassifier(random_state=SEED)
    return Pipeline([("preprocess", preprocess), ("model", model)])


def train_classifier(frame: pd.DataFrame, label_col: str) -> tuple[Pipeline, TrainResult]:
    x = frame[MODEL_COLUMNS]
    y = frame[label_col]

    x_train, x_holdout, y_train, y_holdout = train_test_split(
        x, y, test_size=0.2, random_state=SEED, stratify=y
    )

    pipeline = _build_pipeline()
    pipeline.fit(x_train, y_train)

    proba = pipeline.predict_proba(x_holdout)[:, 1]
    auc = roc_auc_score(y_holdout, proba)
    brier = brier_score_loss(y_holdout, proba)

    # Permutation importance on the holdout set: unlike impurity-based
    # importance, it isn't biased toward high-cardinality features and works
    # for any estimator, including HistGradientBoostingClassifier.
    perm = permutation_importance(
        pipeline, x_holdout, y_holdout, n_repeats=5, random_state=SEED, scoring="roc_auc"
    )
    importance_map = dict(zip(MODEL_COLUMNS, perm.importances_mean, strict=True))

    result = TrainResult(
        label=label_col,
        auc=float(auc),
        brier_score=float(brier),
        n_train=len(x_train),
        n_holdout=len(x_holdout),
        feature_importances=importance_map,
    )
    return pipeline, result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-date", required=True)
    parser.add_argument("--db", type=Path, default=Path("data/warehouse.duckdb"))
    args = parser.parse_args()

    conn = get_connection(args.db)
    frame = build_training_frame(conn, args.train_date)

    for label_col in ["churn_label", "late_payment_label"]:
        _, result = train_classifier(frame, label_col)
        print(f"\n=== {label_col} ===")
        print(
            f"AUC: {result.auc:.3f}  Brier: {result.brier_score:.3f}  "
            f"n_train={result.n_train}  n_holdout={result.n_holdout}"
        )
        top = sorted(result.feature_importances.items(), key=lambda kv: -kv[1])[:5]
        for name, importance in top:
            print(f"  {name}: {importance:.4f}")


if __name__ == "__main__":
    main()
