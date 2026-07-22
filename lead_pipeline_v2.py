import json
import time
from urllib.parse import urlparse

import pandas as pd
import tldextract
from ddgs import DDGS
from scrapegraphai.graphs import SmartScraperGraph


MODEL = "ollama/llama3.2:3b"

NICHE = "hair and beauty salons"
LOCATION = "London UK"

MAX_RESULTS_PER_QUERY = 12
MAX_SITES_TO_SCRAPE = 10

BLOCKED_DOMAINS = {
    "yell.com",
    "yelp.com",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "x.com",
    "twitter.com",
    "tripadvisor.co.uk",
    "tripadvisor.com",
    "gumtree.com",
    "indeed.com",
    "glassdoor.co.uk",
    "checkatrade.com",
    "trustpilot.com",
    "companieshouse.gov.uk",
    "gov.uk",
    "google.com",
    "bing.com",
    "fresha.com",
    "treatwell.co.uk",
    "booksy.com",
    "harrods.com",
}

BAD_URL_WORDS = [
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
]

BAD_TITLE_WORDS = [
    "directory",
    "near me",
    "best salons",
    "top salons",
    "book salons",
    "instantly book",
    "covid",
    "coronavirus",
    "updates",
    "jobs",
    "careers",
]


def domain_key(url: str) -> str:
    parsed = tldextract.extract(url)
    if not parsed.domain or not parsed.suffix:
        return ""
    return f"{parsed.domain}.{parsed.suffix}".lower()


def homepage_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    return f"{parsed.scheme}://{parsed.netloc}/"


def is_good_business_url(url: str, title: str = "") -> bool:
    if not url:
        return False

    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        return False

    domain = domain_key(url)

    if not domain:
        return False

    if domain in BLOCKED_DOMAINS:
        return False

    url_lower = url.lower()
    title_lower = title.lower()

    if any(word in url_lower for word in BAD_URL_WORDS):
        return False

    if any(word in title_lower for word in BAD_TITLE_WORDS):
        return False

    return True


def build_queries(niche: str, location: str) -> list[str]:
    return [
        f'{niche} "{location}" official website contact',
        f'{niche} "{location}" "book now" "contact"',
        f'{niche} "{location}" "services" "prices"',
        f'"hair salon" "London" "official website" "contact"',
        f'"beauty salon" "London" "book online" "contact"',
    ]


def search_business_sites(niche: str, location: str) -> list[dict]:
    all_results = []

    queries = build_queries(niche, location)

    with DDGS() as ddgs:
        for query in queries:
            print(f"\nSearch query: {query}")

            try:
                results = ddgs.text(
                    query,
                    region="uk-en",
                    safesearch="moderate",
                    max_results=MAX_RESULTS_PER_QUERY,
                )
            except Exception as e:
                print(f"Search failed: {e}")
                continue

            for item in results:
                url = item.get("href") or item.get("url")
                title = item.get("title", "")
                body = item.get("body", "")

                if not is_good_business_url(url, title):
                    continue

                all_results.append({
                    "title": title,
                    "url": url,
                    "homepage": homepage_url(url),
                    "snippet": body,
                    "domain": domain_key(url),
                })

            time.sleep(1)

    unique = []
    seen_domains = set()

    for item in all_results:
        if item["domain"] in seen_domains:
            continue
        seen_domains.add(item["domain"])
        unique.append(item)

    return unique


def scrape_business_site(url: str) -> dict:
    graph_config = {
        "llm": {
            "model": MODEL,
            "temperature": 0,
            "format": "json",
            "model_tokens": 8192,
            "base_url": "http://localhost:11434",
        },
        "verbose": False,
        "headless": True,
    }

    prompt = """
    Extract public B2B lead information from this small business website.

    Return only valid JSON.
    Do not use markdown.
    Do not explain anything.

    Use this exact structure:
    {
      "is_valid_lead": true,
      "business_name": "",
      "website": "",
      "city_or_area": "",
      "business_type": "",
      "services": [],
      "generic_email": "",
      "phone": "",
      "contact_page": "",
      "booking_page": "",
      "instagram_or_social": "",
      "has_online_booking": false,
      "website_quality_note": "",
      "lead_score": 0,
      "lead_reason": ""
    }

    Rules:
    - This must be a real individual business website.
    - Reject directories, marketplaces, booking platforms, review websites, large department stores, blog posts, and generic category pages.
    - If it is not a real small or medium business, set is_valid_lead to false.
    - Use only public business information visible on the website.
    - Prefer generic emails like info@, hello@, contact@, bookings@.
    - Avoid private personal emails.
    - Do not guess missing information.
    - If a field is missing, keep it empty.
    - lead_score must be from 1 to 10.
    - lead_reason must explain why this business may be useful for website, branding, booking, SEO, or digital marketing services.
    """

    graph = SmartScraperGraph(
        prompt=prompt,
        source=url,
        config=graph_config,
    )

    raw = graph.run()

    if isinstance(raw, dict) and "content" in raw:
        try:
            return json.loads(raw["content"])
        except json.JSONDecodeError:
            return {
                "is_valid_lead": False,
                "business_name": "",
                "website": url,
                "city_or_area": "",
                "business_type": "",
                "services": [],
                "generic_email": "",
                "phone": "",
                "contact_page": "",
                "booking_page": "",
                "instagram_or_social": "",
                "has_online_booking": False,
                "website_quality_note": "",
                "lead_score": 0,
                "lead_reason": "Could not parse model output.",
                "raw_output": raw["content"],
            }

    if isinstance(raw, dict):
        raw.setdefault("website", url)
        return raw

    return {
        "is_valid_lead": False,
        "business_name": "",
        "website": url,
        "city_or_area": "",
        "business_type": "",
        "services": [],
        "generic_email": "",
        "phone": "",
        "contact_page": "",
        "booking_page": "",
        "instagram_or_social": "",
        "has_online_booking": False,
        "website_quality_note": "",
        "lead_score": 0,
        "lead_reason": "Unexpected output format.",
        "raw_output": str(raw),
    }


def clean_leads(leads: list[dict]) -> list[dict]:
    cleaned = []

    bad_names = {
        "",
        "na",
        "n/a",
        "none",
        "beauty salons",
        "hair salons",
        "hair and beauty salons",
    }

    for lead in leads:
        name = str(lead.get("business_name", "")).strip()
        website = str(lead.get("website", "")).strip()
        source_url = str(lead.get("source_url", "")).strip()

        if name.lower() in bad_names:
            continue

        if not website and not source_url:
            continue

        if lead.get("is_valid_lead") is False:
            continue

        lead_score = lead.get("lead_score", 0)

        try:
            lead_score = int(lead_score)
        except Exception:
            lead_score = 0

        if lead_score <= 0:
            lead["lead_score"] = 5
        else:
            lead["lead_score"] = lead_score

        cleaned.append(lead)

    return cleaned


def main():
    print(f"Searching for: {NICHE} in {LOCATION}")

    sites = search_business_sites(NICHE, LOCATION)

    print(f"\nFound {len(sites)} candidate websites:\n")

    for i, site in enumerate(sites[:MAX_SITES_TO_SCRAPE], start=1):
        print(f"{i}. {site['title']}")
        print(f"   {site['homepage']}")

    raw_leads = []

    for i, site in enumerate(sites[:MAX_SITES_TO_SCRAPE], start=1):
        url = site["homepage"]

        print(f"\nScraping {i}/{min(len(sites), MAX_SITES_TO_SCRAPE)}: {url}")

        try:
            lead = scrape_business_site(url)
            lead["source_url"] = site["url"]
            lead["search_title"] = site["title"]
            lead["search_snippet"] = site["snippet"]
            lead["domain"] = site["domain"]
            raw_leads.append(lead)

            print(f"Done: {lead.get('business_name', '') or url}")

        except Exception as e:
            print(f"Failed: {url}")
            print(str(e))

        time.sleep(2)

    clean = clean_leads(raw_leads)

    output = {
        "niche": NICHE,
        "location": LOCATION,
        "raw_leads": raw_leads,
        "clean_leads": clean,
        "candidate_sites": sites,
    }

    with open("lead_pipeline_v2_output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    if clean:
        df = pd.DataFrame(clean)
        df = df.sort_values(by="lead_score", ascending=False)
        df.to_csv("lead_pipeline_v2_output.csv", index=False, encoding="utf-8-sig")
        print(f"\nSaved {len(clean)} clean leads to lead_pipeline_v2_output.csv")
    else:
        print("\nNo clean leads saved.")

    print("Saved raw output to lead_pipeline_v2_output.json")


if __name__ == "__main__":
    main()