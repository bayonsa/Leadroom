import json
from scrapegraphai.graphs import SmartScraperGraph

graph_config = {
    "llm": {
        "model": "ollama/gemma4:e4b",
        "temperature": 0,
        "format": "json",
        "model_tokens": 8192,
        "base_url": "http://localhost:11434",
    },
    "verbose": True,
    "headless": False,
}

source_url = "https://www.google.com/search?q=cleaning+companies+in+London"

smart_scraper_graph = SmartScraperGraph(
    prompt="""
    Extract public B2B lead information from this page.

    Return valid JSON with this exact structure:
    {
      "leads": [
        {
          "business_name": "",
          "website": "",
          "city_or_area": "",
          "services": [],
          "generic_email": "",
          "phone": "",
          "lead_score": 0,
          "lead_reason": ""
        }
      ]
    }

    Rules:
    - Use only public business information.
    - Prefer generic business emails like info@, hello@, contact@.
    - Avoid private personal emails.
    - Do not guess missing information.
    - If a field is missing, keep it empty.
    """,
    source=source_url,
    config=graph_config,
)

result = smart_scraper_graph.run()

print(json.dumps(result, indent=2, ensure_ascii=False))

with open("leads_raw.json", "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)

print("Saved to leads_raw.json")