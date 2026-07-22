import json
import pandas as pd
from scrapegraphai.graphs import SmartScraperGraph

MODEL = "ollama/llama3.2:3b"

SOURCE_URL = "https://www.yell.com/s/cleaners-london.html"

graph_config = {
    "llm": {
        "model": MODEL,
        "temperature": 0,
        "format": "json",
        "model_tokens": 8192,
        "base_url": "http://localhost:11434",
    },
    "verbose": True,
    "headless": False,
}

prompt = """
Extract public B2B lead information from this page.

Return only valid JSON.
Do not use markdown.
Do not explain anything.

Use this exact structure:
{
  "leads": [
    {
      "business_name": "",
      "website": "",
      "city_or_area": "",
      "services": [],
      "generic_email": "",
      "phone": "",
      "contact_page": "",
      "lead_score": 0,
      "lead_reason": ""
    }
  ]
}

Rules:
- Extract only businesses visible on the page.
- Use only public business information.
- Prefer generic emails like info@, hello@, contact@.
- Avoid private personal emails.
- Do not guess missing information.
- If a field is missing, keep it empty.
- lead_score must be from 1 to 10.
"""

graph = SmartScraperGraph(
    prompt=prompt,
    source=SOURCE_URL,
    config=graph_config,
)

raw_result = graph.run()

print("\nRAW RESULT:")
print(raw_result)

if isinstance(raw_result, dict) and "content" in raw_result:
    try:
        data = json.loads(raw_result["content"])
    except json.JSONDecodeError:
        data = raw_result
else:
    data = raw_result

print("\nCLEAN JSON:")
print(json.dumps(data, indent=2, ensure_ascii=False))

with open("leads_cleaners_london.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

leads = data.get("leads", [])

if leads:
    df = pd.DataFrame(leads)
    df.to_csv("leads_cleaners_london.csv", index=False, encoding="utf-8-sig")
    print(f"\nSaved {len(leads)} leads to leads_cleaners_london.csv")
else:
    print("\nNo leads found.")