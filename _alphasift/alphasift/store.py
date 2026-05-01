# -*- coding: utf-8 -*-
"""Persistence helpers for screen runs and evaluations."""

from __future__ import annotations

import json
from dataclasses import asdict, fields
from pathlib import Path

from alphasift.models import EvaluationResult, Pick, PickEvaluation, ScreenResult


def save_screen_result(
    result: ScreenResult,
    *,
    data_dir: Path,
    path: str | Path | None = None,
    jsonl: bool = False,
) -> Path:
    """Persist a screen result and return the written path."""
    output_path = Path(path) if path is not None else data_dir / "runs" / f"{result.run_id}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.saved_path = str(output_path)
    if jsonl:
        output_path.write_text("\n".join(screen_result_to_jsonl(result)) + "\n", encoding="utf-8")
    else:
        output_path.write_text(
            json.dumps(asdict(result), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return output_path


def load_screen_result(run_ref: str | Path, *, data_dir: Path) -> ScreenResult:
    """Load a saved screen result by run_id or path."""
    path = resolve_run_path(run_ref, data_dir=data_dir)
    data = json.loads(path.read_text(encoding="utf-8"))
    pick_items = data.get("picks", [])
    pick_fields = {field.name for field in fields(Pick)}
    result_fields = {field.name for field in fields(ScreenResult)}
    data["picks"] = [
        Pick(**{key: value for key, value in item.items() if key in pick_fields})
        for item in pick_items
        if isinstance(item, dict)
    ]
    filtered = {key: value for key, value in data.items() if key in result_fields}
    loaded = ScreenResult(**filtered)
    loaded.saved_path = str(path)
    return loaded


def save_evaluation_result(
    result: EvaluationResult,
    *,
    data_dir: Path,
    path: str | Path | None = None,
    jsonl: bool = False,
) -> Path:
    output_path = Path(path) if path is not None else data_dir / "evaluations" / f"{result.run_id}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.saved_path = str(output_path)
    if jsonl:
        output_path.write_text("\n".join(evaluation_result_to_jsonl(result)) + "\n", encoding="utf-8")
    else:
        output_path.write_text(
            json.dumps(asdict(result), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return output_path


def list_saved_runs(*, data_dir: Path, limit: int = 20) -> list[dict[str, object]]:
    runs_dir = data_dir / "runs"
    if not runs_dir.is_dir():
        return []
    items = []
    for path in sorted(runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        items.append({
            "run_id": data.get("run_id", path.stem),
            "strategy": data.get("strategy", ""),
            "market": data.get("market", ""),
            "created_at": data.get("created_at", ""),
            "picks": len(data.get("picks", []) or []),
            "path": str(path),
        })
        if len(items) >= limit:
            break
    return items


def resolve_run_path(run_ref: str | Path, *, data_dir: Path) -> Path:
    path = Path(run_ref)
    if path.is_file():
        return path
    candidate = data_dir / "runs" / f"{run_ref}.json"
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(f"Saved run not found: {run_ref}")


def screen_result_to_jsonl(result: ScreenResult) -> list[str]:
    data = asdict(result)
    picks = data.pop("picks", [])
    lines = [json.dumps({"type": "run", **data}, ensure_ascii=False)]
    for pick in picks:
        lines.append(json.dumps({"type": "pick", "run_id": result.run_id, **pick}, ensure_ascii=False))
    return lines


def evaluation_result_to_jsonl(result: EvaluationResult) -> list[str]:
    data = asdict(result)
    picks = data.pop("picks", [])
    lines = [json.dumps({"type": "evaluation", **data}, ensure_ascii=False)]
    for pick in picks:
        lines.append(json.dumps({"type": "pick_evaluation", "run_id": result.run_id, **pick}, ensure_ascii=False))
    return lines


def evaluation_from_dict(data: dict) -> EvaluationResult:
    pick_fields = {field.name for field in fields(PickEvaluation)}
    result_fields = {field.name for field in fields(EvaluationResult)}
    data = dict(data)
    data["picks"] = [
        PickEvaluation(**{key: value for key, value in item.items() if key in pick_fields})
        for item in data.get("picks", [])
        if isinstance(item, dict)
    ]
    return EvaluationResult(**{key: value for key, value in data.items() if key in result_fields})
