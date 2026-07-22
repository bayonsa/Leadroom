from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import ValidationError
from scrapegraphai.graphs import SmartScraperGraph

from app.config import ScraperConfig
from app.enrichment import HtmlFetcher, apply_enrichment, enrich_public_pages
from app.models import LeadExtraction
from app.normalizer import normalize_lead
from app.parser import parse_model_output

LEAD_PROMPT = """
Extract public B2B lead information from this small business website.

Return only valid JSON. Do not use markdown. Do not explain anything.

Use this exact structure:
{
  "is_valid_lead": true,
  "business_name": "",
  "website": "",
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
  "has_online_booking": false,
  "website_quality_note": ""
}

Rules:
- This must be a real individual business website. Freelancers, sole traders,
  studios, and personal brands offering paid services are valid businesses.
- Reject directories, marketplaces, booking platforms, review websites,
  large department stores, blog posts, and generic category pages.
- Use only public business information visible on the website.
- Prefer role addresses like info@, hello@, contact@, bookings@, studio@, or sales@.
- Also include a named address when the website publicly presents it as a business contact.
- Never guess a private address, and reject no-reply addresses or addresses from unrelated domains.
- Return up to three unique public business emails in emails and up to three public phone numbers in phones.
- Keep generic_email and phone equal to the first item in their matching list.
- Do not guess missing information.
- If a field is missing, keep it empty.
"""


def scrape_business_site(
    url: str,
    config: ScraperConfig,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    public_data, field_evidence, enrichment_errors = enrich_public_pages(
        url,
        config,
        progress_callback=progress_callback,
    )
    provider = config.model.split("/", 1)[0] if "/" in config.model else "ollama"
    llm_config: dict[str, Any] = {
        "model": config.model,
        "temperature": 0,
        "model_tokens": 8192,
    }
    if config.ollama_base_url:
        llm_config["base_url"] = config.ollama_base_url
    if provider == "ollama":
        llm_config["format"] = LeadExtraction.model_json_schema()
    elif config.llm_api_key:
        llm_config["api_key"] = config.llm_api_key
    graph_config = {
        "llm": llm_config,
        "verbose": False,
        "headless": True,
    }

    source_fetcher = HtmlFetcher(
        cache_dir=config.cache_dir,
        timeout_seconds=config.request_timeout_seconds,
        retry_attempts=config.retry_attempts,
        cache_ttl_hours=config.cache_ttl_hours,
        browser_fallback=config.browser_fallback,
    )
    try:
        guarded_html = source_fetcher.fetch(url).html
    finally:
        source_fetcher.close()
    graph = SmartScraperGraph(prompt=LEAD_PROMPT, source=guarded_html, config=graph_config)
    raw = graph.run()
    parsed, raw_text = parse_model_output(raw)
    if isinstance(parsed, dict):
        try:
            parsed = LeadExtraction.model_validate(parsed).model_dump(exclude_none=True)
        except ValidationError as exc:
            lead = normalize_lead(None, source_url=url)
            lead["raw_output"] = raw_text
            lead["validation_errors"] = exc.errors(include_url=False)
            return apply_enrichment(lead, public_data, field_evidence, enrichment_errors)
    lead = normalize_lead(parsed, source_url=url)
    if not parsed:
        lead["raw_output"] = raw_text
    return apply_enrichment(lead, public_data, field_evidence, enrichment_errors)
