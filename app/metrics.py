from __future__ import annotations

from typing import Any


def build_quality_metrics(
    candidates: list[dict[str, Any]],
    raw_leads: list[dict[str, Any]],
    clean_leads: list[dict[str, Any]],
    failed_urls: list[dict[str, Any]],
) -> dict[str, float | int]:
    scraped_attempts = len(raw_leads) + len(failed_urls)
    clean_count = len(clean_leads)
    domains = [str(lead.get("domain", "")) for lead in clean_leads if lead.get("domain")]

    return {
        "candidate_count": len(candidates),
        "scraped_count": len(raw_leads),
        "clean_lead_count": clean_count,
        "failed_count": len(failed_urls),
        "clean_yield": _ratio(clean_count, scraped_attempts),
        "failure_rate": _ratio(len(failed_urls), scraped_attempts),
        "generic_email_coverage": _coverage(clean_leads, "generic_email"),
        "phone_coverage": _coverage(clean_leads, "phone"),
        "contact_page_coverage": _coverage(clean_leads, "contact_page"),
        "booking_page_coverage": _coverage(clean_leads, "booking_page"),
        "duplicate_rate": _ratio(len(domains) - len(set(domains)), len(domains)),
    }


def _coverage(leads: list[dict[str, Any]], field: str) -> float:
    present = sum(1 for lead in leads if lead.get(field))
    return _ratio(present, len(leads))


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0
