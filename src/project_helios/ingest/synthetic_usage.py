"""Synthetic daily usage/billing event generator.

Generates a fact table of daily usage + billing events referencing the
customerID keys from the Kaggle Telco Customer Churn dataset, at a scale
(millions of rows) the real ~7K-row Kaggle table can't demonstrate on its
own. Distributions are loosely calibrated (not fit) to plausible telco
usage patterns — this is a synthetic-scale stand-in for pipeline testing,
not a claim of real-world accuracy.

Usage:
    uv run python -m project_helios.ingest.synthetic_usage \
        --customers data/raw/telco_churn.csv --days 90 --out data/raw/usage_events.parquet
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

RNG_SEED = 42


@dataclass(frozen=True)
class GeneratorConfig:
    days: int
    seed: int = RNG_SEED


def _customer_base_rates(rng: np.random.Generator, n_customers: int) -> pd.DataFrame:
    """Per-customer latent usage/payment propensity, drawn once per customer."""
    return pd.DataFrame(
        {
            "customer_idx": np.arange(n_customers),
            "data_mb_mean": rng.gamma(shape=4.0, scale=350.0, size=n_customers),
            "voice_min_mean": rng.gamma(shape=3.0, scale=15.0, size=n_customers),
            "late_propensity": rng.beta(a=2.0, b=8.0, size=n_customers),
        }
    )


def generate_usage_events(customer_ids: pd.Series, config: GeneratorConfig) -> pd.DataFrame:
    """Generate one row per (customer, day) with usage + billing fields."""
    rng = np.random.default_rng(config.seed)
    n_customers = len(customer_ids)
    base = _customer_base_rates(rng, n_customers)

    dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=config.days, freq="D")
    idx = pd.MultiIndex.from_product(
        [base["customer_idx"], dates], names=["customer_idx", "event_date"]
    )
    events = pd.DataFrame(index=idx).reset_index()
    events = events.merge(base, on="customer_idx", how="left")

    n = len(events)
    events["data_usage_mb"] = rng.gamma(shape=4.0, scale=events["data_mb_mean"] / 4.0, size=n)
    events["voice_minutes"] = rng.gamma(shape=3.0, scale=events["voice_min_mean"] / 3.0, size=n)
    events["sms_count"] = rng.poisson(lam=5, size=n)

    # Billing event: ~1/30 days is a billing cycle event with a payment-timing outcome
    events["is_billing_event"] = rng.random(n) < (1.0 / 30.0)
    days_to_pay = rng.exponential(scale=1.0 + events["late_propensity"] * 20.0, size=n)
    events["days_to_pay"] = np.where(events["is_billing_event"], np.round(days_to_pay, 1), np.nan)

    events["customer_id"] = events["customer_idx"].map(dict(enumerate(customer_ids)))
    drop_cols = ["customer_idx", "data_mb_mean", "voice_min_mean", "late_propensity"]
    return events.drop(columns=drop_cols)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--customers", type=Path, required=True, help="CSV with a customerID column"
    )
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    customers = pd.read_csv(args.customers)
    customer_id_col = "customerID" if "customerID" in customers.columns else customers.columns[0]

    events = generate_usage_events(customers[customer_id_col], GeneratorConfig(days=args.days))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    events.to_parquet(args.out, index=False)
    n_customers = customers[customer_id_col].nunique()
    print(f"Wrote {len(events):,} rows ({args.days} days x {n_customers:,} customers)")
    print(f"  -> {args.out}")


if __name__ == "__main__":
    main()
