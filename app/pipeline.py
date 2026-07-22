from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from app.config import ScraperConfig
from app.database import RunRepository
from app.export import save_run
from app.metrics import build_quality_metrics
from app.models import RunSummary, ScrapeFailure
from app.normalizer import attach_search_metadata, clean_leads, unique_phones
from app.scoring import explain_score, score_lead
from app.scraper import scrape_business_site
from app.search import search_business_sites


def run_pipeline(
    config: ScraperConfig,
    cancel_check: Callable[[], bool] | None = None,
    resume_run_id: str | None = None,
) -> dict[str, Any]:
    repository = RunRepository(config.database_path)
    if resume_run_id:
        config = repository.load_config(resume_run_id)
        run_id = resume_run_id
        recovered = repository.recover_for_resume(run_id)
        sites = repository.list_candidates(run_id)
        raw_leads = repository.load_leads(run_id)
        print(f"Resuming run {run_id}: recovered {recovered} candidate(s)")
    else:
        run_id = repository.create_run(config)
        print(f"Run ID: {run_id}")
        print(f"Searching for: {config.niche} in {config.location}")
        prior_domains = repository.seen_domains(
            config.niche,
            config.location,
            exclude_run_id=run_id,
        )
        discovery: dict[str, Any] = {
            "mode": config.discovery_mode,
            "previous_market_domains": len(prior_domains),
        }
        sites = search_business_sites(
            config,
            excluded_domains=prior_domains if config.discovery_mode == "new_only" else set(),
            diagnostics=discovery,
        )
        repository.add_candidates(run_id, sites, discovery)
        sites = repository.list_candidates(run_id)
        raw_leads = []

    print(f"\nFound {len(sites)} candidate websites:\n")
    for index, site in enumerate(sites[: config.max_sites], start=1):
        print(f"{index}. {site['title']}")
        print(f"   {site['homepage']}")

    failed_urls = []

    selected_sites = [site for site in sites if site.get("status") in {"queued", "failed"}][
        : config.max_sites
    ]
    cancelled = False
    for index, site in enumerate(selected_sites, start=1):
        if cancel_check and cancel_check():
            cancelled = True
            print("\nRun cancelled before the next site.")
            break
        url = site["homepage"]
        candidate_id = repository.claim(run_id, site["domain"])
        if config.discovery_mode == "reuse" and config.reuse_existing_leads:
            cached_lead = repository.find_cached_lead(site["domain"], exclude_run_id=run_id)
            if cached_lead:
                raw_leads.append(cached_lead)
                repository.complete(candidate_id, cached_lead)
                print(f"Reused existing lead: {cached_lead.get('business_name') or url}")
                continue
        if _has_local_seed(site) and not url:
            lead = _lead_from_osm(site)
            raw_leads.append(lead)
            repository.complete(candidate_id, lead)
            print(f"Local lead {index}/{len(selected_sites)}: {lead['business_name']}")
            continue

        print(f"\nScraping {index}/{len(selected_sites)}: {url}")

        try:
            lead = scrape_business_site(
                url,
                config,
                progress_callback=lambda progress, claimed_id=candidate_id: repository.update_candidate_crawl(
                    claimed_id,
                    progress,
                ),
            )
            if _has_local_seed(site):
                _merge_osm_seed(lead, site)
            attach_search_metadata(lead, site)
            raw_leads.append(lead)
            repository.complete(candidate_id, lead)
            print(f"Done: {lead.get('business_name') or url}")
        except Exception as exc:
            failed_urls.append(
                ScrapeFailure(
                    url=url,
                    error=str(exc),
                    error_type=type(exc).__name__,
                ).model_dump()
            )
            repository.fail(candidate_id, str(exc))
            print(f"Failed: {url}")
            print(str(exc))

        time.sleep(config.delay_seconds)

    clean = clean_leads(raw_leads)
    quality_metrics = build_quality_metrics(sites, raw_leads, clean, failed_urls)
    summary = RunSummary(**quality_metrics, cancelled=cancelled).model_dump()
    summary.update(quality_metrics)
    output = {
        "niche": config.niche,
        "run_id": run_id,
        "location": config.location,
        "model": config.model,
        "raw_leads": raw_leads,
        "clean_leads": clean,
        "candidate_sites": sites,
        "failed_urls": failed_urls,
        "summary": summary,
    }

    try:
        json_path, csv_path = save_run(output, config.output_dir, config.run_name)
    except Exception:
        repository.finish_run(run_id, "failed")
        repository.engine.dispose()
        raise
    repository.finish_run(run_id, "cancelled" if cancelled else "completed")
    repository.engine.dispose()
    if csv_path:
        print(f"\nSaved {len(clean)} clean leads to {csv_path}")
    else:
        print("\nNo clean leads saved.")
    print(f"Saved raw output to {json_path}")
    return output


def _lead_from_osm(site: dict[str, Any]) -> dict[str, Any]:
    email = str(site.get("email") or "").strip().lower()
    phone = str(site.get("phone") or "").strip()
    source_url = str(site.get("osm_url") or "")
    lead: dict[str, Any] = {
        "is_valid_lead": bool(site.get("business_name")),
        "business_name": str(site.get("business_name") or site.get("title") or ""),
        "website": str(site.get("homepage") or ""),
        "city_or_area": str(site.get("city_or_area") or ""),
        "business_type": str(site.get("business_type") or ""),
        "services": [],
        "generic_email": email,
        "emails": [email] if email else [],
        "phone": phone,
        "phones": [phone] if phone else [],
        "contact_page": "",
        "booking_page": "",
        "instagram_or_social": "",
        "has_online_booking": False,
        "website_quality_note": "Imported from the local OpenStreetMap dataset.",
        "source_url": source_url,
        "search_title": str(site.get("title") or ""),
        "search_snippet": str(site.get("snippet") or ""),
        "domain": str(site.get("domain") or ""),
        "field_evidence": {
            key: {"value": lead_value(site, key), "source_url": source_url, "method": "osm-local"}
            for key in ("business_name", "generic_email", "phone", "city_or_area")
            if lead_value(site, key)
        },
        "enrichment_errors": [],
        "source": "osm_local",
        "source_id": str(site.get("source_id") or ""),
        "address": str(site.get("address") or ""),
        "latitude": str(site.get("latitude") or ""),
        "longitude": str(site.get("longitude") or ""),
    }
    lead["lead_score"] = score_lead(lead)
    lead["lead_reason"] = explain_score(lead)
    return lead


def _has_local_seed(site: dict[str, Any]) -> bool:
    return site.get("source") == "osm_local" or "local" in (site.get("sources") or [])


def _merge_osm_seed(lead: dict[str, Any], site: dict[str, Any]) -> None:
    mapping = {
        "business_name": "business_name",
        "city_or_area": "city_or_area",
        "business_type": "business_type",
        "generic_email": "email",
        "phone": "phone",
    }
    evidence = lead.setdefault("field_evidence", {})
    source_url = str(site.get("osm_url") or "")
    for target, source in mapping.items():
        value = str(site.get(source) or "").strip()
        if value and not lead.get(target):
            lead[target] = value
            evidence[target] = {"value": value, "source_url": source_url, "method": "osm-local"}
    emails = [value for value in [lead.get("generic_email"), site.get("email")] if value]
    phones = [value for value in [lead.get("phone"), site.get("phone")] if value]
    lead["emails"] = list(dict.fromkeys([*(lead.get("emails") or []), *emails]))[:3]
    lead["phones"] = unique_phones([*(lead.get("phones") or []), *phones])
    lead["phone"] = lead["phones"][0] if lead["phones"] else ""
    lead["source"] = "hybrid"
    lead["source_id"] = str(site.get("source_id") or "")
    lead["address"] = str(site.get("address") or "")
    lead["lead_score"] = score_lead(lead)
    lead["lead_reason"] = explain_score(lead)


def lead_value(site: dict[str, Any], key: str) -> Any:
    source_key = {"generic_email": "email"}.get(key, key)
    return site.get(source_key)
