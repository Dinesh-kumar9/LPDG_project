"""
Unit tests for determinism of predictions.
"""

from __future__ import annotations

import hashlib
import pathlib

from src.load import load_telemetry
from src.predict import predict
from src.train import write_model_artifact


def test_prediction_determinism(
    real_data_dir: pathlib.Path, temp_models_dir: pathlib.Path, tmp_path: pathlib.Path
):
    # 1. Train and promote v1
    telemetry = load_telemetry(real_data_dir)
    write_model_artifact(
        telemetry=telemetry,
        models_dir=temp_models_dir,
        version_name="v1_test",
        promote=True,
    )

    out1 = tmp_path / "pred1.csv"
    out2 = tmp_path / "pred2.csv"

    # 2. Run predict twice
    predict(data_dir=real_data_dir, out_path=out1, models_dir=temp_models_dir)
    predict(data_dir=real_data_dir, out_path=out2, models_dir=temp_models_dir)

    # 3. Assert file bytes and SHA-256 hashes are 100% identical
    hash1 = hashlib.sha256(out1.read_bytes()).hexdigest()
    hash2 = hashlib.sha256(out2.read_bytes()).hexdigest()
    assert hash1 == hash2

    # 4. Check contents: exactly 120 rows (8 weeks x 15 gateways)
    import pandas as pd

    df1 = pd.read_csv(out1)
    assert len(df1) == 120
    assert list(df1.columns) == ["week_start", "rank", "gateway_id", "score", "reason"]
    assert df1["week_start"].nunique() == 8
    for _, week_df in df1.groupby("week_start"):
        assert list(week_df["rank"]) == list(range(1, 16))
        assert week_df["gateway_id"].nunique() == 15
