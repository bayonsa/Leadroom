from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    fix: str = ""


def ollama_model_name(model: str) -> str:
    return model.removeprefix("ollama/")


def check_python() -> CheckResult:
    version = ".".join(str(part) for part in sys.version_info[:3])
    ok = (3, 12) <= sys.version_info[:2] < (3, 14)
    return CheckResult("Python", ok, version, "Install Python 3.12 or 3.13.")


def check_output_dir(output_dir: Path) -> CheckResult:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output_dir, prefix=".write-check-", delete=True):
            pass
    except OSError as exc:
        return CheckResult("Output directory", False, str(exc), "Choose a writable output directory.")
    return CheckResult("Output directory", True, str(output_dir.resolve()))


def check_ollama(base_url: str, model: str, timeout: float = 4.0) -> list[CheckResult]:
    endpoint = f"{base_url.rstrip('/')}/api/tags"
    try:
        request = Request(endpoint, headers={"Accept": "application/json"})
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
        return [
            CheckResult(
                "Ollama service",
                False,
                str(exc),
                f"Start Ollama and verify OLLAMA_BASE_URL={base_url}.",
            ),
            CheckResult("Ollama model", False, ollama_model_name(model), "Check Ollama first."),
        ]

    installed = {
        str(item.get("name", "")).split("@", 1)[0]
        for item in payload.get("models", [])
        if isinstance(item, dict)
    }
    expected = ollama_model_name(model)
    aliases = {expected, expected.split(":", 1)[0]}
    found = any(name in aliases or name.split(":", 1)[0] in aliases for name in installed)
    return [
        CheckResult("Ollama service", True, base_url),
        CheckResult(
            "Ollama model",
            found,
            expected,
            f"Run: ollama pull {expected}",
        ),
    ]


def run_checks(output_dir: Path, base_url: str, model: str) -> list[CheckResult]:
    return [check_python(), check_output_dir(output_dir), *check_ollama(base_url, model)]


def parse_args() -> argparse.Namespace:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Check local lead scraper prerequisites")
    parser.add_argument("--output", default="data/exports")
    parser.add_argument("--model", default=os.getenv("DEFAULT_MODEL", "ollama/llama3.2:3b"))
    parser.add_argument("--ollama-url", default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = run_checks(Path(args.output), args.ollama_url, args.model)
    for result in results:
        marker = "PASS" if result.ok else "FAIL"
        print(f"[{marker}] {result.name}: {result.detail}")
        if not result.ok and result.fix:
            print(f"       Fix: {result.fix}")
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
