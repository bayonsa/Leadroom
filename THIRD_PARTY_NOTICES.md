# Third-Party Notices

Leadroom includes or integrates with third-party open-source software and data. This file is a concise attribution guide, not a replacement for the license text distributed with each dependency.

## ScrapeGraphAI

The first Leadroom prototype was built around `SmartScraperGraph`, and the current enrichment pipeline continues to depend on the open-source [ScrapeGraphAI project](https://github.com/ScrapeGraphAI/Scrapegraph-ai).

- Upstream repository: <https://github.com/ScrapeGraphAI/Scrapegraph-ai>
- Upstream license: MIT
- Role in Leadroom: LLM-assisted structured extraction from public business websites

Leadroom is an independent community project. It is not an official ScrapeGraphAI product and is not endorsed by ScrapeGraphAI's maintainers.

## OpenStreetMap and Geofabrik

The optional local discovery engine can download OpenStreetMap extracts provided by Geofabrik.

- OpenStreetMap copyright: <https://www.openstreetmap.org/copyright>
- Open Database License (ODbL): <https://opendatacommons.org/licenses/odbl/>
- Geofabrik download server and usage policy: <https://download.geofabrik.de/>

OpenStreetMap data is Copyright OpenStreetMap contributors and is available under the ODbL. Generated products must preserve the attribution and comply with the applicable database license.

## Other Dependencies

Python and frontend dependencies are declared in `pyproject.toml`, `requirements.txt`, and `frontend/package-lock.json`. The current audit and binary-distribution blocker are recorded in `docs/DEPENDENCY_LICENSES.md`. Distributors must repeat that audit and include the applicable licence texts with each release artifact.
