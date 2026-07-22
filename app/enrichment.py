from __future__ import annotations

import gzip
import hashlib
import ipaddress
import json
import os
import re
import socket
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from app.config import ScraperConfig
from app.filters import domain_key, homepage_url
from app.normalizer import (
    email_priority,
    normalize_phone,
    promote_verified_business,
    public_business_email,
    unique_phones,
)
from app.scoring import explain_score, score_lead

BUSINESS_JSON_LD_TYPES = {
    "Organization",
    "Corporation",
    "LocalBusiness",
    "ProfessionalService",
    "Store",
    "MedicalBusiness",
    "Dentist",
    "BeautySalon",
    "HairSalon",
    "HealthAndBeautyBusiness",
    "HomeAndConstructionBusiness",
    "LegalService",
    "FinancialService",
    "RealEstateAgent",
}
LINK_WEIGHTS = {
    "contact": 10,
    "contact-us": 10,
    "get-in-touch": 9,
    "locations": 7,
    "location": 7,
    "book": 6,
    "booking": 6,
    "about": 4,
    "team": 4,
    "people": 4,
    "staff": 4,
    "studio": 3,
    "services": 2,
    "service": 2,
}
SKIP_PATH_MARKERS = (
    "/privacy",
    "/terms",
    "/cookies",
    "/legal",
    "/careers",
    "/jobs",
    "/blog/",
    "/news/",
    "/tag/",
    "/category/",
    "/author/",
    "/cart",
    "/checkout",
)
SKIP_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".css",
    ".js",
    ".zip",
    ".mp4",
    ".mp3",
    ".woff",
    ".woff2",
    ".ttf",
)
UK_PHONE_RE = re.compile(r"(?<!\d)(?:(?:\+44\s?(?:\(0\)\s?)?)|0)(?:\d[\s().-]?){9,10}(?!\d)")
OBFUSCATED_EMAIL_RE = re.compile(
    r"\b([A-Z0-9._%+-]+)\s*(?:\[at\]|\(at\)|\sat\s)\s*"
    r"([A-Z0-9.-]+)\s*(?:\[dot\]|\(dot\)|\sdot\s)\s*([A-Z]{2,})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FetchResult:
    url: str
    html: str
    from_cache: bool
    method: str


class HtmlFetcher:
    def __init__(
        self,
        cache_dir: Path,
        timeout_seconds: float,
        retry_attempts: int,
        cache_ttl_hours: int,
        browser_fallback: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = retry_attempts
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.browser_fallback = browser_fallback
        self.client = httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
            transport=transport,
            headers={"User-Agent": "LocalLeadResearch/0.1 (+public-business-research)"},
        )

    def fetch(self, url: str) -> FetchResult:
        _assert_public_url(url)
        cached = self._read_cache(url)
        if cached:
            return FetchResult(
                url=cached["url"],
                html=cached["html"],
                from_cache=True,
                method=cached.get("method", "cache"),
            )

        last_error: Exception | None = None
        for attempt in range(self.retry_attempts + 1):
            try:
                request_url = url
                for _redirect in range(6):
                    _assert_public_url(request_url)
                    response = self.client.get(request_url)
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("Redirect response did not include a destination")
                        request_url = urljoin(request_url, location)
                        continue
                    break
                else:
                    raise ValueError("Website exceeded the redirect safety limit")
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Server returned {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                _assert_public_url(str(response.url))
                content_type = response.headers.get("content-type", "")
                if "html" not in content_type.lower():
                    raise ValueError(f"Expected HTML but received {content_type or 'unknown content type'}")
                if len(response.content) > 5_000_000:
                    raise ValueError("HTML response exceeded the 5 MB safety limit")
                self._write_cache(url, str(response.url), response.text, "http")
                return FetchResult(url=str(response.url), html=response.text, from_cache=False, method="http")
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                retryable = not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code >= 500
                if attempt >= self.retry_attempts or not retryable:
                    if self.browser_fallback and not isinstance(exc, httpx.HTTPStatusError):
                        return self._fetch_with_browser(url)
                    raise
                time.sleep(0.25 * (2**attempt))
        raise RuntimeError(str(last_error) if last_error else "Fetch failed")

    def fetch_text(self, url: str) -> FetchResult:
        _assert_public_url(url)
        cached = self._read_cache(url)
        if cached:
            return FetchResult(
                url=cached["url"],
                html=cached["html"],
                from_cache=True,
                method=cached.get("method", "cache"),
            )
        last_error: Exception | None = None
        for attempt in range(self.retry_attempts + 1):
            try:
                request_url = url
                for _redirect in range(6):
                    _assert_public_url(request_url)
                    response = self.client.get(request_url)
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("Redirect response did not include a destination")
                        request_url = urljoin(request_url, location)
                        continue
                    break
                else:
                    raise ValueError("Document exceeded the redirect safety limit")
                response.raise_for_status()
                _assert_public_url(str(response.url))
                if len(response.content) > 5_000_000:
                    raise ValueError("Document exceeded the 5 MB safety limit")
                content = response.content
                if content.startswith(b"\x1f\x8b"):
                    content = gzip.decompress(content)
                    if len(content) > 5_000_000:
                        raise ValueError("Expanded document exceeded the 5 MB safety limit")
                text = content.decode(response.encoding or "utf-8", errors="replace")
                self._write_cache(url, str(response.url), text, "http-document")
                return FetchResult(str(response.url), text, False, "http-document")
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                retryable = not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code >= 500
                if attempt >= self.retry_attempts or not retryable:
                    raise
                time.sleep(0.25 * (2**attempt))
        raise RuntimeError(str(last_error) if last_error else "Document fetch failed")

    def close(self) -> None:
        self.client.close()

    def _fetch_with_browser(self, url: str) -> FetchResult:
        try:
            with sync_playwright() as playwright:
                launch_options: dict[str, Any] = {"headless": True}
                browser_channel = os.getenv(
                    "LEADROOM_BROWSER_CHANNEL",
                    "msedge" if sys.platform == "win32" else "",
                ).strip()
                if browser_channel:
                    launch_options["channel"] = browser_channel
                browser = playwright.chromium.launch(**launch_options)
                context = browser.new_context(
                    ignore_https_errors=True,
                    user_agent="LocalLeadResearch/0.1 (+public-business-research)",
                )

                def guard_request(route) -> None:
                    try:
                        _assert_public_url(route.request.url)
                    except ValueError:
                        route.abort()
                    else:
                        route.continue_()

                context.route("**/*", guard_request)
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=int(self.timeout_seconds * 1000))
                html = page.content()
                final_url = page.url
                _assert_public_url(final_url)
                browser.close()
        except PlaywrightError as exc:
            raise httpx.TransportError(f"Browser fallback failed: {exc}") from exc
        self._write_cache(url, final_url, html, "browser-fallback")
        return FetchResult(url=final_url, html=html, from_cache=False, method="browser-fallback")

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def _read_cache(self, url: str) -> dict[str, str] | None:
        path = self._cache_path(url)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(payload["fetched_at"])
            if datetime.now(UTC) - fetched_at > self.cache_ttl:
                return None
            return payload
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return None

    def _write_cache(self, requested_url: str, final_url: str, html: str, method: str) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._cache_path(requested_url)
        temp_path = path.with_suffix(".tmp")
        payload = {
            "fetched_at": datetime.now(UTC).isoformat(),
            "url": final_url,
            "html": html,
            "method": method,
        }
        temp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(path)


def _assert_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public HTTP(S) URLs can be fetched")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
    except socket.gaierror as exc:
        raise ValueError(f"Website hostname could not be resolved: {parsed.hostname}") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("Private, loopback, and link-local destinations are blocked")


def discover_relevant_links(
    html: str,
    base_url: str,
    limit: int = 3,
    include_general: bool = False,
) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    base_domain = domain_key(base_url)
    scored: dict[str, int] = {}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        if urlparse(absolute).scheme not in {"http", "https"} or domain_key(absolute) != base_domain:
            continue
        haystack = f"{urlparse(absolute).path} {anchor.get_text(' ', strip=True)}".lower()
        parsed = urlparse(absolute)
        path = parsed.path.lower().rstrip("/") or "/"
        if any(marker in path for marker in SKIP_PATH_MARKERS) or path.endswith(SKIP_EXTENSIONS):
            continue
        score = max((weight for word, weight in LINK_WEIGHTS.items() if word in haystack), default=0)
        if include_general and not score and path != "/":
            score = 1
        if score:
            clean_url = absolute.split("#", 1)[0]
            scored[clean_url] = max(score, scored.get(clean_url, 0))
    return [url for url, _ in sorted(scored.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def discover_sitemap_links(
    fetcher: HtmlFetcher,
    base_url: str,
    limit: int,
    include_general: bool = False,
) -> list[str]:
    home = homepage_url(base_url)
    if not home:
        return []
    root = home.rstrip("/")
    sitemap_queue = [f"{root}/sitemap.xml"]
    try:
        robots = fetcher.fetch_text(f"{root}/robots.txt")
        for line in robots.html.splitlines():
            if line.lower().startswith("sitemap:"):
                sitemap_queue.append(line.split(":", 1)[1].strip())
    except (OSError, ValueError, httpx.HTTPError):
        pass
    documents_seen: set[str] = set()
    scored: dict[str, int] = {}
    while sitemap_queue and len(documents_seen) < 4 and len(scored) < limit * 4:
        sitemap_url = sitemap_queue.pop(0)
        if sitemap_url in documents_seen:
            continue
        documents_seen.add(sitemap_url)
        try:
            document = fetcher.fetch_text(sitemap_url)
        except (OSError, ValueError, httpx.HTTPError):
            continue
        soup = BeautifulSoup(document.html, "xml")
        for node in soup.find_all("loc"):
            candidate = node.get_text(strip=True).split("#", 1)[0]
            if not candidate or domain_key(candidate) != domain_key(home):
                continue
            path = urlparse(candidate).path.lower()
            if path.endswith((".xml", ".xml.gz")):
                if len(sitemap_queue) < 12:
                    sitemap_queue.append(candidate)
                continue
            if any(marker in path for marker in SKIP_PATH_MARKERS) or path.endswith(SKIP_EXTENSIONS):
                continue
            score = max((weight for word, weight in LINK_WEIGHTS.items() if word in path), default=0)
            if include_general and not score and path.rstrip("/"):
                score = 1
            if score:
                scored[candidate] = max(score, scored.get(candidate, 0))
    return [url for url, _ in sorted(scored.items(), key=lambda item: (-item[1], item[0]))[:limit]]


def extract_public_data(html: str, source_url: str) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    soup = BeautifulSoup(html, "lxml")
    data: dict[str, Any] = {}
    evidence: dict[str, dict[str, str]] = {}

    json_ld = _business_json_ld(soup)
    if json_ld:
        _set(data, evidence, "business_name", json_ld.get("name"), source_url, "json-ld")
        json_phone = normalize_phone(json_ld.get("telephone"))
        _set(data, evidence, "phone", json_phone, source_url, "json-ld")
        _set_list(data, evidence, "phones", [json_phone], source_url, "json-ld")
        raw_json_email = str(json_ld.get("email", ""))
        json_email = public_business_email(raw_json_email, source_url)
        _set(
            data,
            evidence,
            "generic_email",
            json_email,
            source_url,
            "json-ld",
        )
        _set_list(data, evidence, "emails", [json_email], source_url, "json-ld")
        address = json_ld.get("address")
        if isinstance(address, dict):
            area = address.get("addressLocality") or address.get("addressRegion")
            _set(data, evidence, "city_or_area", area, source_url, "json-ld")

    emails = {_clean_email(link.get("href", "")) for link in soup.select('a[href^="mailto:"]')}
    visible_text = soup.get_text(" ")
    emails.update(re.findall(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", visible_text, re.I))
    emails.update(
        "@".join((match.group(1), f"{match.group(2)}.{match.group(3)}"))
        for match in OBFUSCATED_EMAIL_RE.finditer(visible_text)
    )
    emails.update(_cloudflare_email(node.get("data-cfemail", "")) for node in soup.select("[data-cfemail]"))
    public_emails = sorted(
        {cleaned for email in emails if (cleaned := public_business_email(email, source_url))},
        key=email_priority,
    )[:3]
    public_email = public_emails[0] if public_emails else ""
    _set(data, evidence, "generic_email", public_email, source_url, "html")
    _set_list(data, evidence, "emails", public_emails, source_url, "html")

    phones = unique_phones(
        [
            *(link.get("href", "") for link in soup.select('a[href^="tel:"]')),
            *UK_PHONE_RE.findall(visible_text),
        ]
    )
    if phones:
        _set(data, evidence, "phone", phones[0], source_url, "html-link")
        _set_list(data, evidence, "phones", phones, source_url, "html-link")

    for anchor in soup.find_all("a", href=True):
        href = urljoin(source_url, str(anchor.get("href", "")))
        lower = href.lower()
        if "instagram.com" in lower or "facebook.com" in lower:
            _set(data, evidence, "instagram_or_social", href, source_url, "html-link")
            break

    return data, evidence


def enrich_public_pages(
    url: str,
    config: ScraperConfig,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, str]], list[str]]:
    fetcher = HtmlFetcher(
        cache_dir=config.cache_dir,
        timeout_seconds=config.request_timeout_seconds,
        retry_attempts=config.retry_attempts,
        cache_ttl_hours=config.cache_ttl_hours,
        browser_fallback=config.browser_fallback,
    )
    combined: dict[str, Any] = {"website": url}
    evidence: dict[str, dict[str, str]] = {"website": {"source_url": url, "method": "search", "value": url}}
    errors: list[str] = []
    queue: list[tuple[str, int]] = [(url, 0)]
    home = homepage_url(url)
    if home and home != url:
        queue.append((home, 0))
    if config.crawl_mode in {"deep", "exhaustive"}:
        sitemap_links = discover_sitemap_links(
            fetcher,
            home or url,
            config.crawl_page_limit,
            include_general=config.crawl_mode == "exhaustive",
        )
        queue.extend((link, 1) for link in sitemap_links)
    visited: set[str] = set()
    try:
        while queue and len(visited) < config.crawl_page_limit:
            link, depth = queue.pop(0)
            clean_link = link.split("#", 1)[0].rstrip("/") or link
            if clean_link in visited:
                continue
            try:
                page = fetcher.fetch(link)
                final_link = page.url.split("#", 1)[0].rstrip("/") or page.url
                if final_link in visited:
                    continue
                visited.add(final_link)
                page_data, page_evidence = extract_public_data(page.html, page.url)
                _attach_fetch_method(page_evidence, page.method)
                _merge(combined, evidence, page_data, page_evidence)
                contacts_found = len(combined.get("emails") or []) + len(combined.get("phones") or [])
                combined["crawl_pages_checked"] = len(visited)
                combined["crawl_page_limit"] = config.crawl_page_limit
                combined["crawl_mode"] = config.crawl_mode
                if progress_callback:
                    progress_callback(
                        {
                            "crawl_mode": config.crawl_mode,
                            "crawl_pages_checked": len(visited),
                            "crawl_page_limit": config.crawl_page_limit,
                            "crawl_current_url": page.url,
                            "crawl_contacts_found": contacts_found,
                        }
                    )
                path = urlparse(page.url).path.lower()
                if "contact" in path or "get-in-touch" in path or "enquir" in path:
                    _set(combined, evidence, "contact_page", page.url, page.url, "discovered-link")
                if "book" in path:
                    _set(combined, evidence, "booking_page", page.url, page.url, "discovered-link")
                    combined["has_online_booking"] = True
                if _contact_goal_reached(combined, len(visited)):
                    combined["crawl_stopped_early"] = True
                    break
                if depth < config.crawl_depth:
                    discovered = discover_relevant_links(
                        page.html,
                        page.url,
                        limit=config.crawl_page_limit,
                        include_general=config.crawl_mode == "exhaustive",
                    )
                    queued = {item[0].split("#", 1)[0].rstrip("/") or item[0] for item in queue}
                    for discovered_link in discovered:
                        clean_discovered = discovered_link.split("#", 1)[0].rstrip("/") or discovered_link
                        if clean_discovered not in visited and clean_discovered not in queued:
                            queue.append((discovered_link, depth + 1))
                            queued.add(clean_discovered)
            except (OSError, ValueError, httpx.HTTPError) as exc:
                errors.append(f"{link}: {type(exc).__name__}: {exc}")
    finally:
        fetcher.close()
    return combined, evidence, errors


def _contact_goal_reached(data: dict[str, Any], pages_checked: int) -> bool:
    if pages_checked < 4:
        return False
    emails = len(data.get("emails") or [])
    phones = len(data.get("phones") or [])
    return (emails >= 3 and phones >= 2) or (emails >= 2 and phones >= 3)


def apply_enrichment(
    lead: dict[str, Any],
    data: dict[str, Any],
    evidence: dict[str, dict[str, str]],
    errors: list[str],
) -> dict[str, Any]:
    source_website = str(data.get("website") or lead.get("website") or "")
    existing_emails = lead.get("emails") if isinstance(lead.get("emails"), list) else []
    existing_emails = [
        email
        for value in [*existing_emails, lead.get("generic_email", "")]
        if (email := public_business_email(value, source_website))
    ]
    lead["emails"] = sorted(set(existing_emails), key=email_priority)[:3]
    lead["generic_email"] = lead["emails"][0] if lead["emails"] else ""
    for item in evidence.values():
        if item.get("url") and not item.get("source_url"):
            item["source_url"] = item.pop("url")
    authoritative = {
        "business_name",
        "city_or_area",
        "generic_email",
        "emails",
        "phone",
        "phones",
        "contact_page",
        "booking_page",
        "instagram_or_social",
    }
    for field, value in data.items():
        if value and (field in authoritative or not lead.get(field)):
            lead[field] = value
    for field, item in evidence.items():
        if item.get("value") is None and lead.get(field) not in (None, "", []):
            item["value"] = lead[field]
    if lead.get("booking_page"):
        lead["has_online_booking"] = True
    for field in (
        "business_name",
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
    ):
        if lead.get(field) and field not in evidence:
            evidence[field] = {
                "value": lead[field],
                "source_url": str(lead.get("website", "")),
                "method": "llm",
            }
    lead["field_evidence"] = evidence
    if errors:
        lead["enrichment_errors"] = errors
    lead = promote_verified_business(lead)
    lead["lead_score"] = score_lead(lead)
    lead["lead_reason"] = explain_score(lead)
    return lead


def _business_json_ld(soup: BeautifulSoup) -> dict[str, Any] | None:
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.get_text(strip=True))
        except (TypeError, json.JSONDecodeError):
            continue
        items = list(_walk_json_ld(payload))
        for item in items:
            item_type = item.get("@type") if isinstance(item, dict) else None
            item_types = item_type if isinstance(item_type, list) else [item_type]
            is_business = (
                isinstance(item, dict)
                and item.get("name")
                and any(
                    value in BUSINESS_JSON_LD_TYPES or str(value).endswith("Business") for value in item_types
                )
            )
            if is_business:
                return item
    return None


def _walk_json_ld(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from _walk_json_ld(item)
    elif isinstance(value, dict):
        yield value
        graph = value.get("@graph")
        if graph is not None:
            yield from _walk_json_ld(graph)


def _attach_fetch_method(evidence: dict[str, dict[str, str]], method: str) -> None:
    for item in evidence.values():
        item["fetch"] = method


def _set(
    data: dict[str, Any],
    evidence: dict[str, dict[str, str]],
    field: str,
    value: Any,
    source_url: str,
    method: str,
) -> None:
    if value and not data.get(field):
        data[field] = str(value).strip()
        evidence[field] = {"source_url": source_url, "method": method, "value": str(value).strip()}


def _set_list(
    data: dict[str, Any],
    evidence: dict[str, dict[str, str]],
    field: str,
    values: list[str],
    source_url: str,
    method: str,
) -> None:
    existing = data.get(field) if isinstance(data.get(field), list) else []
    merged = list(dict.fromkeys([*existing, *(value for value in values if value)]))[:3]
    if merged:
        data[field] = merged
        evidence.setdefault(
            field,
            {"source_url": source_url, "method": method, "value": json.dumps(merged, ensure_ascii=False)},
        )


def _merge(
    target: dict[str, Any],
    target_evidence: dict[str, dict[str, str]],
    source: dict[str, Any],
    source_evidence: dict[str, dict[str, str]],
) -> None:
    for field, value in source.items():
        if field in {"emails", "phones"} and isinstance(value, list):
            current = target.get(field) if isinstance(target.get(field), list) else []
            target[field] = list(dict.fromkeys([*current, *value]))[:3]
            target_evidence.setdefault(field, source_evidence[field])
        elif value and not target.get(field):
            target[field] = value
            target_evidence[field] = source_evidence[field]


def _clean_email(value: str) -> str:
    return value.removeprefix("mailto:").split("?", 1)[0].strip().lower()


def _cloudflare_email(value: str) -> str:
    try:
        encoded = bytes.fromhex(str(value))
    except ValueError:
        return ""
    if len(encoded) < 2:
        return ""
    return "".join(chr(byte ^ encoded[0]) for byte in encoded[1:])
