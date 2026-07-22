from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any


def extract_json_from_text(text: str) -> dict[str, Any] | list[Any] | None:
    if not text:
        return None

    candidate = text.strip()
    parsed = _try_json(candidate)
    if parsed is not None:
        return parsed

    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL | re.IGNORECASE)
    if fenced:
        parsed = _try_json(fenced.group(1).strip())
        if parsed is not None:
            return parsed

    for opener, closer in (("{", "}"), ("[", "]")):
        first = candidate.find(opener)
        last = candidate.rfind(closer)
        if first != -1 and last != -1 and last > first:
            parsed = _try_json(candidate[first : last + 1])
            if parsed is not None:
                return parsed

    return None


def parse_model_output(raw: Any) -> tuple[dict[str, Any] | list[Any] | None, str]:
    """Return parsed model data plus raw text for diagnostics."""
    if raw is None:
        return None, ""

    if isinstance(raw, Mapping):
        if "content" in raw:
            content = raw["content"]
            if isinstance(content, Mapping):
                return dict(content), json.dumps(content, ensure_ascii=False)
            if isinstance(content, list):
                return content, json.dumps(content, ensure_ascii=False)
            if isinstance(content, str):
                return extract_json_from_text(content), content

        return dict(raw), json.dumps(raw, ensure_ascii=False)

    if isinstance(raw, list):
        return raw, json.dumps(raw, ensure_ascii=False)

    if isinstance(raw, str):
        return extract_json_from_text(raw), raw

    text = str(raw)
    return extract_json_from_text(text), text


def _try_json(text: str) -> dict[str, Any] | list[Any] | None:
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    if isinstance(parsed, (dict, list)):
        return parsed
    return None
