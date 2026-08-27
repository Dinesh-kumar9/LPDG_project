"""
FastAPI application dependencies and configuration settings.
"""

from __future__ import annotations

import pathlib
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LPDG Gateway Prioritization API"
    app_version: str = "1.0.0"
    data_dir: pathlib.Path = pathlib.Path("../../OneDrive_1_8-30-2026/03-challenge-data/data")
    models_dir: pathlib.Path = pathlib.Path("models")
    reports_dir: pathlib.Path = pathlib.Path("../drift_reports")
    predictions_path: pathlib.Path = pathlib.Path("predictions.csv")

    model_config = SettingsConfigDict(env_prefix="LPDG_", env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
