from __future__ import annotations

from datetime import date


class TestSQLiteStorage:
    # --- Daily data ---

    def test_save_and_get(self, storage, sample_daily_bars):
        written = storage.save_daily_data(sample_daily_bars)
        assert written == 20

        result = storage.get_daily_data("000001")
        assert len(result) == 20
        assert result[0].close == 10.2

    def test_get_with_date_range(self, storage, sample_daily_bars):
        storage.save_daily_data(sample_daily_bars)
        result = storage.get_daily_data(
            "000001",
            start=date(2026, 1, 10),
            end=date(2026, 1, 15),
        )
        assert len(result) == 6

    def test_upsert_behavior(self, storage, sample_daily_bars):
        storage.save_daily_data(sample_daily_bars[:5])
        # Resave overlapping data
        storage.save_daily_data(sample_daily_bars[:10])
        result = storage.get_daily_data("000001")
        assert len(result) == 10

    def test_latest_date(self, storage, sample_daily_bars):
        storage.save_daily_data(sample_daily_bars)
        latest = storage.get_latest_date("000001")
        assert latest == date(2026, 1, 24)

    def test_latest_date_empty(self, storage):
        assert storage.get_latest_date("000001") is None

    # --- Indicators ---

    def test_save_and_get_indicators(self, storage, sample_indicators):
        written = storage.save_indicators(sample_indicators)
        assert written == 20

        result = storage.get_indicators("000001")
        assert len(result) == 20
        assert result[0].rsi_14 == 55.0

    # --- Merged query ---

    def test_get_merged_dataframe(self, storage, sample_daily_bars, sample_indicators):
        storage.save_daily_data(sample_daily_bars)
        storage.save_indicators(sample_indicators)

        df = storage.get_merged_dataframe("000001")
        assert len(df) == 20
        assert "close" in df.columns
        assert "rsi_14" in df.columns

    def test_save_empty(self, storage):
        assert storage.save_daily_data([]) == 0
        assert storage.save_indicators([]) == 0
