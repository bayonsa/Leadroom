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

smart_scraper_graph = SmartScraperGraph(
    prompt="""
    Extract basic business information from this website.

    Return valid JSON with these fields:
    {
      "business_name": "",
      "summary": "",
      "services": [],
      "contact_links": [],
      "social_links": []
    }

    Do not guess missing information.
    """,
    source="https://scrapegraphai.com/",
    config=graph_config,
)

result = smart_scraper_graph.run()

print(json.dumps(result, indent=2, ensure_ascii=False))