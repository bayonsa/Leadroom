from __future__ import annotations

import json
from pathlib import Path

from app.filters import is_good_business_url


def evaluate(path: Path = Path("benchmarks/filter_cases.json")) -> dict[str, float | int]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    true_positive = false_positive = true_negative = false_negative = 0
    for case in cases:
        actual = is_good_business_url(case["url"], case["title"])
        expected = bool(case["expected"])
        if actual and expected:
            true_positive += 1
        elif actual and not expected:
            false_positive += 1
        elif not actual and not expected:
            true_negative += 1
        else:
            false_negative += 1

    total = len(cases)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0
    accuracy = (true_positive + true_negative) / total if total else 0
    return {
        "cases": total,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "true_negative": true_negative,
        "false_negative": false_negative,
        "precision": round(precision, 4),
        "accuracy": round(accuracy, 4),
    }


def main() -> None:
    print(json.dumps(evaluate(), indent=2))


if __name__ == "__main__":
    main()
