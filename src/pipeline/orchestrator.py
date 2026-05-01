from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd
from loguru import logger

from config.settings import settings
from src.ai.base_predictor import BasePredictor
from src.ai.evaluation import evaluate_model
from src.ai.features import FeatureEngineer
from src.analysis.analyzer import TechnicalAnalyzer
from src.core.exceptions import PipelineError
from src.core.models.prediction import PredictionResult
from src.core.models.stock import StockDaily
from src.data.base_fetcher import BaseFetcher
from src.data.base_storage import BaseStorage


class PipelineOrchestrator:
    """Coordinates the full data → analysis → AI pipeline."""

    def __init__(
        self,
        fetcher: BaseFetcher,
        storage: BaseStorage,
        analyzer: TechnicalAnalyzer,
        predictor: BasePredictor,
        feature_engineer: FeatureEngineer,
    ) -> None:
        self._fetcher = fetcher
        self._storage = storage
        self._analyzer = analyzer
        self._predictor = predictor
        self._fe = feature_engineer

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    def collect_data(self, codes: list[str], incremental: bool = False) -> dict[str, int]:
        """Fetch and persist daily data for the given stock codes."""
        results: dict[str, int] = {}
        for code in codes:
            logger.info(f"Collecting data for {code}")
            start_date = settings.data_start_date
            end_date = date.today().isoformat()

            if incremental:
                latest = self._storage.get_latest_date(code)
                if latest:
                    start_date = latest.isoformat()
                else:
                    logger.info(f"No existing data for {code}, fetching from {start_date}")

            daily_list = self._fetcher.fetch_daily_data(code, start_date, end_date)
            written = self._storage.save_daily_data(daily_list)
            results[code] = written
            logger.info(f"{code}: saved {written} daily bars")
        return results

    def compute_indicators(self, codes: list[str]) -> dict[str, int]:
        """Compute technical indicators and persist them."""
        results: dict[str, int] = {}
        for code in codes:
            daily_list = self._storage.get_daily_data(code)
            if not daily_list:
                logger.warning(f"No daily data for {code}, skipping indicators")
                results[code] = 0
                continue
            df = self._daily_list_to_df(daily_list)
            df = self._analyzer.compute_all(df)
            indicator_list = self._analyzer.to_indicator_list(df)
            written = self._storage.save_indicators(indicator_list)
            results[code] = written
            logger.info(f"{code}: computed & saved {written} indicator rows")
        return results

    def train_model(self, code: str) -> dict:
        """Train a prediction model for a single stock."""
        df = self._storage.get_merged_dataframe(code)
        if len(df) < 60:
            raise PipelineError(f"Not enough data for {code} (need >= 60 rows)")

        X, y = self._fe.build_features(df)
        split = int(len(X) * settings.train_test_split)
        X_train, X_test = X.iloc[:split], X.iloc[split:]
        y_train, y_test = y.iloc[:split], y.iloc[split:]

        train_info = self._predictor.train(X_train, y_train)

        # Evaluate
        preds = self._predictor.predict(X_test)
        eval_result = evaluate_model(y_test, preds, FeatureEngineer.label_names())

        model_path = settings.model_dir / f"{code}_{date.today().isoformat()}.joblib"
        self._predictor.save(str(model_path))

        logger.info(
            f"Model for {code} — accuracy={eval_result['accuracy']:.4f}, saved to {model_path}"
        )
        return {**train_info, "evaluation": eval_result, "model_path": str(model_path)}

    def predict(self, code: str) -> PredictionResult:
        """Predict the future trend for a single stock."""
        df = self._storage.get_merged_dataframe(code)
        if len(df) < 60:
            raise PipelineError(f"Not enough data for {code} (need >= 60 rows)")

        X, _ = self._fe.build_features(df)
        latest_feature = X.iloc[-1:]

        # Predict confidence per class
        results = self._predictor.predict_with_confidence(latest_feature)
        best = results[0]

        return PredictionResult(
            code=code,
            predict_date=date.today(),
            predicted_trend=best["label"],
            confidence=best["confidence"],
            model_name=self._predictor.model_name,
            features_used=list(X.columns),
        )

    def run_full_pipeline(self, code: str) -> PredictionResult:
        """Execute the complete pipeline for one stock: collect → indicators → train → predict."""
        logger.info(f"Starting full pipeline for {code}")
        self.collect_data([code])
        self.compute_indicators([code])
        self.train_model(code)
        result = self.predict(code)
        logger.info(
            f"Pipeline complete — {code}: {result.predicted_trend} "
            f"(confidence={result.confidence:.2%})"
        )
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _daily_list_to_df(data: list[StockDaily]) -> pd.DataFrame:
        return pd.DataFrame([d.model_dump() for d in data])
