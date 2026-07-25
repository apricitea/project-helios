import pandas as pd

from project_helios.ingest.synthetic_usage import GeneratorConfig, generate_usage_events


def _customer_ids(n: int) -> pd.Series:
    return pd.Series([f"CUST-{i:04d}" for i in range(n)])


def test_one_row_per_customer_per_day():
    n_customers, days = 10, 5
    events = generate_usage_events(_customer_ids(n_customers), GeneratorConfig(days=days))
    assert len(events) == n_customers * days


def test_days_to_pay_only_set_on_billing_events():
    events = generate_usage_events(_customer_ids(20), GeneratorConfig(days=30))
    assert (events["days_to_pay"].notna() == events["is_billing_event"]).all()


def test_deterministic_with_fixed_seed():
    ids = _customer_ids(5)
    a = generate_usage_events(ids, GeneratorConfig(days=10, seed=7))
    b = generate_usage_events(ids, GeneratorConfig(days=10, seed=7))
    pd.testing.assert_frame_equal(a, b)


def test_non_negative_usage_fields():
    events = generate_usage_events(_customer_ids(15), GeneratorConfig(days=20))
    assert (events["data_usage_mb"] >= 0).all()
    assert (events["voice_minutes"] >= 0).all()
    assert (events["sms_count"] >= 0).all()
