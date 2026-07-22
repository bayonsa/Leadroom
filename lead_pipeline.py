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
MAX_SEARCH_RESULTS = 20
MAX_SITES_TO_SCRAPE = 8

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
}


def domain_key(url: str) -> str:
    parsed = tldextract.extract(url)
    if not parsed.domain or not parsed.suffix:
        return ""
    return f"{parsed.domain}.{parsed.suffix}".lower()


def is_good_business_url(url: str) -> bool:
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

    # حذف لینک‌های خیلی واضح دایرکتوری و شبکه اجتماعی
    bad_words = [
        "directory",
        "listing",
        "review",
        "jobs",
        "career",
        "map",
        "search",
        "results",
    ]

    url_lower = url.lower()
    if any(word in url_lower for word in bad_words):
        return False

    return True


def search_business_sites(niche: str, location: str, max_results: int = 20) -> list[dict]:
    query = (
        f'{niche} "{location}" '
        f'contact website booking services email'
    )

    results = []

    with DDGS() as ddgs:
        for item in ddgs.text(query, region="uk-en", safesearch="moderate", max_results=max_results):
            url = item.get("href") or item.get("url")
            title = item.get("title", "")
            body = item.get("body", "")

            if not is_good_business_url(url):
                continue

            results.append({
                "title": title,
                "url": url,
                "snippet": body,
                "domain": domain_key(url),
            })

    # حذف دامنه‌های تکراری
    unique = []
    seen_domains = set()

    for item in results:
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
    Extract public B2B lead information from this business website.

    Return only valid JSON.
    Do not use markdown.
    Do not explain anything.

    Use this exact structure:
    {
      "business_name": "",
      "website": "",
      "city_or_area": "",
      "services": [],
      "generic_email": "",
      "phone": "",
      "contact_page": "",
      "booking_page": "",
      "instagram_or_social": "",
      "lead_score": 0,
      "lead_reason": ""
    }

    Rules:
    - Use only public business information visible on the website.
    - Prefer generic emails like info@, hello@, contact@, bookings@.
    - Avoid private personal emails.
    - Do not guess missing information.
    - If a field is missing, keep it empty.
    - lead_score must be from 1 to 10.
    - lead_reason must explain why this business may be a useful lead for website, branding, booking, SEO, or digital marketing services.
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
                "business_name": "",
                "website": url,
                "city_or_area": "",
                "services": [],
                "generic_email": "",
                "phone": "",
                "contact_page": "",
                "booking_page": "",
                "instagram_or_social": "",
                "lead_score": 0,
                "lead_reason": "Could not parse model output.",
                "raw_output": raw["content"],
            }

    if isinstance(raw, dict):
        raw.setdefault("website", url)
        return raw

    return {
        "business_name": "",
        "website": url,
        "city_or_area": "",
        "services": [],
        "generic_email": "",
        "phone": "",
        "contact_page": "",
        "booking_page": "",
        "instagram_or_social": "",
        "lead_score": 0,
        "lead_reason": "Unexpected output format.",
        "raw_output": str(raw),
    }


def main():
    print(f"Searching for: {NICHE} in {LOCATION}")

    sites = search_business_sites(
        niche=NICHE,
        location=LOCATION,
        max_results=MAX_SEARCH_RESULTS,
    )

    print(f"\nFound {len(sites)} candidate websites:\n")

    for i, site in enumerate(sites[:MAX_SITES_TO_SCRAPE], start=1):
        print(f"{i}. {site['title']}")
        print(f"   {site['url']}")

    leads = []

    for i, site in enumerate(sites[:MAX_SITES_TO_SCRAPE], start=1):
        url = site["url"]
        print(f"\nScraping {i}/{min(len(sites), MAX_SITES_TO_SCRAPE)}: {url}")

        try:
            lead = scrape_business_site(url)
            lead["source_url"] = url
            lead["search_title"] = site["title"]
            lead["search_snippet"] = site["snippet"]
            leads.append(lead)
            print(f"Done: {lead.get('business_name', '') or url}")
        except Exception as e:
            print(f"Failed: {url}")
            print(str(e))

        time.sleep(2)

    output = {
        "niche": NICHE,
        "location": LOCATION,
        "leads": leads,
        "candidate_sites": sites,
    }

    with open("lead_pipeline_output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    if leads:
        df = pd.DataFrame(leads)
        df.to_csv("lead_pipeline_output.csv", index=False, encoding="utf-8-sig")
        print(f"\nSaved {len(leads)} leads to lead_pipeline_output.csv")
    else:
        print("\nNo leads scraped.")

    print("Saved raw output to lead_pipeline_output.json")


if __name__ == "__main__":
    main()