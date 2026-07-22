from __future__ import annotations

import re
from urllib.parse import urlparse

import tldextract

from app.config import DEFAULT_BLOCKED_DOMAINS

NICHE_STOP_WORDS = {
    "and",
    "business",
    "businesses",
    "company",
    "companies",
    "clinic",
    "clinics",
    "firm",
    "firms",
    "service",
    "services",
    "local",
    "independent",
    "office",
    "contractor",
    "contractors",
    "subcontractor",
    "subcontractors",
}

LOCATION_COUNTRY_WORDS = {
    "england",
    "great",
    "britain",
    "kingdom",
    "united",
    "uk",
    "usa",
    "states",
}

UK_POSTCODE_RE = re.compile(
    r"\b(?:GIR\s?0AA|[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})\b",
    re.IGNORECASE,
)

BAD_URL_WORDS = {
    "directory",
    "listing",
    "review",
    "reviews",
    "jobs",
    "career",
    "careers",
    "map",
    "search",
    "results",
    "covid",
    "coronavirus",
    "blog",
    "news",
    "article",
    "voucher",
    "gift-card",
    "leadfinder",
}

BAD_TITLE_WORDS = {
    "directory",
    "near me",
    "best salons",
    "best hair salons",
    "the best hair salons",
    "best beauty salons",
    "top salons",
    "book salons",
    "instantly book",
    "covid",
    "coronavirus",
    "updates",
    "jobs",
    "careers",
    "list of all",
    "lead finder",
    "reviews",
    "compare",
    "how to choose",
    "top 5",
    "top 10",
}


def domain_key(url: str) -> str:
    parsed = tldextract.extract(url or "")
    if not parsed.domain or not parsed.suffix:
        return ""
    return f"{parsed.domain}.{parsed.suffix}".lower()


def homepage_url(url: str) -> str:
    parsed = urlparse(url or "")
    if not parsed.scheme or not parsed.netloc:
        return url
    return f"{parsed.scheme}://{parsed.netloc}/"


def is_good_business_url(
    url: str,
    title: str = "",
    blocked_domains: set[str] | None = None,
) -> bool:
    if not url:
        return False

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False

    domain = domain_key(url)
    if not domain:
        return False

    blocked = DEFAULT_BLOCKED_DOMAINS if blocked_domains is None else blocked_domains
    if any(domain == item or domain.endswith(f".{item}") for item in blocked):
        return False
    if domain.endswith((".edu", ".ac.uk")):
        return False

    url_lower = url.lower()
    title_lower = title.lower()

    if any(word in url_lower for word in BAD_URL_WORDS):
        return False

    return not any(word in title_lower for word in BAD_TITLE_WORDS)


def is_relevant_to_niche(url: str, title: str, snippet: str, niche: str) -> bool:
    terms = {
        _term_root(word)
        for word in niche.lower().replace("&", " ").split()
        if len(word) >= 4 and word not in NICHE_STOP_WORDS
    }
    if not terms:
        return True
    primary_evidence = f"{domain_key(url)} {title}".lower()
    evidence = f"{primary_evidence} {snippet}".lower()
    matched_terms = {term for term in terms if re.search(rf"\b{re.escape(term)}[a-z]*", evidence)}
    primary_matches = {term for term in terms if re.search(rf"\b{re.escape(term)}[a-z]*", primary_evidence)}
    required_matches = 1 if len(terms) == 1 else 2
    return bool(primary_matches) and len(matched_terms) >= required_matches


def is_relevant_to_location(url: str, title: str, snippet: str, location: str) -> bool:
    place_words = [
        word.lower()
        for word in re.findall(r"[A-Za-z]+", location)
        if word.lower() not in LOCATION_COUNTRY_WORDS
    ]
    if not place_words:
        return True

    domain_and_title = f"{domain_key(url)} {title}".lower()
    snippet_lower = " ".join(snippet.lower().split())
    place_pattern = r"\s+".join(re.escape(word) for word in place_words)

    if re.search(rf"\b{place_pattern}\b", domain_and_title):
        return True

    local_phrases = (
        rf"\b(?:based|located|headquartered)\s+(?:in|near)\s+{place_pattern}\b",
        rf"\b{place_pattern}[ -]based\b",
        rf"\b(?:in|near|serving|across)\s+{place_pattern}\b",
        rf"^{place_pattern}(?:\b|[,|:-])",
    )
    if any(re.search(pattern, snippet_lower) for pattern in local_phrases):
        return True

    return bool(UK_POSTCODE_RE.search(snippet) and re.search(rf"\b{place_pattern}\b", snippet_lower))


def _term_root(word: str) -> str:
    word = "".join(character for character in word if character.isalpha())
    if word.startswith("dent"):
        return "dent"
    if word.endswith("ing") and len(word) > 6:
        return word[:-3]
    if word.endswith("ies") and len(word) > 5:
        return word[:-3] + "y"
    if word.endswith("s") and len(word) > 5:
        return word[:-1]
    return word
