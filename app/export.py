from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from app.normalizer import LEAD_FIELDS


def save_run(output: dict[str, Any], output_dir: Path, run_name: str) -> tuple[Path, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / f"{run_name}_output.json"
    csv_path = output_dir / f"{run_name}_output.csv"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2, ensure_ascii=False)

    clean_leads = output.get("clean_leads") or []
    if clean_leads:
        df = pd.DataFrame(clean_leads)
        for field in LEAD_FIELDS:
            if field not in df.columns:
                df[field] = ""
        df = df[LEAD_FIELDS]
        df = df.map(_csv_cell)
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        return json_path, csv_path

    return json_path, None


def _csv_cell(value: Any) -> Any:
    if isinstance(value, list):
        value = "; ".join(str(item) for item in value)
    if isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=False)
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{value}"
    return value
