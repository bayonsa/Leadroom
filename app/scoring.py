from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def score_lead(lead: Mapping[str, Any]) -> int:
    """Score observable lead evidence without trusting an LLM-provided number."""
    if not lead.get("is_valid_lead"):
        return 0

    score = 0
    score += 1 if has_verified_evidence(lead, "business_name") else 0
    score += 2 if has_verified_evidence(lead, "website") else 0
    score += 1 if has_verified_evidence(lead, "city_or_area") else 0
    score += 1 if bool(lead.get("services")) else 0
    score += 1 if has_verified_evidence(lead, "generic_email") else 0
    score += 1 if has_verified_evidence(lead, "phone") else 0
    score += 1 if has_verified_evidence(lead, "contact_page") else 0
    score += 1 if has_verified_evidence(lead, "instagram_or_social") else 0
    score += 1 if not lead.get("has_online_booking") else 0
    return min(10, score)


def explain_score(lead: Mapping[str, Any]) -> str:
    if not lead.get("is_valid_lead"):
        return "Rejected because the page could not be verified as an independent business website."

    strengths = []
    opportunities = []
    if lead.get("generic_email") or lead.get("phone"):
        strengths.append("public contact details")
    if lead.get("services"):
        strengths.append("clear service information")
    if lead.get("city_or_area"):
        strengths.append("target-location evidence")
    if lead.get("contact_page"):
        strengths.append("a direct contact page")
    if not lead.get("has_online_booking"):
        opportunities.append("no verified online booking flow")
    if not lead.get("generic_email"):
        opportunities.append("no verified generic email")

    strength_text = ", ".join(strengths) if strengths else "a direct business website"
    if opportunities:
        return f"Verified {strength_text}; opportunity signals include {', '.join(opportunities)}."
    return f"Verified {strength_text}."


def _present(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def has_verified_evidence(lead: Mapping[str, Any], field: str) -> bool:
    if not _present(lead.get(field)):
        return False
    evidence = lead.get("field_evidence")
    if not isinstance(evidence, Mapping):
        return False
    item = evidence.get(field)
    if not isinstance(item, Mapping):
        return False
    source_url = item.get("source_url") or item.get("url")
    evidence_value = item.get("value")
    if (
        evidence_value is None
        or str(evidence_value).strip().casefold() != str(lead.get(field)).strip().casefold()
    ):
        return False
    return _present(source_url) and item.get("method") not in {"llm", "manual", "unverified"}
