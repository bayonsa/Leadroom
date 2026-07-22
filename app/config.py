from __future__ import annotations

import os
import re
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

DEFAULT_BLOCKED_DOMAINS = {
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
    "d7leadfinder.com",
    "aveda.co.uk",
    "whatclinic.com",
    "tiktok.com",
    "pinterest.com",
    "tuugo.co.uk",
    "cleanster.com",
    "need-a-pro.com",
    "andent.al",
    "thedentalhospital.org.uk",
    "europages.co.uk",
    "doctify.com",
    "designmynight.com",
    "mybuilder.com",
    "ukclassifieds.co.uk",
    "mastermanchester.co.uk",
    "bestdentists.uk",
    "github.com",
    "github.io",
    "malt.uk",
    "resumeworded.com",
    "10times.com",
    "twine.net",
    "wikipedia.org",
    "123rf.com",
    "designrush.com",
    "sitelike.org",
    "youtube.com",
}


def _data_path(relative: str) -> Path:
    if relative == "cache":
        cache = os.getenv("LEADROOM_CACHE_DIR", "").strip()
        if cache:
            return Path(cache)
    root = os.getenv("LEADROOM_DATA_ROOT", "").strip()
    return Path(root) / relative if root else Path("data") / relative


class ScraperConfig(BaseModel):
    niche: str
    location: str
    model: str = Field(default_factory=lambda: os.getenv("DEFAULT_MODEL", "ollama/llama3.2:3b"))
    max_results_per_query: int = Field(default=12, ge=1, le=100)
    max_sites: int = Field(default=10, ge=1, le=500)
    output_dir: Path = Field(default_factory=lambda: _data_path("exports"))
    run_name: str = "lead_pipeline"
    blocked_domains: set[str] = Field(default_factory=lambda: set(DEFAULT_BLOCKED_DOMAINS))
    delay_seconds: float = Field(default=1.0, ge=0, le=60)
    request_timeout_seconds: float = Field(default=12.0, ge=1, le=120)
    retry_attempts: int = Field(default=2, ge=0, le=5)
    crawl_mode: str = Field(default="quick", pattern="^(quick|deep|exhaustive)$")
    crawl_page_limit: int = Field(default=6, ge=1, le=40)
    crawl_depth: int = Field(default=2, ge=0, le=4)
    cache_dir: Path = Field(default_factory=lambda: _data_path("cache"))
    cache_ttl_hours: int = Field(default=168, ge=1, le=2160)
    browser_fallback: bool = True
    database_path: Path = Field(default_factory=lambda: _data_path("lead_scraper.db"))
    reuse_existing_leads: bool = True
    discovery_mode: str = "new_only"
    search_provider: str = Field(default_factory=lambda: os.getenv("SEARCH_PROVIDER", "auto"))
    brave_search_api_key: str = Field(
        default_factory=lambda: os.getenv("BRAVE_SEARCH_API_KEY", ""),
        exclude=True,
        repr=False,
    )
    ollama_base_url: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    llm_api_key: str = Field(
        default_factory=lambda: os.getenv("LEADROOM_LLM_API_KEY", ""),
        exclude=True,
        repr=False,
    )

    @field_validator("niche", "location", "model")
    @classmethod
    def require_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("run_name")
    @classmethod
    def validate_run_name(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", value):
            raise ValueError("must be 1-80 filename-safe characters")
        return value

    @field_validator("ollama_base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("must be an HTTP(S) URL")
        return value

    @field_validator("search_provider")
    @classmethod
    def validate_search_provider(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"auto", "brave", "ddgs", "osm_local", "hybrid"}:
            raise ValueError("must be auto, brave, ddgs, osm_local, or hybrid")
        return value

    @field_validator("discovery_mode")
    @classmethod
    def validate_discovery_mode(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"new_only", "reuse", "refresh"}:
            raise ValueError("must be new_only, reuse, or refresh")
        return value
