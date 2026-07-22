from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class CampaignBrief:
    base_message: str
    tone: str
    links: tuple[str, ...]
    sender_identity: str
    opt_out_address: str


def compose_outreach_message(
    lead: dict[str, Any],
    brief: CampaignBrief,
    runtime: dict[str, str],
    api_key: str = "",
    personalize: bool = True,
) -> tuple[str, str, dict[str, Any]]:
    business = str(lead.get("business_name") or lead.get("domain") or "the business").strip()
    fallback_subject = f"A note for {business}"[:200]
    area = str(lead.get("city_or_area") or "your area")
    service = str(next(iter(lead.get("services") or []), "your services"))
    fallback_body = (
        f"Hello {business} team,\n\n"
        f"I found your public business website while researching {service} providers in {area}. "
        f"{_render_template(brief.base_message, lead)}"
    )
    metadata: dict[str, Any] = {"personalized_by": "template", "model": ""}

    try:
        if not personalize:
            raise ValueError("AI personalization was not requested")
        generated = _generate(lead, brief, runtime, api_key)
        if set(generated) != {"subject", "body"}:
            raise ValueError("The model returned fields outside the outreach schema")
        if not all(isinstance(generated.get(field), str) for field in ("subject", "body")):
            raise ValueError("The model returned non-text outreach fields")
        subject = _safe_subject(str(generated.get("subject") or fallback_subject))
        body = str(generated.get("body") or fallback_body).strip()
        if len(body) < 20 or len(body) > 2000:
            raise ValueError("The model returned an incomplete message")
        if re.search(r"https?://|www\.", body, flags=re.IGNORECASE):
            raise ValueError("The model added an unapproved link")
        metadata = {"personalized_by": "ai", "model": runtime.get("model_name", "")}
    except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
        subject = fallback_subject
        body = fallback_body
        if personalize:
            metadata["fallback_reason"] = str(exc)[:500]

    footer: list[str] = []
    if brief.links:
        footer.extend(["Links:", *brief.links])
    footer.extend(
        [
            f"Regards,\n{brief.sender_identity.strip()}",
            f"To opt out of future contact, reply to this email or email {brief.opt_out_address.strip()}.",
        ]
    )
    return subject, f"{body.strip()}\n\n" + "\n\n".join(footer), metadata


def _generate(
    lead: dict[str, Any],
    brief: CampaignBrief,
    runtime: dict[str, str],
    api_key: str,
) -> dict[str, Any]:
    prompt = _prompt(lead, brief)
    endpoint = runtime["model_endpoint"].rstrip("/")
    model_name = runtime["model_name"]
    provider = runtime.get("model_provider", "ollama")
    timeout = httpx.Timeout(45, connect=8)

    if provider == "ollama":
        response = httpx.post(
            f"{endpoint}/api/chat",
            json={
                "model": model_name,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.2},
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=timeout,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
    else:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        response = httpx.post(
            f"{endpoint}/chat/completions",
            headers=headers,
            json={
                "model": model_name,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=timeout,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    return json.loads(_json_text(str(content)))


def _prompt(lead: dict[str, Any], brief: CampaignBrief) -> str:
    safe_lead = {
        "business_name": lead.get("business_name"),
        "business_type": lead.get("business_type"),
        "city_or_area": lead.get("city_or_area"),
        "services": (lead.get("services") or [])[:8],
        "website": lead.get("website"),
        "website_quality_note": lead.get("website_quality_note"),
    }
    return (
        "Write a short, truthful B2B outreach email using only the supplied evidence. "
        "Do not invent achievements, problems, people, or facts. Do not add a signature, links, "
        "tracking language, or an unsubscribe line; the application adds those. "
        "Return strict JSON with exactly two string fields: subject and body.\n\n"
        f"Tone: {brief.tone}\n"
        f"Base message: {brief.base_message}\n"
        f"Lead evidence: {json.dumps(safe_lead, ensure_ascii=False)}"
    )


def _render_template(template: str, lead: dict[str, Any]) -> str:
    values = {
        "business_name": str(lead.get("business_name") or lead.get("domain") or "your team"),
        "business_type": str(lead.get("business_type") or "business"),
        "location": str(lead.get("city_or_area") or "your area"),
        "service": str(next(iter(lead.get("services") or []), "your services")),
        "website": str(lead.get("website") or ""),
    }
    rendered = template.strip()
    for key, value in values.items():
        rendered = rendered.replace(f"{{{key}}}", value)
    return rendered


def _safe_subject(value: str) -> str:
    return re.sub(r"[\r\n]+", " ", value).strip()[:200]


def _json_text(value: str) -> str:
    value = value.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.IGNORECASE)
    match = re.search(r"\{.*\}", value, flags=re.DOTALL)
    if not match:
        raise ValueError("The model did not return JSON")
    return match.group(0)
