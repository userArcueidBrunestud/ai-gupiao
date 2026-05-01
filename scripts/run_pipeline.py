#!/usr/bin/env python
"""
CLI entry point for the A-share intelligent analysis pipeline.

Usage:
    python scripts/run_pipeline.py collect 000001 000002
    python scripts/run_pipeline.py analyze 000001
    python scripts/run_pipeline.py train 000001
    python scripts/run_pipeline.py predict 000001
    python scripts/run_pipeline.py full 000001
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from src.ai.features import FeatureEngineer
from src.ai.sklearn_predictor import SklearnPredictor
from src.analysis.analyzer import TechnicalAnalyzer
from src.data.akshare_fetcher import AkshareFetcher
from src.data.sqlite_storage import SQLiteStorage
from src.pipeline.orchestrator import PipelineOrchestrator
from src.utils.logger import setup_logging


def build_orchestrator() -> PipelineOrchestrator:
    """Wire up dependencies and return the orchestrator."""
    setup_logging()

    # Ensure directories exist
    settings.model_dir.mkdir(parents=True, exist_ok=True)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)

    fetcher = AkshareFetcher()
    storage = SQLiteStorage()
    analyzer = TechnicalAnalyzer()

    # Try to load an existing model, otherwise create a new one
    predictor = SklearnPredictor()

    feature_engineer = FeatureEngineer()

    return PipelineOrchestrator(fetcher, storage, analyzer, predictor, feature_engineer)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_pipeline.py <command> [codes...]")
        print("Commands: collect, analyze, train, predict, full")
        sys.exit(1)

    command = sys.argv[1]
    codes = sys.argv[2:] if len(sys.argv) > 2 else ["000001"]

    orch = build_orchestrator()

    if command == "collect":
        results = orch.collect_data(codes)
        print(f"Collected data: {results}")

    elif command == "analyze":
        results = orch.compute_indicators(codes)
        print(f"Indicators computed: {results}")

    elif command == "train":
        for code in codes:
            result = orch.train_model(code)
            print(f"Trained model for {code}: {result}")

    elif command == "predict":
        for code in codes:
            result = orch.predict(code)
            print(f"Prediction for {code}: {result.predicted_trend} (confidence={result.confidence:.2%})")

    elif command == "full":
        for code in codes:
            result = orch.run_full_pipeline(code)
            print(f"Full pipeline for {code}: {result.predicted_trend} (confidence={result.confidence:.2%})")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
