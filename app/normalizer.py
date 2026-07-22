from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import unquote, urljoin

from app.filters import domain_key, homepage_url
from app.models import Lead
from app.scoring import explain_score, has_verified_evidence, score_lead

EMAIL_RE = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)
FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "hotmail.com",
    "icloud.com",
    "outlook.com",
    "yahoo.com",
}
PREFERRED_EMAIL_LOCALS = (
    "info",
    "hello",
    "contact",
    "enquiries",
    "enquiry",
    "bookings",
    "booking",
    "sales",
    "studio",
    "office",
    "team",
    "production",
    "producer",
    "work",
    "admin",
)
REJECTED_EMAIL_LOCALS = {
    "noreply",
    "no-reply",
    "do-not-reply",
    "donotreply",
    "mailer-daemon",
    "postmaster",
}
MISSING_TEXT = {"na", "n/a", "none", "null", "not found", "not available", "unknown", "-"}

LEAD_FIELDS = [
    "is_valid_lead",
    "business_name",
    "website",
    "city_or_area",
    "business_type",
    "services",
    "generic_email",
    "emails",
    "phone",
    "phones",
    "contact_page",
    "booking_page",
    "instagram_or_social",
    "has_online_booking",
    "website_quality_note",
    "lead_score",
    "lead_reason",
    "source_url",
    "search_title",
    "search_snippet",
    "domain",
    "field_evidence",
    "enrichment_errors",
]

BAD_NAMES = {
    "",
    "na",
    "n/a",
    "none",
    "beauty salons",
    "hair salons",
    "hair and beauty salons",
}


def empty_lead(source_url: str = "", reason: str = "") -> dict[str, Any]:
    return {
        "is_valid_lead": False,
        "business_name": "",
        "website": homepage_url(source_url) if source_url else "",
        "city_or_area": "",
        "business_type": "",
        "services": [],
        "generic_email": "",
        "emails": [],
        "phone": "",
        "phones": [],
        "contact_page": "",
        "booking_page": "",
        "instagram_or_social": "",
        "has_online_booking": False,
        "website_quality_note": "",
        "lead_score": 0,
        "lead_reason": reason,
        "source_url": source_url,
        "search_title": "",
        "search_snippet": "",
        "domain": domain_key(source_url) if source_url else "",
        "field_evidence": {},
        "enrichment_errors": [],
    }


def normalize_lead(data: Any, source_url: str = "") -> dict[str, Any]:
    if isinstance(data, list):
        data = _first_mapping(data)

    if not isinstance(data, Mapping):
        return empty_lead(source_url, "Could not parse model output.")

    lead = empty_lead(source_url)
    source_homepage = homepage_url(source_url) if source_url else ""

    lead["business_name"] = _first_text(
        data,
        "business_name",
        "name",
        "title",
        "legalName",
        "alternateName",
    )
    lead["website"] = _first_text(data, "website", "url", "sameAs") or source_homepage
    if isinstance(data.get("sameAs"), list):
        lead["instagram_or_social"] = _first_social(data["sameAs"])

    lead["city_or_area"] = _city_or_area(data)
    lead["business_type"] = _first_text(data, "business_type", "@type", "type")
    lead["services"] = _services(data.get("services") or data.get("service") or data.get("offers"))
    lead["emails"] = _emails(data, source_homepage)
    lead["generic_email"] = lead["emails"][0] if lead["emails"] else ""
    lead["phones"] = _phones(data)
    lead["phone"] = lead["phones"][0] if lead["phones"] else ""
    lead["contact_page"] = _absolute_url(_first_text(data, "contact_page", "contactPage"), source_homepage)
    lead["booking_page"] = _absolute_url(_first_text(data, "booking_page", "bookingPage"), source_homepage)
    lead["instagram_or_social"] = lead["instagram_or_social"] or _social_from_mapping(data)
    lead["has_online_booking"] = _boolish(data.get("has_online_booking")) or bool(lead["booking_page"])
    lead["website_quality_note"] = _first_text(data, "website_quality_note", "description")
    if "is_valid_lead" in data:
        lead["is_valid_lead"] = _boolish(data.get("is_valid_lead"))
    else:
        lead["is_valid_lead"] = _looks_like_business(lead)

    # Prefer the searched business domain if the model drifted to a booking or product domain.
    if source_homepage and domain_key(lead["website"]) != domain_key(source_homepage):
        lead["website"] = source_homepage

    lead["domain"] = domain_key(lead["website"] or source_url)
    lead["lead_score"] = score_lead(lead)
    lead["lead_reason"] = explain_score(lead)
    return Lead.model_validate(lead).model_dump()


def attach_search_metadata(lead: dict[str, Any], site: Mapping[str, Any]) -> dict[str, Any]:
    lead["source_url"] = str(site.get("url", ""))
    lead["search_title"] = str(site.get("title", ""))
    lead["search_snippet"] = str(site.get("snippet", ""))
    lead["domain"] = str(site.get("domain", "")) or domain_key(lead.get("website", ""))
    return lead


def clean_leads(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    seen = set()

    for lead in leads:
        name = str(lead.get("business_name", "")).strip()
        website = str(lead.get("website", "")).strip()
        source_url = str(lead.get("source_url", "")).strip()
        key = str(lead.get("domain", "")).strip() or domain_key(website or source_url)

        if name.lower() in BAD_NAMES:
            continue
        if not key:
            continue
        lead = promote_verified_business(lead)
        if lead.get("is_valid_lead") is False or not is_contactable_lead(lead):
            continue
        if key in seen:
            continue

        lead["lead_score"] = score_lead(lead)
        lead["lead_reason"] = explain_score(lead)
        cleaned.append({field: lead.get(field, "") for field in LEAD_FIELDS})
        seen.add(key)

    return sorted(cleaned, key=lambda item: int(item.get("lead_score") or 0), reverse=True)


def _first_mapping(items: list[Any]) -> Mapping[str, Any] | None:
    for item in items:
        if isinstance(item, Mapping):
            return item
    return None


def _first_text(data: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip().casefold() not in MISSING_TEXT:
            return value.strip()
        if (
            isinstance(value, list)
            and value
            and isinstance(value[0], str)
            and value[0].strip().casefold() not in MISSING_TEXT
        ):
            return value[0].strip()
    return ""


def _city_or_area(data: Mapping[str, Any]) -> str:
    value = data.get("city_or_area")
    if isinstance(value, str):
        return value.strip()
    address = data.get("address")
    if isinstance(address, Mapping):
        return _first_text(address, "addressLocality", "addressRegion", "addressCountry")
    if isinstance(address, str):
        return address.strip()
    return ""


def _services(value: Any) -> list[str]:
    results: list[str] = []

    def walk(item: Any) -> None:
        if isinstance(item, str) and item.strip():
            results.append(item.strip())
        elif isinstance(item, Mapping):
            for key, child in item.items():
                if key in {"name", "title", "service"} and isinstance(child, str):
                    results.append(child.strip())
                else:
                    walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    deduped = []
    seen = set()
    for service in results:
        key = service.lower()
        if key not in seen:
            deduped.append(service)
            seen.add(key)
    return deduped[:12]


def _emails(data: Mapping[str, Any], source_url: str = "") -> list[str]:
    values: list[str] = []
    direct = data.get("emails")
    if isinstance(direct, list):
        values.extend(str(item) for item in direct)
    values.extend([_first_text(data, "generic_email"), _first_text(data, "email")])
    values.extend(re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", json.dumps(data), re.I))
    cleaned = [email for value in values if (email := public_business_email(value, source_url))]
    return _unique_contacts(sorted(cleaned, key=email_priority), limit=3)


def _phones(data: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    direct = data.get("phones")
    if isinstance(direct, list):
        values.extend(str(item) for item in direct)
    values.extend([_first_text(data, "phone"), _first_text(data, "telephone")])
    return unique_phones(values)


def normalize_phone(value: Any) -> str:
    raw = unquote(str(value or "")).strip()
    if raw.lower().startswith("tel:"):
        raw = raw[4:]
    raw = raw.replace("\u00a0", " ").replace("\u2009", " ")
    raw = re.sub(r"(?i)(?:ext\.?|extension|x)\s*\d+.*$", "", raw).strip()
    raw = re.sub(r"[^\d+().\s-]", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" .-")
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    digits = re.sub(r"\D", "", raw)
    return raw if 7 <= len(digits) <= 15 else ""


def phone_identity(value: Any) -> str:
    """Return a comparison key that treats UK national and +44 forms as equal."""
    normalized = normalize_phone(value)
    digits = re.sub(r"\D", "", normalized)
    if not digits:
        return ""
    if digits.startswith("44") and len(digits) >= 11:
        national = digits[2:].lstrip("0")
        return f"44{national}"
    if digits.startswith("0") and 10 <= len(digits) <= 11:
        return f"44{digits[1:]}"
    return digits


def unique_phones(values: Any, limit: int = 3) -> list[str]:
    return _unique_contacts((normalize_phone(value) for value in values), limit=limit, phone=True)


def _unique_contacts(values: Any, limit: int, phone: bool = False) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        key = phone_identity(value) if phone else value.casefold()
        if key and key not in seen:
            seen.add(key)
            results.append(value)
        if len(results) == limit:
            break
    return results


def public_business_email(value: Any, source_url: str = "") -> str:
    email = str(value or "").strip().lower().removeprefix("mailto:").split("?", 1)[0]
    email = email.strip(" <>[](){}.,;:\"'")
    if not EMAIL_RE.fullmatch(email):
        return ""
    local, email_domain = email.rsplit("@", 1)
    if local in REJECTED_EMAIL_LOCALS:
        return ""
    source_domain = domain_key(source_url)
    if (
        source_domain
        and email_domain not in FREE_EMAIL_DOMAINS
        and domain_key(f"https://{email_domain}") != source_domain
    ):
        return ""
    return email


def email_priority(email: str) -> tuple[int, str]:
    local = email.split("@", 1)[0]
    try:
        return PREFERRED_EMAIL_LOCALS.index(local), email
    except ValueError:
        return len(PREFERRED_EMAIL_LOCALS), email


def is_contactable_lead(lead: Mapping[str, Any]) -> bool:
    return bool(lead.get("generic_email") or lead.get("phone") or lead.get("emails") or lead.get("phones"))


def promote_verified_business(lead: dict[str, Any]) -> dict[str, Any]:
    if lead.get("is_valid_lead") is not False:
        return lead
    verified_contact = has_verified_evidence(lead, "generic_email") or has_verified_evidence(lead, "phone")
    if verified_contact and has_verified_evidence(lead, "business_name"):
        promoted = dict(lead)
        promoted["is_valid_lead"] = True
        promoted["lead_score"] = score_lead(promoted)
        promoted["lead_reason"] = explain_score(promoted)
        return promoted
    return lead


def _social_from_mapping(data: Mapping[str, Any]) -> str:
    for key in ("instagram_or_social", "instagram", "facebook", "twitter", "linkedin"):
        value = data.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    for value in data.values():
        if isinstance(value, Mapping):
            social = _social_from_mapping(value)
            if social:
                return social
    return ""


def _first_social(values: list[Any]) -> str:
    for value in values:
        if isinstance(value, str) and ("instagram." in value or "facebook." in value):
            return value
    for value in values:
        if isinstance(value, str) and value.startswith("http"):
            return value
    return ""


def _score(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    if isinstance(value, (int, float)):
        return value == 1
    return False


def _looks_like_business(lead: Mapping[str, Any]) -> bool:
    name = str(lead.get("business_name", "")).strip().lower()
    if name in BAD_NAMES:
        return False
    return bool(name and lead.get("website"))


def _absolute_url(value: str, base_url: str) -> str:
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    if base_url:
        return urljoin(base_url, value)
    return value
