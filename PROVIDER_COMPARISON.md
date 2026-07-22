# Search Provider Comparison

Measured on 14 July 2026 using five query variants per case, three results per query, and a five-candidate cap.

| Provider | Status | Candidate coverage | Case latency | Cost | Operational role |
|---|---|---:|---:|---:|---|
| DDGS | Live benchmark | 9 manually reviewed business domains after final filters across 3 cases | 6.6-7.1 s | No API fee; no SLA | Prototype and automatic fallback |
| Brave Search | Contract/fixture tested | Not live-tested without a project key | Official service target is under 1 s for 95% of requests | $5 per 1,000 requests with $5 monthly credits | Recommended production provider |

The DDGS run covered London hair/beauty, Manchester cleaning, and Birmingham dental searches. Two filter iterations removed query drift and directory/listicle domains. Stable labelled regression cases remain the release gate because live rankings change.

Brave integration uses the official `GET /res/v1/web/search` endpoint, `X-Subscription-Token`, GB country targeting, English results, a maximum count of 20, bounded retries, and a 12-second timeout. The API key is read from `BRAVE_SEARCH_API_KEY` and excluded from persisted run configuration.

Sources: [Brave Web Search API reference](https://api-dashboard.search.brave.com/api-reference/web/search/get), [Brave Search API pricing](https://brave.com/search/api/).

## Reproduce

```powershell
python -m benchmarks.run_search_benchmark --provider ddgs --max-results 3 --top 5 --delay 0
$env:BRAVE_SEARCH_API_KEY = "..."
python -m benchmarks.run_search_benchmark --provider brave --max-results 3 --top 5 --delay 0
```

Before selecting Brave for stored commercial datasets, review the current plan's storage rights and terms.
