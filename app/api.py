from __future__ import annotations

import asyncio
import base64
import binascii
import csv
import io
import json
import os
import re
import shutil
import ssl
import threading
import time
import uuid
from collections.abc import AsyncIterable, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import datetime
from hmac import compare_digest
from ipaddress import ip_address
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.compliance import ComplianceService
from app.config import DEFAULT_BLOCKED_DOMAINS, ScraperConfig
from app.database import RUN_TERMINAL, RunRepository
from app.email_delivery import DeliveryUncertainError, EmailDeliveryConfig, SMTPEmailProvider
from app.local_data import LocalDataService
from app.models import LeadExtraction
from app.normalizer import LEAD_FIELDS, clean_leads
from app.pipeline import run_pipeline
from app.search import SearchStopped, search_business_sites
from app.storage import (
    directory_size,
    load_storage_config,
    save_storage_config,
    schedule_storage_change,
)

DEFAULT_WORKSPACE_NAME = "Leadroom"
DEFAULT_WORKSPACE_SUBTITLE = "Signal desk"
VALID_THEMES = {
    "brushstroke",
    "genesis",
    "flip7",
    "rawblock",
    "evreghen",
    "ember",
    "insightdeck",
    "vercel",
    "trustblue",
    "zengrid",
}


def _text_or_default(value: Any, default: str) -> Any:
    if isinstance(value, str):
        return value.strip() or default
    return default if value is None else value


def make_run_name(niche: str, now: datetime | None = None) -> str:
    safe_niche = re.sub(r"[^A-Za-z0-9]+", "_", niche.strip().lower()).strip("_")
    safe_niche = safe_niche or "market"
    timestamp = (now or datetime.now().astimezone()).strftime("%Y%m%d_%H%M%S_%f")
    return f"{safe_niche[:45]}_{timestamp}"


class RunCreate(BaseModel):
    niche: str = Field(min_length=1, max_length=120)
    location: str = Field(min_length=1, max_length=120)
    max_results_per_query: int = Field(default=100, ge=1, le=100)
    max_sites: int = Field(default=500, ge=1, le=500)
    model: str | None = Field(default=None, min_length=1, max_length=120)
    run_name: str = Field(default="lead_pipeline", pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    delay_seconds: float = Field(default=1.0, ge=0, le=60)
    search_provider: str = Field(default="auto", pattern="^(auto|brave|ddgs|osm_local|hybrid)$")
    discovery_mode: str = Field(default="new_only", pattern="^(new_only|reuse|refresh)$")
    crawl_mode: str = Field(default="deep", pattern="^(quick|deep|exhaustive)$")
    advanced_fetching: bool = True


class Problem(BaseModel):
    problem: str
    cause: str
    fix: str


class CandidateSelection(BaseModel):
    selected: bool


class LeadUpdate(BaseModel):
    business_name: str | None = Field(default=None, max_length=200)
    generic_email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=80)
    city_or_area: str | None = Field(default=None, max_length=200)
    website_quality_note: str | None = Field(default=None, max_length=2000)


class RepositoryImport(BaseModel):
    run_id: str = Field(min_length=1, max_length=36)
    domains: list[str] | None = Field(default=None, min_length=1, max_length=500)


class RepositoryLeadUpdate(BaseModel):
    business_name: str | None = Field(default=None, max_length=200)
    city_or_area: str | None = Field(default=None, max_length=200)
    website: str | None = Field(default=None, max_length=1000)
    emails: list[str] | None = Field(default=None, max_length=3)
    phones: list[str] | None = Field(default=None, max_length=3)
    collection: str | None = Field(default=None, min_length=1, max_length=120)


class RepositoryCollectionMerge(BaseModel):
    sources: list[str] = Field(min_length=1, max_length=100)
    target: str = Field(min_length=1, max_length=120)

    @field_validator("sources")
    @classmethod
    def clean_sources(cls, values: list[str]) -> list[str]:
        clean = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if not clean:
            raise ValueError("at least one source collection is required")
        return clean

    @field_validator("target")
    @classmethod
    def clean_target(cls, value: str) -> str:
        return value.strip()


class SuppressionCreate(BaseModel):
    value: str = Field(min_length=3, max_length=320)
    kind: str = Field(pattern="^(email|domain)$")
    reason: str = Field(min_length=3, max_length=500)


class OutreachDraftCreate(BaseModel):
    run_id: str
    domain: str
    subscriber_type: str = Field(pattern="^(corporate|sole_trader|unknown)$")
    lawful_basis_note: str = Field(min_length=10, max_length=2000)
    sender_identity: str = Field(min_length=2, max_length=200)
    opt_out_address: str = Field(min_length=5, max_length=320)
    offer_summary: str = Field(min_length=10, max_length=1000)
    consent_confirmed: bool = False
    tone: str = Field(default="professional", pattern="^(professional|warm|concise|friendly)$")
    links: list[str] = Field(default_factory=list, max_length=10)
    ai_personalize: bool = False

    @field_validator("links")
    @classmethod
    def valid_campaign_links(cls, values: list[str]) -> list[str]:
        clean: list[str] = []
        for value in values:
            link = value.strip()
            if not re.fullmatch(r"https?://[^\s]{3,500}", link):
                raise ValueError(f"invalid campaign link: {value}")
            if link not in clean:
                clean.append(link)
        return clean


class OutreachApproval(BaseModel):
    reviewed_by: str = Field(min_length=2, max_length=120)
    corporate_status_confirmed: bool
    privacy_notice_confirmed: bool


class OutreachExport(BaseModel):
    draft_ids: list[str] = Field(min_length=1, max_length=25)


class OutreachSend(BaseModel):
    draft_ids: list[str] = Field(min_length=1, max_length=25)
    email_account_id: str | None = Field(default=None, min_length=1, max_length=64)


class OutreachPreflight(BaseModel):
    run_id: str = Field(min_length=1, max_length=36)
    domains: list[str] | None = Field(default=None, max_length=100)


class OutreachBulkCreate(OutreachDraftCreate):
    domain: str | None = None
    domains: list[str] = Field(min_length=1, max_length=100)


class OutreachBulkApproval(OutreachApproval):
    draft_ids: list[str] = Field(min_length=1, max_length=100)


class SettingsUpdate(BaseModel):
    model_provider: str = Field(pattern="^(ollama|openai_compatible)$")
    model_name: str = Field(min_length=1, max_length=120)
    model_endpoint: str = Field(min_length=8, max_length=500)
    api_key: str | None = Field(default=None, max_length=500)
    clear_api_key: bool = False
    blocked_domains: list[str] = Field(default_factory=list, max_length=500)
    workspace_name: str = Field(min_length=1, max_length=40)
    workspace_subtitle: str = Field(default=DEFAULT_WORKSPACE_SUBTITLE, max_length=60)
    logo_data_url: str = Field(default="", max_length=700_000)
    theme: str = Field(
        default="brushstroke",
        pattern="^(brushstroke|genesis|flip7|rawblock|evreghen|ember|insightdeck|vercel|trustblue|zengrid)$",
    )
    smtp_host: str | None = Field(default=None, max_length=255)
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_security: str | None = Field(default=None, pattern="^(starttls|ssl|none)$")
    smtp_username: str | None = Field(default=None, max_length=320)
    smtp_password: str | None = Field(default=None, max_length=500)
    clear_smtp_password: bool = False
    smtp_from_email: str | None = Field(default=None, max_length=320)
    smtp_from_name: str | None = Field(default=None, max_length=200)
    smtp_reply_to: str | None = Field(default=None, max_length=320)

    @field_validator("workspace_name", mode="before")
    @classmethod
    def default_workspace_name(cls, value: Any) -> Any:
        return _text_or_default(value, DEFAULT_WORKSPACE_NAME)

    @field_validator("workspace_subtitle", mode="before")
    @classmethod
    def default_workspace_subtitle(cls, value: Any) -> Any:
        return _text_or_default(value, DEFAULT_WORKSPACE_SUBTITLE)

    @field_validator("model_name")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("model_endpoint")
    @classmethod
    def valid_endpoint(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("must be an HTTP(S) URL")
        parsed = urlparse(value)
        host = parsed.hostname or ""
        is_loopback = host.lower() == "localhost"
        if not is_loopback:
            with suppress(ValueError):
                is_loopback = ip_address(host).is_loopback
        if parsed.scheme != "https" and not is_loopback:
            raise ValueError("remote model endpoints must use HTTPS")
        return value

    @field_validator("blocked_domains")
    @classmethod
    def valid_domains(cls, values: list[str]) -> list[str]:
        clean: list[str] = []
        for value in values:
            domain = value.strip().lower().removeprefix("www.")
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?\.[a-z]{2,63}", domain):
                raise ValueError(f"invalid domain: {value}")
            if domain not in clean:
                clean.append(domain)
        return clean

    @field_validator("logo_data_url")
    @classmethod
    def valid_logo(cls, value: str) -> str:
        if not value:
            return ""
        match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)", value)
        if not match:
            raise ValueError("logo must be a PNG, JPEG, or WebP image")
        try:
            decoded = base64.b64decode(match.group(2), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("logo data is invalid") from exc
        if len(decoded) > 500_000:
            raise ValueError("logo must be smaller than 500 KB")
        try:
            with Image.open(io.BytesIO(decoded)) as image:
                width, height = image.size
                detected_format = str(image.format or "").lower()
                image.verify()
        except (OSError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            raise ValueError("logo data is not a valid image") from exc
        expected_format = {"png": "png", "jpeg": "jpeg", "webp": "webp"}[match.group(1)]
        if detected_format != expected_format:
            raise ValueError("logo content does not match its declared image type")
        if width > 4096 or height > 4096 or width * height > 16_000_000:
            raise ValueError("logo dimensions must not exceed 4096 px or 16 megapixels")
        return value


class StorageUpdate(BaseModel):
    data_root: str = Field(min_length=3, max_length=1000)
    downloads_root: str = Field(min_length=3, max_length=1000)
    data_action: str = Field(default="move", pattern="^(move|use)$")
    move_downloads: bool = True


class StorageBrowse(BaseModel):
    initial_path: str = Field(default="", max_length=1000)


class ThemeUpdate(BaseModel):
    theme: str = Field(
        pattern="^(brushstroke|genesis|flip7|rawblock|evreghen|ember|insightdeck|vercel|trustblue|zengrid)$"
    )
    version: int = Field(default=0, ge=0)


class EmailAccountUpdate(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=587, ge=1, le=65535)
    security: str = Field(default="starttls", pattern="^(starttls|ssl|none)$")
    username: str = Field(default="", max_length=320)
    password: str | None = Field(default=None, max_length=500)
    clear_password: bool = False
    from_email: str = Field(min_length=3, max_length=320)
    from_name: str = Field(default="", max_length=200)
    reply_to: str = Field(default="", max_length=320)


class OllamaModelRequest(BaseModel):
    model: str = Field(min_length=1, max_length=120)

    @field_validator("model")
    @classmethod
    def valid_model_name(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*(?::[A-Za-z0-9._-]+)?", value) or ".." in value:
            raise ValueError("enter a valid Ollama model tag such as qwen2.5:7b")
        return value


class SpaStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: dict[str, Any]) -> Response:
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                response = await super().get_response("index.html", scope)
            else:
                raise
        if response.status_code == 404:
            response = await super().get_response("index.html", scope)
        if response.media_type == "text/html":
            response.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response


def _settings_payload(repo: RunRepository) -> dict[str, Any]:
    stored = repo.app_settings()
    defaults = ScraperConfig(niche="businesses", location="London UK")
    repairs: dict[str, str] = {}
    provider = str(stored.get("model_provider") or "").strip()
    if provider not in {"ollama", "openai_compatible"}:
        provider = "ollama"
        repairs["model_provider"] = provider
    model_name = str(stored.get("model_name") or "").strip()
    if not model_name:
        model_name = defaults.model.split("/", 1)[-1]
        repairs["model_name"] = model_name
    endpoint = str(stored.get("model_endpoint") or "").strip().rstrip("/")
    if not _stored_endpoint_is_safe(endpoint):
        provider = "ollama"
        endpoint = defaults.ollama_base_url
        repairs.update({"model_provider": provider, "model_endpoint": endpoint})
    try:
        legacy_custom = json.loads(stored.get("custom_blocked_domains", "[]"))
        raw_blocked = (
            json.loads(stored["blocked_domains"])
            if "blocked_domains" in stored
            else [
                *DEFAULT_BLOCKED_DOMAINS,
                *legacy_custom,
            ]
        )
    except (json.JSONDecodeError, TypeError):
        raw_blocked = list(DEFAULT_BLOCKED_DOMAINS)
    blocked_domains = _sanitized_domains(raw_blocked)
    if not isinstance(raw_blocked, list) or blocked_domains != raw_blocked:
        repairs["blocked_domains"] = json.dumps(blocked_domains)
    workspace_name = _text_or_default(stored.get("workspace_name"), DEFAULT_WORKSPACE_NAME)
    workspace_subtitle = _text_or_default(
        stored.get("workspace_subtitle"), DEFAULT_WORKSPACE_SUBTITLE
    )
    if stored.get("workspace_name") != workspace_name:
        repairs["workspace_name"] = workspace_name
    if stored.get("workspace_subtitle") != workspace_subtitle:
        repairs["workspace_subtitle"] = workspace_subtitle
    theme = str(stored.get("theme") or "")
    if theme not in VALID_THEMES:
        theme = "brushstroke"
        repairs["theme"] = theme
    try:
        smtp_port = int(stored.get("smtp_port", "587") or 587)
        if not 1 <= smtp_port <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        smtp_port = 587
        repairs["smtp_port"] = "587"
    smtp_security = str(stored.get("smtp_security") or "starttls")
    if smtp_security not in {"starttls", "ssl", "none"}:
        smtp_security = "starttls"
        repairs["smtp_security"] = smtp_security
    if repairs:
        repo.repair_app_settings(
            {key: stored.get(key) for key in repairs},
            repairs,
        )
    prefix = "ollama" if provider == "ollama" else "oneapi"
    accounts, default_account_id = _email_accounts(stored)
    return {
        "model_provider": provider,
        "model_name": model_name,
        "default_model": f"{prefix}/{model_name}",
        "model_endpoint": endpoint,
        "ollama_base_url": endpoint,
        "api_key_configured": bool(stored.get("llm_api_key")),
        "blocked_domains": sorted(set(blocked_domains)),
        "workspace_name": workspace_name,
        "workspace_subtitle": workspace_subtitle,
        "logo_data_url": stored.get("logo_data_url", ""),
        "theme": theme,
        "smtp_host": stored.get("smtp_host", ""),
        "smtp_port": smtp_port,
        "smtp_security": smtp_security,
        "smtp_username": stored.get("smtp_username", ""),
        "smtp_password_configured": bool(stored.get("smtp_password")),
        "smtp_from_email": stored.get("smtp_from_email", ""),
        "smtp_from_name": stored.get("smtp_from_name", ""),
        "smtp_reply_to": stored.get("smtp_reply_to", ""),
        "email_accounts": [
            _public_email_account(account, account["id"] == default_account_id) for account in accounts
        ],
        "default_email_account_id": default_account_id,
        "email_configured": any(_email_account_ready(account) for account in accounts),
        "secret_errors": sorted(
            key.removesuffix("_unreadable")
            for key, value in stored.items()
            if key.endswith("_unreadable") and value == "true"
        ),
        "limits": {"max_results_per_query": 100, "max_sites": 500},
        "search_providers": ["hybrid", "osm_local", "auto", "brave", "ddgs"],
        "brave_configured": bool(defaults.brave_search_api_key),
    }


def _stored_endpoint_is_safe(value: str) -> bool:
    if not value.startswith(("http://", "https://")):
        return False
    parsed = urlparse(value)
    host = parsed.hostname or ""
    if parsed.scheme == "https":
        return bool(host)
    if host.lower() == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _sanitized_domains(values: Any) -> list[str]:
    if not isinstance(values, list):
        return list(DEFAULT_BLOCKED_DOMAINS)
    clean: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        domain = value.strip().lower().removeprefix("www.")
        if (
            re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?\.[a-z]{2,63}", domain)
            and domain not in clean
        ):
            clean.append(domain)
    return clean


def _storage_payload(app: FastAPI) -> dict[str, Any]:
    config = load_storage_config(app.state.storage_config_path, app.state.bootstrap_root)
    data_root = Path(config["data_root"])
    downloads_root = Path(config["downloads_root"]) if config["downloads_root"] else None
    active_data_root = app.state.database_path.parent.resolve()
    active_cache = Path(os.getenv("LEADROOM_CACHE_DIR", active_data_root / "cache")).resolve()
    active_browser = Path(os.getenv("PLAYWRIGHT_BROWSERS_PATH", config["browser_dir"])).resolve()
    configured_cache = Path(config["cache_dir"]).resolve()
    configured_browser = Path(config["browser_dir"]).resolve()
    database_path = data_root / "lead_scraper.db"

    def disk(path: Path) -> dict[str, int]:
        probe = path
        while not probe.exists() and probe.parent != probe:
            probe = probe.parent
        usage = shutil.disk_usage(probe)
        return {"free_bytes": usage.free, "total_bytes": usage.total}

    return {
        "data_root": str(data_root),
        "downloads_root": str(downloads_root or ""),
        "active_data_root": str(active_data_root),
        "database_path": str(database_path),
        "database_exists": database_path.exists(),
        "database_bytes": directory_size(database_path),
        "workspace_bytes": directory_size(data_root / "exports") + directory_size(database_path),
        "cache_dir": config["cache_dir"],
        "browser_dir": config["browser_dir"],
        "ollama_dir": config["ollama_dir"],
        "data_disk": disk(data_root),
        "downloads_disk": disk(downloads_root or configured_cache),
        "restart_required": (
            data_root.resolve() != active_data_root
            or configured_cache != active_cache
            or configured_browser != active_browser
        ),
        "ollama_restart_required": bool(config.get("ollama_restart_required", False)),
    }


def _email_accounts(stored: dict[str, str]) -> tuple[list[dict[str, Any]], str]:
    accounts: list[dict[str, Any]] = []
    try:
        raw = json.loads(stored.get("email_accounts", "[]"))
        if isinstance(raw, list):
            accounts = [dict(item) for item in raw if isinstance(item, dict) and item.get("id")]
    except (json.JSONDecodeError, TypeError):
        accounts = []
    sanitized_accounts: list[dict[str, Any]] = []
    for account in accounts:
        try:
            port = int(account.get("port", 587))
        except (TypeError, ValueError):
            continue
        security = str(account.get("security", "starttls"))
        if not 1 <= port <= 65535 or security not in {"starttls", "ssl", "none"}:
            continue
        sanitized_accounts.append({**account, "port": port, "security": security})
    accounts = sanitized_accounts
    if not accounts and stored.get("smtp_host") and stored.get("smtp_from_email"):
        try:
            legacy_port = int(stored.get("smtp_port", "587") or 587)
        except (TypeError, ValueError):
            legacy_port = 587
        accounts = [
            {
                "id": "legacy-default",
                "label": stored.get("smtp_from_name") or stored.get("smtp_from_email") or "Primary account",
                "host": stored.get("smtp_host", ""),
                "port": legacy_port,
                "security": stored.get("smtp_security", "starttls"),
                "username": stored.get("smtp_username", ""),
                "password": stored.get("smtp_password", ""),
                "from_email": stored.get("smtp_from_email", ""),
                "from_name": stored.get("smtp_from_name", ""),
                "reply_to": stored.get("smtp_reply_to", ""),
            }
        ]
    default_id = stored.get("default_email_account_id", "")
    if not any(account["id"] == default_id for account in accounts):
        default_id = str(accounts[0]["id"]) if accounts else ""
    return accounts, default_id


def _public_email_account(account: dict[str, Any], is_default: bool = False) -> dict[str, Any]:
    return {
        "id": str(account.get("id", "")),
        "label": str(account.get("label", "")),
        "host": str(account.get("host", "")),
        "port": int(account.get("port", 587)),
        "security": str(account.get("security", "starttls")),
        "username": str(account.get("username", "")),
        "password_configured": bool(account.get("password")),
        "from_email": str(account.get("from_email", "")),
        "from_name": str(account.get("from_name", "")),
        "reply_to": str(account.get("reply_to", "")),
        "is_default": is_default,
    }


def _email_account_config(account: dict[str, Any]) -> EmailDeliveryConfig:
    return EmailDeliveryConfig.from_settings(
        {
            "smtp_host": str(account.get("host", "")),
            "smtp_port": str(account.get("port", 587)),
            "smtp_security": str(account.get("security", "starttls")),
            "smtp_username": str(account.get("username", "")),
            "smtp_password": str(account.get("password", "")),
            "smtp_from_email": str(account.get("from_email", "")),
            "smtp_from_name": str(account.get("from_name", "")),
            "smtp_reply_to": str(account.get("reply_to", "")),
        }
    )


def _email_account_ready(account: dict[str, Any]) -> bool:
    try:
        _email_account_config(account)
    except (TypeError, ValueError):
        return False
    return True


def create_app(database_path: Path | None = None, frontend_dir: Path | None = None) -> FastAPI:
    database_path = database_path or Path(os.getenv("LEAD_SCRAPER_DATABASE", "data/lead_scraper.db"))
    app = FastAPI(title="Local Lead Scraper API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
    launch_token = os.getenv("LEADROOM_LAUNCH_TOKEN", "")

    @app.middleware("http")
    async def desktop_session(request: Request, call_next):
        if not launch_token or request.url.path == "/api/v1/health":
            return await call_next(request)
        supplied = request.query_params.get("launch_token", "")
        cookie = request.cookies.get("leadroom_session", "")
        authorized = bool(cookie and compare_digest(cookie, launch_token))
        bootstrapping = bool(supplied and compare_digest(supplied, launch_token))
        if request.url.path.startswith("/api/") and not authorized:
            return _problem(
                401,
                "Local session required",
                "This API request did not come from the active Leadroom session.",
                "Open Leadroom from the desktop application.",
            )
        if bootstrapping and request.method == "GET" and not request.url.path.startswith("/api/"):
            clean_params = [
                (key, value) for key, value in request.query_params.multi_items() if key != "launch_token"
            ]
            clean_url = request.url.replace_query_params(**dict(clean_params))
            response = RedirectResponse(str(clean_url), status_code=303)
        else:
            response = await call_next(request)
        if bootstrapping:
            response.set_cookie(
                "leadroom_session",
                launch_token,
                httponly=True,
                samesite="strict",
                secure=False,
                max_age=12 * 60 * 60,
            )
        return response

    app.state.database_path = database_path
    app.state.bootstrap_root = Path(os.getenv("LEADROOM_BOOTSTRAP_ROOT", str(database_path.parent))).resolve()
    app.state.storage_config_path = Path(
        os.getenv("LEADROOM_STORAGE_CONFIG", str(app.state.bootstrap_root / "storage.json"))
    ).resolve()
    app.state.choose_directory = None
    app.state.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="lead-worker")
    app.state.model_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="model-download")
    app.state.model_downloads: dict[str, dict[str, Any]] = {}
    app.state.model_download_futures: dict[str, Any] = {}
    app.state.model_download_clients: dict[str, httpx.Client] = {}
    app.state.model_download_lock = threading.RLock()
    app.state.ollama_catalog_cache: dict[str, dict[str, Any]] = {}
    app.state.outreach_send_jobs: dict[str, dict[str, Any]] = {}
    app.state.outreach_send_configs: dict[str, EmailDeliveryConfig] = {}
    app.state.outreach_send_lock = threading.RLock()
    app.state.shutting_down = threading.Event()
    app.state.discovery_jobs: dict[str, str] = {}
    app.state.enrichment_jobs: dict[str, str] = {}

    @app.on_event("shutdown")
    def shutdown_workers() -> None:
        app.state.shutting_down.set()
        with app.state.model_download_lock:
            for job in app.state.model_downloads.values():
                if job["status"] in {"queued", "downloading"}:
                    job["stop_requested"] = True
            download_clients = list(app.state.model_download_clients.values())
        for client in download_clients:
            client.close()
        queued_drafts: list[str] = []
        with app.state.outreach_send_lock:
            for job in app.state.outreach_send_jobs.values():
                if job["status"] in {"queued", "sending"}:
                    job["stop_requested"] = True
                    job["message"] = "Application is closing; sending will stop after the current email"
                    queued_drafts.extend(job.get("draft_ids", []))
        if queued_drafts:
            service = ComplianceService(app.state.database_path)
            try:
                service.release_queued(queued_drafts)
            finally:
                service.close()
        app.state.discovery_jobs.clear()
        app.state.enrichment_jobs.clear()
        app.state.model_executor.shutdown(wait=False, cancel_futures=True)
        app.state.executor.shutdown(wait=False, cancel_futures=True)

    def schedule_discovery(
        config: ScraperConfig, run_id: str, continuation: bool, source: str | None = None
    ) -> None:
        token = str(uuid.uuid4())
        app.state.discovery_jobs[run_id] = token
        future = app.state.executor.submit(
            _execute_discovery,
            config,
            run_id,
            continuation,
            source,
            lambda: app.state.discovery_jobs.get(run_id) == token,
        )
        future.add_done_callback(
            lambda _future: app.state.discovery_jobs.pop(run_id, None)
            if app.state.discovery_jobs.get(run_id) == token
            else None
        )

    def schedule_enrichment(config: ScraperConfig, run_id: str) -> None:
        token = str(uuid.uuid4())
        app.state.enrichment_jobs[run_id] = token
        future = app.state.executor.submit(
            _execute_run,
            config,
            run_id,
            lambda: app.state.enrichment_jobs.get(run_id) == token,
        )
        future.add_done_callback(
            lambda _future: app.state.enrichment_jobs.pop(run_id, None)
            if app.state.enrichment_jobs.get(run_id) == token
            else None
        )

    recovery = ComplianceService(database_path)
    try:
        recovery.recover_interrupted_deliveries()
    finally:
        recovery.close()

    def repository() -> RunRepository:
        return RunRepository(app.state.database_path)

    def ollama_runtime() -> tuple[str, str]:
        repo = repository()
        try:
            current = _settings_payload(repo)
        finally:
            repo.engine.dispose()
        if current["model_provider"] != "ollama":
            raise ValueError("Switch the model provider to Ollama before managing local models")
        return str(current["model_endpoint"]).rstrip("/"), str(current["model_name"])

    def ollama_models(endpoint: str) -> list[dict[str, Any]]:
        try:
            response = httpx.get(f"{endpoint}/api/tags", timeout=8, follow_redirects=True)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ValueError(f"Ollama could not be reached: {exc}") from exc
        models = payload.get("models", []) if isinstance(payload, dict) else []
        return [model for model in models if isinstance(model, dict)]

    def assert_model_ready(config: ScraperConfig) -> None:
        if not config.model.startswith("ollama/"):
            return
        selected = config.model.split("/", 1)[-1]
        installed = {
            str(item.get("name") or item.get("model"))
            for item in ollama_models(config.ollama_base_url.rstrip("/"))
            if item.get("name") or item.get("model")
        }
        aliases = {selected, f"{selected}:latest" if ":" not in selected else selected}
        if not installed.intersection(aliases):
            raise ValueError(
                f"The selected Ollama model '{selected}' is not installed. "
                "Open Settings to download or select an installed model."
            )

    app.state.model_validator = assert_model_ready

    def ollama_catalog(query: str) -> list[dict[str, Any]]:
        cache_key = query.strip().lower()
        cached = app.state.ollama_catalog_cache.get(cache_key)
        if cached and time.monotonic() - cached["created_at"] < 600:
            return cached["models"]
        try:
            response = httpx.get(
                "https://ollama.com/search",
                params={"q": query.strip()} if query.strip() else None,
                timeout=12,
                follow_redirects=True,
                verify=ssl.create_default_context(),
                headers={"User-Agent": "Leadroom/0.1 (+local Ollama model picker)"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ValueError(f"The Ollama model catalog could not be reached: {exc}") from exc

        models: list[dict[str, Any]] = []
        seen: set[str] = set()
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.select('a[href^="/library/"]'):
            heading = link.find("h2")
            if not heading:
                continue
            family = heading.get_text(" ", strip=True)
            if not family or family in seen:
                continue
            seen.add(family)
            summary_node = link.find("p")
            badges = [
                item.get_text(" ", strip=True).lower() for item in link.select("div.flex.flex-wrap span")
            ]
            known_capabilities = {"vision", "tools", "thinking", "embedding", "audio"}
            capabilities = [badge for badge in badges if badge in known_capabilities]
            variants = [badge for badge in badges if re.fullmatch(r"(?:e?\d+(?:\.\d+)?b|latest)", badge)]
            cloud = "cloud" in badges
            models.append(
                {
                    "name": family,
                    "family": family,
                    "description": summary_node.get_text(" ", strip=True) if summary_node else "",
                    "capabilities": capabilities,
                    "variants": variants,
                    "cloud": cloud,
                    "local": bool(variants) or not cloud,
                    "url": f"https://ollama.com/library/{family}",
                }
            )
            if len(models) >= 30:
                break
        app.state.ollama_catalog_cache[cache_key] = {"created_at": time.monotonic(), "models": models}
        return models

    def pull_ollama_model(job_id: str, endpoint: str, model: str) -> None:
        job = app.state.model_downloads[job_id]
        client: httpx.Client | None = None
        try:
            timeout = httpx.Timeout(connect=10, read=60, write=30, pool=10)
            client = httpx.Client(timeout=timeout)
            with app.state.model_download_lock:
                app.state.model_download_clients[job_id] = client
            with client.stream(
                "POST",
                f"{endpoint}/api/pull",
                json={"model": model, "stream": True},
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if job.get("stop_requested") or app.state.shutting_down.is_set():
                        job.update(
                            {
                                "status": "cancelled",
                                "message": "Download cancelled",
                                "updated_at": datetime.now().astimezone().isoformat(),
                            }
                        )
                        break
                    if not line:
                        continue
                    update = json.loads(line)
                    if update.get("error"):
                        raise ValueError(str(update["error"]))
                    total = int(update.get("total") or job.get("total") or 0)
                    completed = int(update.get("completed") or job.get("completed") or 0)
                    job.update(
                        {
                            "status": "downloading",
                            "message": str(update.get("status") or "Downloading model"),
                            "total": total,
                            "completed": completed,
                            "percent": min(100, round(completed / total * 100)) if total else 0,
                            "updated_at": datetime.now().astimezone().isoformat(),
                        }
                    )
                    if update.get("status") == "success":
                        job.update({"status": "completed", "message": "Model installed", "percent": 100})
            if job["status"] not in {"completed", "cancelled"}:
                job.update({"status": "completed", "message": "Model installed", "percent": 100})
        except Exception as exc:
            if job.get("stop_requested") or app.state.shutting_down.is_set():
                job.update(
                    {
                        "status": "cancelled",
                        "message": "Download cancelled",
                        "error": "",
                        "updated_at": datetime.now().astimezone().isoformat(),
                    }
                )
            else:
                job.update(
                    {
                        "status": "failed",
                        "message": "Download failed",
                        "error": str(exc) or type(exc).__name__,
                        "updated_at": datetime.now().astimezone().isoformat(),
                    }
                )
        finally:
            if client is not None:
                client.close()
            with app.state.model_download_lock:
                app.state.model_download_clients.pop(job_id, None)
                app.state.model_download_futures.pop(job_id, None)

    @app.exception_handler(KeyError)
    async def not_found(_request: Request, exc: KeyError) -> JSONResponse:
        return _problem(404, "Resource not found", str(exc), "Check the run ID and try again.")

    @app.exception_handler(ValueError)
    async def invalid_state(_request: Request, exc: ValueError) -> JSONResponse:
        return _problem(409, "Invalid operation", str(exc), "Refresh the run state before retrying.")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return _problem(
            422,
            "Invalid request",
            str(exc.errors()),
            "Correct the highlighted fields and submit again.",
        )

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        return _problem(
            500,
            "Search could not be started",
            str(exc) or type(exc).__name__,
            "Retry the search. If it fails again, open the failed run diagnostics.",
        )

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        repo = repository()
        try:
            integrity = repo.integrity_check()
        finally:
            repo.engine.dispose()
        if integrity != "ok":
            raise HTTPException(status_code=503, detail="Database integrity check failed")
        return {"status": "ok", "database": integrity}

    @app.get("/api/v1/runs")
    def list_runs(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
        repo = repository()
        try:
            repo.stop_stale_searches(_search_stale_seconds())
            return repo.list_runs(limit)
        finally:
            repo.engine.dispose()

    @app.get("/api/v1/settings")
    def settings() -> dict[str, Any]:
        repo = repository()
        try:
            return _settings_payload(repo)
        finally:
            repo.engine.dispose()

    @app.get("/api/v1/settings/storage")
    def storage_settings() -> dict[str, Any]:
        return _storage_payload(app)

    @app.post("/api/v1/settings/storage/browse")
    def browse_storage(payload: StorageBrowse) -> dict[str, str]:
        chooser = app.state.choose_directory
        if chooser is None:
            raise ValueError(
                "Folder browsing is available in the Leadroom desktop window. You can also type an absolute path."
            )
        return {"path": chooser(payload.initial_path)}

    @app.put("/api/v1/settings/storage")
    def update_storage(payload: StorageUpdate) -> dict[str, Any]:
        current = load_storage_config(app.state.storage_config_path, app.state.bootstrap_root)
        downloads_changed = (
            Path(payload.downloads_root).expanduser().resolve()
            != Path(current["downloads_root"] or current["cache_dir"]).expanduser().resolve()
        )
        schedule_storage_change(
            app.state.storage_config_path,
            app.state.bootstrap_root,
            app.state.database_path.parent,
            payload.data_root,
            payload.downloads_root,
            payload.data_action,
            payload.move_downloads,
        )
        if downloads_changed:
            stored = json.loads(app.state.storage_config_path.read_text(encoding="utf-8"))
            stored["ollama_restart_required"] = True
            save_storage_config(app.state.storage_config_path, stored)
        return _storage_payload(app)

    @app.put("/api/v1/settings")
    def update_settings(payload: SettingsUpdate) -> dict[str, Any]:
        values = {
            "model_provider": payload.model_provider,
            "model_name": payload.model_name,
            "model_endpoint": payload.model_endpoint,
            "blocked_domains": json.dumps(payload.blocked_domains),
            "workspace_name": payload.workspace_name,
            "workspace_subtitle": payload.workspace_subtitle,
            "logo_data_url": payload.logo_data_url,
        }
        repo = repository()
        try:
            previous = repo.app_settings()
            if "theme" not in previous:
                values["theme"] = payload.theme
            endpoint_changed = previous.get("model_endpoint", "") != payload.model_endpoint
            provider_changed = previous.get("model_provider", "ollama") != payload.model_provider
            if payload.clear_api_key or ((endpoint_changed or provider_changed) and not payload.api_key):
                values["llm_api_key"] = ""
            elif payload.api_key:
                values["llm_api_key"] = payload.api_key.strip()
            smtp_fields = {
                "smtp_host": payload.smtp_host,
                "smtp_port": str(payload.smtp_port) if payload.smtp_port is not None else None,
                "smtp_security": payload.smtp_security,
                "smtp_username": payload.smtp_username,
                "smtp_from_email": payload.smtp_from_email,
                "smtp_from_name": payload.smtp_from_name,
                "smtp_reply_to": payload.smtp_reply_to,
            }
            values.update(
                {key: str(value).strip() for key, value in smtp_fields.items() if value is not None}
            )
            smtp_identity_changed = any(
                previous.get(key, "") != str(values.get(key, ""))
                for key in ("smtp_host", "smtp_port", "smtp_security", "smtp_username")
                if key in values
            )
            if payload.clear_smtp_password or (smtp_identity_changed and not payload.smtp_password):
                values["smtp_password"] = ""
            elif payload.smtp_password:
                values["smtp_password"] = payload.smtp_password
            repo.update_app_settings(values)
            return _settings_payload(repo)
        finally:
            repo.engine.dispose()

    @app.patch("/api/v1/settings/theme")
    def update_theme(payload: ThemeUpdate) -> dict[str, Any]:
        repo = repository()
        try:
            repo.update_theme_setting(payload.theme, payload.version)
            return _settings_payload(repo)
        finally:
            repo.engine.dispose()

    def email_accounts_payload(repo: RunRepository) -> dict[str, Any]:
        accounts, default_id = _email_accounts(repo.app_settings())
        return {
            "accounts": [_public_email_account(account, account["id"] == default_id) for account in accounts],
            "default_account_id": default_id,
        }

    @app.get("/api/v1/settings/email-accounts")
    def list_email_accounts() -> dict[str, Any]:
        repo = repository()
        try:
            return email_accounts_payload(repo)
        finally:
            repo.engine.dispose()

    @app.post("/api/v1/settings/email-accounts", status_code=201)
    def create_email_account(payload: EmailAccountUpdate) -> dict[str, Any]:
        repo = repository()
        try:
            accounts, default_id = _email_accounts(repo.app_settings())
            account = payload.model_dump(exclude={"clear_password"})
            account["id"] = uuid.uuid4().hex[:12]
            account["password"] = payload.password or ""
            _email_account_config(account)
            accounts.append(account)
            default_id = default_id or account["id"]
            repo.update_app_settings(
                {
                    "email_accounts": json.dumps(accounts),
                    "default_email_account_id": default_id,
                }
            )
            return email_accounts_payload(repo)
        finally:
            repo.engine.dispose()

    @app.put("/api/v1/settings/email-accounts/{account_id}")
    def update_email_account(account_id: str, payload: EmailAccountUpdate) -> dict[str, Any]:
        repo = repository()
        try:
            accounts, default_id = _email_accounts(repo.app_settings())
            account = next((item for item in accounts if item["id"] == account_id), None)
            if account is None:
                raise KeyError(f"Email account {account_id} was not found")
            password = (
                ""
                if payload.clear_password
                else payload.password
                if payload.password is not None
                else account.get("password", "")
            )
            account.update(payload.model_dump(exclude={"password", "clear_password"}))
            account["password"] = password
            _email_account_config(account)
            repo.update_app_settings(
                {
                    "email_accounts": json.dumps(accounts),
                    "default_email_account_id": default_id,
                }
            )
            return email_accounts_payload(repo)
        finally:
            repo.engine.dispose()

    @app.delete("/api/v1/settings/email-accounts/{account_id}")
    def delete_email_account(account_id: str) -> dict[str, Any]:
        repo = repository()
        try:
            accounts, default_id = _email_accounts(repo.app_settings())
            if not any(item["id"] == account_id for item in accounts):
                raise KeyError(f"Email account {account_id} was not found")
            accounts = [item for item in accounts if item["id"] != account_id]
            if default_id == account_id:
                default_id = str(accounts[0]["id"]) if accounts else ""
            repo.update_app_settings(
                {
                    "email_accounts": json.dumps(accounts),
                    "default_email_account_id": default_id,
                }
            )
            return email_accounts_payload(repo)
        finally:
            repo.engine.dispose()

    @app.patch("/api/v1/settings/email-accounts/{account_id}/default")
    def set_default_email_account(account_id: str) -> dict[str, Any]:
        repo = repository()
        try:
            accounts, _default_id = _email_accounts(repo.app_settings())
            if not any(item["id"] == account_id for item in accounts):
                raise KeyError(f"Email account {account_id} was not found")
            repo.update_app_settings({"default_email_account_id": account_id})
            return email_accounts_payload(repo)
        finally:
            repo.engine.dispose()

    @app.post("/api/v1/settings/email-accounts/{account_id}/test")
    def test_saved_email_account(account_id: str) -> dict[str, Any]:
        repo = repository()
        try:
            accounts, _default_id = _email_accounts(repo.app_settings())
            account = next((item for item in accounts if item["id"] == account_id), None)
            if account is None:
                raise KeyError(f"Email account {account_id} was not found")
            result = SMTPEmailProvider(_email_account_config(account)).test_connection()
            return {**result, "account_id": account_id, "label": account["label"]}
        finally:
            repo.engine.dispose()

    @app.post("/api/v1/settings/test-model")
    def test_model_connection() -> dict[str, Any]:
        repo = repository()
        try:
            current = _settings_payload(repo)
            secret = repo.app_settings().get("llm_api_key", "")
        finally:
            repo.engine.dispose()
        endpoint = str(current["model_endpoint"]).rstrip("/")
        model_name = str(current["model_name"])
        if current["model_provider"] == "ollama":
            url = f"{endpoint}/api/tags"
            headers: dict[str, str] = {}
        else:
            url = f"{endpoint}/models"
            headers = {"Authorization": f"Bearer {secret}"} if secret else {}
            if not secret:
                raise ValueError("Add an API key before testing this provider")
        try:
            response = httpx.get(url, headers=headers, timeout=8, follow_redirects=True)
            response.raise_for_status()
            inventory = response.json()
        except httpx.HTTPError as exc:
            raise ValueError(f"Model endpoint could not be reached: {exc}") from exc
        except ValueError as exc:
            raise ValueError("Model endpoint returned an invalid inventory response") from exc
        if current["model_provider"] == "ollama":
            models = inventory.get("models", []) if isinstance(inventory, dict) else []
            installed = {
                str(item.get("name") or item.get("model"))
                for item in models
                if isinstance(item, dict) and (item.get("name") or item.get("model"))
            }
            aliases = {model_name, f"{model_name}:latest" if ":" not in model_name else model_name}
            if not installed.intersection(aliases):
                raise ValueError(f"The selected model '{model_name}' is not installed")
            generation_url = f"{endpoint}/api/generate"
            generation_payload = {"model": model_name, "prompt": "Reply with OK.", "stream": False}
        else:
            models = inventory.get("data", []) if isinstance(inventory, dict) else []
            installed = {
                str(item.get("id"))
                for item in models
                if isinstance(item, dict) and item.get("id")
            }
            if model_name not in installed:
                raise ValueError(f"The selected model '{model_name}' is not available")
            generation_url = f"{endpoint}/chat/completions"
            generation_payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "max_tokens": 8,
            }
        try:
            generated = httpx.post(
                generation_url,
                headers=headers,
                json=generation_payload,
                timeout=20,
                follow_redirects=True,
            )
            generated.raise_for_status()
            generated_payload = generated.json()
        except httpx.HTTPError as exc:
            raise ValueError(f"The selected model could not generate a response: {exc}") from exc
        except ValueError as exc:
            raise ValueError("The selected model returned an invalid generation response") from exc
        if current["model_provider"] == "ollama":
            usable = bool(
                isinstance(generated_payload, dict)
                and str(generated_payload.get("response") or "").strip()
            )
        else:
            choices = generated_payload.get("choices", []) if isinstance(generated_payload, dict) else []
            usable = bool(
                choices
                and isinstance(choices[0], dict)
                and str((choices[0].get("message") or {}).get("content") or "").strip()
            )
        if not usable:
            raise ValueError("The selected model returned an empty generation response")
        return {"status": "ok", "provider": current["model_provider"], "model": current["default_model"]}

    @app.post("/api/v1/settings/test-email")
    def test_email_connection() -> dict[str, Any]:
        repo = repository()
        try:
            accounts, default_id = _email_accounts(repo.app_settings())
            account = next((item for item in accounts if item["id"] == default_id), None)
            config = (
                _email_account_config(account)
                if account
                else EmailDeliveryConfig.from_settings(repo.app_settings())
            )
        finally:
            repo.engine.dispose()
        return SMTPEmailProvider(config).test_connection()

    @app.get("/api/v1/settings/ollama/models")
    def list_ollama_models() -> dict[str, Any]:
        endpoint, selected = ollama_runtime()
        models = ollama_models(endpoint)
        return {"status": "ok", "endpoint": endpoint, "selected_model": selected, "models": models}

    @app.get("/api/v1/settings/ollama/catalog")
    def search_ollama_catalog(q: str = Query(default="", max_length=80)) -> dict[str, Any]:
        endpoint, selected = ollama_runtime()
        installed_models = ollama_models(endpoint)
        installed_names = sorted(
            {
                str(item.get("name") or item.get("model"))
                for item in installed_models
                if item.get("name") or item.get("model")
            }
        )
        return {
            "status": "ok",
            "selected_model": selected,
            "installed": installed_names,
            "models": ollama_catalog(q),
        }

    @app.patch("/api/v1/settings/ollama/model")
    def select_ollama_model(payload: OllamaModelRequest) -> dict[str, Any]:
        endpoint, _selected = ollama_runtime()
        installed = {
            str(item.get("name") or item.get("model"))
            for item in ollama_models(endpoint)
            if item.get("name") or item.get("model")
        }
        aliases = {payload.model, f"{payload.model}:latest" if ":" not in payload.model else payload.model}
        if not installed.intersection(aliases):
            raise ValueError("Download this model before selecting it")
        repo = repository()
        try:
            repo.update_app_settings({"model_name": payload.model})
            return _settings_payload(repo)
        finally:
            repo.engine.dispose()

    @app.post("/api/v1/settings/ollama/pull", status_code=202)
    def start_ollama_pull(payload: OllamaModelRequest) -> dict[str, Any]:
        endpoint, _selected = ollama_runtime()
        with app.state.model_download_lock:
            if app.state.shutting_down.is_set():
                raise ValueError("The application is shutting down")
            active = next(
                (
                    job
                    for job in app.state.model_downloads.values()
                    if job["model"] == payload.model
                    and job["status"] in {"queued", "downloading"}
                ),
                None,
            )
            if active:
                return active
            job_id = uuid.uuid4().hex
            job = {
                "id": job_id,
                "model": payload.model,
                "status": "queued",
                "message": "Waiting to download",
                "completed": 0,
                "total": 0,
                "percent": 0,
                "error": "",
                "stop_requested": False,
                "updated_at": datetime.now().astimezone().isoformat(),
            }
            app.state.model_downloads[job_id] = job
            try:
                future = app.state.model_executor.submit(
                    pull_ollama_model, job_id, endpoint, payload.model
                )
            except RuntimeError:
                app.state.model_downloads.pop(job_id, None)
                raise ValueError("The application is shutting down") from None
            app.state.model_download_futures[job_id] = future
            return job

    @app.get("/api/v1/settings/ollama/pulls/{job_id}")
    def ollama_pull_status(job_id: str) -> dict[str, Any]:
        job = app.state.model_downloads.get(job_id)
        if not job:
            raise KeyError(f"Model download {job_id} was not found")
        return job

    @app.post("/api/v1/settings/ollama/pulls/{job_id}/cancel")
    def cancel_ollama_pull(job_id: str) -> dict[str, Any]:
        client: httpx.Client | None = None
        with app.state.model_download_lock:
            job = app.state.model_downloads.get(job_id)
            if not job:
                raise KeyError(f"Model download {job_id} was not found")
            if job["status"] not in {"queued", "downloading"}:
                raise ValueError(f"Cannot cancel a model download in {job['status']} state")
            job["stop_requested"] = True
            future = app.state.model_download_futures.get(job_id)
            if future is not None and future.cancel():
                app.state.model_download_futures.pop(job_id, None)
                job.update(
                    {
                        "status": "cancelled",
                        "message": "Download cancelled",
                        "updated_at": datetime.now().astimezone().isoformat(),
                    }
                )
            else:
                job["message"] = "Cancelling download"
                client = app.state.model_download_clients.get(job_id)
        if client is not None:
            client.close()
        return job

    @app.post("/api/v1/settings/ollama/benchmark")
    def benchmark_ollama_model(payload: OllamaModelRequest) -> dict[str, Any]:
        endpoint, _selected = ollama_runtime()
        installed = {str(item.get("name") or item.get("model")) for item in ollama_models(endpoint)}
        if payload.model not in installed and f"{payload.model}:latest" not in installed:
            raise ValueError("Download this model before testing it")
        schema = LeadExtraction.model_json_schema()
        benchmark_required = {
            "business_name",
            "generic_email",
            "phone",
            "city_or_area",
            "services",
        }
        prompt = (
            "Extract business lead data from this website HTML. Return only the requested structured "
            "data and leave fields blank when the page does not provide evidence.\n\n"
            "<html><head><title>Bright Smile Dental Clinic</title></head><body>"
            "<main><h1>Bright Smile Dental Clinic</h1><p>Dental implants and dental hygiene "
            "appointments in London.</p><a href='mailto:hello@brightsmile.example'>Email our team</a>"
            "<a href='tel:02079460123'>020 7946 0123</a></main></body></html>"
        )
        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{endpoint}/api/generate",
                json={
                    "model": payload.model,
                    "prompt": prompt,
                    "format": schema,
                    "stream": False,
                    "options": {"temperature": 0, "num_predict": 220},
                },
                timeout=120,
                follow_redirects=True,
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("Ollama returned a non-object response")
            raw_extracted = json.loads(result.get("response", ""))
            extracted = LeadExtraction.model_validate(raw_extracted).model_dump()
        except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"The model could not complete the extraction benchmark: {exc}") from exc
        duration = round(time.perf_counter() - started, 2)
        services = " ".join(str(item).lower() for item in extracted.get("services", []) if item)
        phone_digits = re.sub(r"\D", "", str(extracted.get("phone", "")))
        checks = [
            {
                "label": "Valid structured output",
                "passed": all(key in raw_extracted for key in benchmark_required),
                "points": 2,
            },
            {
                "label": "Business name",
                "passed": "bright smile" in str(extracted.get("business_name", "")).lower(),
                "points": 2,
            },
            {
                "label": "Email accuracy",
                "passed": str(extracted.get("generic_email", "")).lower() == "hello@brightsmile.example",
                "points": 2,
            },
            {"label": "Phone accuracy", "passed": phone_digits.endswith("02079460123"), "points": 1},
            {
                "label": "Location accuracy",
                "passed": "london" in str(extracted.get("city_or_area", "")).lower(),
                "points": 1,
            },
            {
                "label": "Services accuracy",
                "passed": "implant" in services and ("hygiene" in services or "hygien" in services),
                "points": 2,
            },
        ]
        score = sum(item["points"] for item in checks if item["passed"])
        eval_count = int(result.get("eval_count") or 0)
        eval_duration = int(result.get("eval_duration") or 0)
        tokens_per_second = (
            round(eval_count / (eval_duration / 1_000_000_000), 1) if eval_count and eval_duration else None
        )
        verdict = "recommended" if score >= 8 else "usable" if score >= 6 else "not_recommended"
        return {
            "model": payload.model,
            "score": score,
            "verdict": verdict,
            "duration_seconds": duration,
            "tokens_per_second": tokens_per_second,
            "checks": checks,
            "sample": extracted,
        }

    @app.get("/api/v1/local-data/status")
    def local_data_status() -> dict[str, Any]:
        return LocalDataService().status()

    @app.get("/api/v1/local-data/preview")
    def local_data_preview(
        niche: str = Query(min_length=2, max_length=120),
        location: str = Query(min_length=1, max_length=120),
        limit: int = Query(default=8, ge=1, le=25),
    ) -> dict[str, Any]:
        service = LocalDataService()
        status = service.status()
        if not status["ready"]:
            raise ValueError(status["message"])
        return service.preview(niche, location, limit)

    @app.post("/api/v1/local-data/update", status_code=202)
    def local_data_update() -> dict[str, str]:
        return LocalDataService().request_update()

    @app.get("/api/v1/repository")
    def list_repository_leads() -> dict[str, Any]:
        repo = repository()
        try:
            leads = repo.list_repository_leads()
            return {"count": len(leads), "leads": leads}
        finally:
            repo.engine.dispose()

    @app.post("/api/v1/repository/import")
    def import_repository_leads(payload: RepositoryImport) -> dict[str, int]:
        repo = repository()
        try:
            return repo.import_repository_leads(payload.run_id, payload.domains)
        finally:
            repo.engine.dispose()

    @app.get("/api/v1/repository/export")
    def export_repository(format: str = Query(pattern="^(json|csv)$")) -> Response:
        repo = repository()
        try:
            leads = repo.list_repository_leads()
        finally:
            repo.engine.dispose()
        if not leads:
            raise KeyError(f"Repository export is not available yet: {format}")
        filename = _download_filename("lead_repository", format)
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        if format == "json":
            content = json.dumps({"count": len(leads), "leads": leads}, ensure_ascii=False, indent=2)
            return Response(content, media_type="application/json", headers=headers)
        fields = [
            *LEAD_FIELDS,
            "niches",
            "locations",
            "sources",
            "source_run_ids",
            "created_at",
            "updated_at",
        ]
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for lead in leads:
            writer.writerow({key: _csv_value(lead.get(key, "")) for key in fields})
        return Response("\ufeff" + stream.getvalue(), media_type="text/csv", headers=headers)

    @app.post("/api/v1/repository/collections/merge")
    def merge_repository_collections(payload: RepositoryCollectionMerge) -> dict[str, Any]:
        repo = repository()
        try:
            return repo.merge_repository_collections(payload.sources, payload.target)
        finally:
            repo.engine.dispose()

    @app.delete("/api/v1/repository/collections/{name}")
    def delete_repository_collection(name: str) -> dict[str, Any]:
        repo = repository()
        try:
            return repo.delete_repository_collection(name)
        finally:
            repo.engine.dispose()

    @app.delete("/api/v1/repository/{domain}")
    def delete_repository_lead(domain: str) -> dict[str, str]:
        repo = repository()
        try:
            return repo.delete_repository_lead(domain)
        finally:
            repo.engine.dispose()

    @app.patch("/api/v1/repository/{domain}")
    def update_repository_lead(domain: str, payload: RepositoryLeadUpdate) -> dict[str, Any]:
        repo = repository()
        try:
            changes = payload.model_dump(exclude_unset=True)
            collection = changes.pop("collection", None)
            if collection is not None:
                cleaned_collection = collection.strip()
                if not cleaned_collection:
                    raise ValueError("Collection name cannot be blank")
                changes["niches"] = [cleaned_collection]
            return repo.update_repository_lead(domain, changes)
        finally:
            repo.engine.dispose()

    @app.get("/api/v1/discovery/history")
    def discovery_history(
        niche: str = Query(min_length=1, max_length=120),
        location: str = Query(min_length=1, max_length=120),
    ) -> dict[str, Any]:
        repo = repository()
        try:
            return repo.market_history(niche, location)
        finally:
            repo.engine.dispose()

    def compliance() -> ComplianceService:
        return ComplianceService(app.state.database_path)

    def process_outreach_send(job_id: str, draft_ids: list[str]) -> None:
        job = app.state.outreach_send_jobs[job_id]
        service = compliance()
        try:
            config = app.state.outreach_send_configs.get(job_id)
            if config is None:
                raise ValueError("The email account snapshot is no longer available")
            provider = SMTPEmailProvider(config)
            job["status"] = "sending"
            for index, draft_id in enumerate(draft_ids):
                if job.get("stop_requested") or app.state.shutting_down.is_set():
                    service.release_queued(draft_ids[index:])
                    job["status"] = "stopped"
                    job["message"] = "Sending stopped. Remaining drafts returned to approved."
                    break
                job["current_draft_id"] = draft_id
                accepted_by_smtp = False
                message_id = SMTPEmailProvider.new_message_id(provider.config.from_email)
                try:
                    payload = service.delivery_payload(draft_id)
                    service.mark_delivery_started(draft_id, message_id)
                    message_id = provider.send(
                        payload["recipient"],
                        payload["subject"],
                        payload["body"],
                        message_id=message_id,
                    )
                    accepted_by_smtp = True
                    try:
                        service.complete_delivery(draft_id, "sent", provider_message_id=message_id)
                    except Exception as persist_error:
                        service.mark_delivery_uncertain(draft_id, message_id, str(persist_error))
                        job["failed"] += 1
                        job["results"].append(
                            {"draft_id": draft_id, "status": "uncertain", "error": str(persist_error)}
                        )
                        job["completed"] += 1
                        job["percent"] = round(job["completed"] / job["total"] * 100)
                        continue
                    job["sent"] += 1
                    job["results"].append({"draft_id": draft_id, "status": "sent", "error": ""})
                except DeliveryUncertainError as exc:
                    service.mark_delivery_uncertain(draft_id, message_id, str(exc))
                    job["failed"] += 1
                    job["results"].append({"draft_id": draft_id, "status": "uncertain", "error": str(exc)})
                except Exception as exc:
                    if not accepted_by_smtp:
                        service.complete_delivery(draft_id, "failed", error=str(exc))
                    job["failed"] += 1
                    job["results"].append(
                        {
                            "draft_id": draft_id,
                            "status": "uncertain" if accepted_by_smtp else "failed",
                            "error": str(exc),
                        }
                    )
                job["completed"] += 1
                job["percent"] = round(job["completed"] / job["total"] * 100)
            else:
                job["status"] = "completed"
                job["message"] = f"Sent {job['sent']} of {job['total']} emails."
        except Exception as exc:
            service.release_queued(draft_ids)
            job["status"] = "failed"
            job["message"] = str(exc)
        finally:
            job["current_draft_id"] = ""
            job["updated_at"] = datetime.now().astimezone().isoformat()
            app.state.outreach_send_configs.pop(job_id, None)
            service.close()

    @app.get("/api/v1/compliance/suppressions")
    def list_suppressions() -> list[dict[str, Any]]:
        service = compliance()
        try:
            return service.list_suppressions()
        finally:
            service.close()

    @app.post("/api/v1/compliance/suppressions", status_code=201)
    def add_suppression(payload: SuppressionCreate) -> dict[str, Any]:
        service = compliance()
        try:
            return service.add_suppression(payload.value, payload.kind, payload.reason)
        finally:
            service.close()

    @app.get("/api/v1/outreach/drafts")
    def list_outreach_drafts(run_id: str | None = None) -> list[dict[str, Any]]:
        service = compliance()
        try:
            return service.list_drafts(run_id)
        finally:
            service.close()

    @app.post("/api/v1/outreach/drafts", status_code=201)
    def create_outreach_draft(payload: OutreachDraftCreate) -> dict[str, Any]:
        service = compliance()
        try:
            return service.create_draft(**payload.model_dump())
        finally:
            service.close()

    @app.post("/api/v1/outreach/preflight")
    def outreach_preflight(payload: OutreachPreflight) -> dict[str, Any]:
        service = compliance()
        try:
            return service.preflight_run(payload.run_id, payload.domains)
        finally:
            service.close()

    @app.post("/api/v1/outreach/drafts/bulk", status_code=201)
    def create_outreach_drafts_bulk(payload: OutreachBulkCreate) -> dict[str, Any]:
        service = compliance()
        try:
            values = payload.model_dump(exclude={"domain", "domains"})
            return service.create_drafts_bulk(domains=payload.domains, **values)
        finally:
            service.close()

    @app.post("/api/v1/outreach/drafts/approve-bulk")
    def approve_outreach_drafts_bulk(payload: OutreachBulkApproval) -> dict[str, Any]:
        service = compliance()
        try:
            values = payload.model_dump(exclude={"draft_ids"})
            return service.approve_drafts_bulk(payload.draft_ids, **values)
        finally:
            service.close()

    @app.post("/api/v1/outreach/drafts/{draft_id}/approve")
    def approve_outreach_draft(draft_id: str, payload: OutreachApproval) -> dict[str, Any]:
        service = compliance()
        try:
            return service.approve_draft(draft_id, **payload.model_dump())
        finally:
            service.close()

    @app.post("/api/v1/outreach/send", status_code=202)
    def send_outreach(payload: OutreachSend) -> dict[str, Any]:
        with app.state.outreach_send_lock:
            if app.state.shutting_down.is_set():
                raise ValueError("The application is shutting down")
            active = next(
                (
                    job
                    for job in app.state.outreach_send_jobs.values()
                    if job["status"] in {"queued", "sending"}
                ),
                None,
            )
            if active:
                raise ValueError("Another outreach send job is already active")
            repo = repository()
            try:
                accounts, default_id = _email_accounts(repo.app_settings())
            finally:
                repo.engine.dispose()
            account_id = payload.email_account_id or default_id
            account = next((item for item in accounts if item["id"] == account_id), None)
            if account is None:
                raise ValueError("Select a configured email account before sending")
            config = _email_account_config(account)
            service = compliance()
            try:
                service.validate_delivery_account(
                    payload.draft_ids,
                    {config.from_email, config.reply_to},
                )
                draft_ids = service.queue_deliveries(payload.draft_ids)
            finally:
                service.close()
            job_id = uuid.uuid4().hex
            job = {
                "id": job_id,
                "status": "queued",
                "message": "Waiting to send",
                "total": len(draft_ids),
                "completed": 0,
                "sent": 0,
                "failed": 0,
                "percent": 0,
                "current_draft_id": "",
                "email_account_id": account_id,
                "email_account_label": account.get("label", ""),
                "from_email": account.get("from_email", ""),
                "stop_requested": False,
                "draft_ids": draft_ids,
                "results": [],
                "updated_at": datetime.now().astimezone().isoformat(),
            }
            app.state.outreach_send_jobs[job_id] = job
            app.state.outreach_send_configs[job_id] = config
            try:
                app.state.executor.submit(process_outreach_send, job_id, draft_ids)
            except RuntimeError:
                app.state.outreach_send_jobs.pop(job_id, None)
                app.state.outreach_send_configs.pop(job_id, None)
                service = compliance()
                try:
                    service.release_queued(draft_ids)
                finally:
                    service.close()
                raise ValueError("The application is shutting down") from None
            return job

    @app.get("/api/v1/outreach/send/{job_id}")
    def outreach_send_status(job_id: str) -> dict[str, Any]:
        job = app.state.outreach_send_jobs.get(job_id)
        if not job:
            raise KeyError(f"Outreach send job {job_id} was not found")
        return job

    @app.post("/api/v1/outreach/send/{job_id}/stop")
    def stop_outreach_send(job_id: str) -> dict[str, Any]:
        job = app.state.outreach_send_jobs.get(job_id)
        if not job:
            raise KeyError(f"Outreach send job {job_id} was not found")
        if job["status"] not in {"queued", "sending"}:
            raise ValueError(f"Cannot stop outreach in {job['status']} state")
        job["stop_requested"] = True
        job["message"] = "Stopping after the current email"
        return job

    @app.post("/api/v1/outreach/export")
    def export_outreach(payload: OutreachExport) -> Response:
        service = compliance()
        try:
            drafts = service.export_approved(payload.draft_ids)
        finally:
            service.close()
        return Response(
            json.dumps({"approved_outreach": drafts}, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="approved_outreach.json"'},
        )

    @app.post("/api/v1/outreach/purge")
    def purge_outreach(retention_days: int = Query(default=90, ge=30, le=3650)) -> dict[str, int]:
        service = compliance()
        try:
            return {"purged": service.purge_drafts(retention_days)}
        finally:
            service.close()

    @app.post("/api/v1/runs", status_code=201)
    def create_run(payload: RunCreate) -> dict[str, Any]:
        if payload.search_provider == "osm_local":
            local_status = LocalDataService().status()
            if not local_status["ready"]:
                raise ValueError(local_status["message"])
        repo = repository()
        try:
            runtime = _settings_payload(repo)
            stored = repo.app_settings()
            config_values = payload.model_dump()
            config_values["model"] = payload.model or runtime["default_model"]
            config_values["run_name"] = make_run_name(payload.niche)
            config_values["blocked_domains"] = set(runtime["blocked_domains"])
            config_values["ollama_base_url"] = runtime["model_endpoint"]
            config_values["llm_api_key"] = stored.get("llm_api_key", "")
            crawl_page_limit, crawl_depth = {
                "quick": (6, 2),
                "deep": (20, 3),
                "exhaustive": (40, 4),
            }[payload.crawl_mode]
            config_values["crawl_page_limit"] = crawl_page_limit
            config_values["crawl_depth"] = crawl_depth
            config = ScraperConfig(
                **config_values,
                database_path=app.state.database_path,
            )
            run_id = repo.create_run(config)
            response = {"run": repo.run_status(run_id), "candidates": [], "leads": []}
        finally:
            repo.engine.dispose()
        schedule_discovery(config, run_id, False)
        return response

    @app.get("/api/v1/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        repo = repository()
        try:
            return {
                "run": repo.run_status(run_id),
                "candidates": repo.list_candidates(run_id),
                "leads": clean_leads(repo.load_leads(run_id)),
            }
        finally:
            repo.engine.dispose()

    @app.get("/api/v1/runs/{run_id}/diagnostics")
    def run_diagnostics(run_id: str) -> dict[str, Any]:
        repo = repository()
        try:
            config = repo.load_config(run_id)
            return {
                "run": repo.run_status(run_id),
                "database": repo.integrity_check(),
                "configuration": {
                    "niche": config.niche,
                    "location": config.location,
                    "model": config.model,
                    "max_sites": config.max_sites,
                    "retry_attempts": config.retry_attempts,
                    "crawl_mode": config.crawl_mode,
                    "crawl_page_limit": config.crawl_page_limit,
                    "crawl_depth": config.crawl_depth,
                    "advanced_fetching": config.advanced_fetching,
                },
                "events": repo.list_events(run_id)[-100:],
            }
        finally:
            repo.engine.dispose()

    @app.post("/api/v1/runs/{run_id}/discover-more", status_code=202)
    def discover_more(
        run_id: str,
        source: str | None = Query(default=None, pattern="^(local|web|both)$"),
    ) -> dict[str, Any]:
        repo = repository()
        try:
            status = repo.run_status(run_id)
            if status["status"] in {"searching", "running"}:
                raise ValueError(f"Run is already {status['status']}")
            config = repo.load_config(run_id)
            repo.begin_search(run_id, continuation=True)
        finally:
            repo.engine.dispose()
        schedule_discovery(config, run_id, True, source)
        return {
            "run_id": run_id,
            "status": "accepted",
            "kind": "discovery",
            "source": source or _source_mode(config.search_provider),
        }

    @app.post("/api/v1/runs/{run_id}/start", status_code=202)
    def start_run(run_id: str) -> dict[str, str]:
        repo = repository()
        try:
            config = repo.load_config(run_id)
            app.state.model_validator(config)
            repo.begin_run(run_id)
        finally:
            repo.engine.dispose()
        schedule_enrichment(config, run_id)
        return {"run_id": run_id, "status": "accepted"}

    @app.put("/api/v1/runs/{run_id}/candidates/{domain}")
    def select_candidate(run_id: str, domain: str, payload: CandidateSelection) -> dict[str, str]:
        repo = repository()
        try:
            return repo.set_candidate_selected(run_id, domain, payload.selected)
        finally:
            repo.engine.dispose()

    @app.patch("/api/v1/runs/{run_id}/leads/{domain}")
    def update_lead(run_id: str, domain: str, payload: LeadUpdate) -> dict[str, Any]:
        repo = repository()
        try:
            changes = payload.model_dump(exclude_none=True)
            if not changes:
                raise ValueError("At least one lead field must be provided")
            return repo.update_lead(run_id, domain, changes)
        finally:
            repo.engine.dispose()

    @app.delete("/api/v1/runs/{run_id}/leads/{domain}")
    def delete_lead(
        run_id: str, domain: str, reason: str = Query(min_length=3, max_length=500)
    ) -> dict[str, Any]:
        service = compliance()
        try:
            return service.delete_lead_data(run_id, domain, reason)
        finally:
            service.close()

    @app.post("/api/v1/runs/{run_id}/cancel")
    def cancel_run(run_id: str) -> dict[str, Any]:
        app.state.discovery_jobs.pop(run_id, None)
        app.state.enrichment_jobs.pop(run_id, None)
        repo = repository()
        try:
            status = repo.run_status(run_id)["status"]
            if status not in {"searching", "running"}:
                raise ValueError(f"Cannot stop a run in {status} state")
            repo.finish_run(run_id, "stopped", {"reason": "Stopped by user"})
            return repo.run_status(run_id)
        finally:
            repo.engine.dispose()

    @app.post("/api/v1/runs/{run_id}/continue", status_code=202)
    def continue_run(run_id: str) -> dict[str, Any]:
        repo = repository()
        try:
            status = repo.run_status(run_id)
            if status["status"] in {"searching", "running"}:
                raise ValueError(f"Run is already {status['status']}")
            config = repo.load_config(run_id)
            counts = status["counts"]
            actionable = counts.get("queued", 0) + counts.get("failed", 0) + counts.get("processing", 0)
            if actionable:
                app.state.model_validator(config)
                recovered = repo.recover_for_resume(run_id)
                kind = "enrichment"
            else:
                continuation = bool(repo.candidate_domains(run_id) or status.get("discovery"))
                repo.begin_search(run_id, continuation=continuation)
                recovered = 0
                kind = "discovery"
        finally:
            repo.engine.dispose()
        if kind == "enrichment":
            schedule_enrichment(config, run_id)
        else:
            schedule_discovery(config, run_id, continuation)
        return {"run_id": run_id, "status": "accepted", "kind": kind, "recovered": recovered}

    @app.delete("/api/v1/runs/{run_id}")
    def delete_run(run_id: str) -> dict[str, str]:
        app.state.discovery_jobs.pop(run_id, None)
        app.state.enrichment_jobs.pop(run_id, None)
        repo = repository()
        try:
            status = repo.run_status(run_id)["status"]
            if status in {"searching", "running"}:
                repo.finish_run(run_id, "stopped", {"reason": "Stopped before deletion"})
            return repo.delete_run(run_id)
        finally:
            repo.engine.dispose()

    @app.post("/api/v1/runs/{run_id}/retry", status_code=202)
    def retry_run(run_id: str) -> dict[str, Any]:
        repo = repository()
        try:
            config = repo.load_config(run_id)
            status = repo.run_status(run_id)
            if status["status"] in {"searching", "running"}:
                raise ValueError(f"Run is already {status['status']}")
            if not status["counts"].get("failed") and not status["counts"].get("processing"):
                raise ValueError("This run has no failed or interrupted candidates to retry")
            app.state.model_validator(config)
            recovered = repo.recover_for_resume(run_id)
        finally:
            repo.engine.dispose()
        schedule_enrichment(config, run_id)
        return {"run_id": run_id, "status": "accepted", "recovered": recovered}

    @app.get("/api/v1/runs/{run_id}/events", response_class=EventSourceResponse)
    async def events(
        run_id: str,
        after_id: int = Query(default=0, ge=0),
    ) -> AsyncIterable[ServerSentEvent]:
        cursor = after_id
        while True:
            repo = repository()
            try:
                rows = repo.list_events(run_id, cursor)
                status = repo.run_status(run_id)["status"]
            finally:
                repo.engine.dispose()
            for row in rows:
                cursor = row["id"]
                yield ServerSentEvent(data=row, event=row["event"], id=str(row["id"]))
            if status in RUN_TERMINAL and not rows:
                break
            await asyncio.sleep(0.25)

    @app.get("/api/v1/runs/{run_id}/export")
    def export_run(run_id: str, format: str = Query(pattern="^(json|csv)$")) -> Response:
        repo = repository()
        try:
            run = repo.run_status(run_id)
            leads = clean_leads(repo.load_leads(run_id))
        finally:
            repo.engine.dispose()
        if not leads:
            raise KeyError(f"Export is not available yet: {format}")
        filename = _download_filename(run["run_name"], format)
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        if format == "json":
            content = json.dumps({"run_id": run_id, "clean_leads": leads}, ensure_ascii=False, indent=2)
            return Response(content, media_type="application/json", headers=headers)
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=LEAD_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for lead in leads:
            writer.writerow({key: _csv_value(lead.get(key, "")) for key in LEAD_FIELDS})
        return Response("\ufeff" + stream.getvalue(), media_type="text/csv", headers=headers)

    frontend_dir = frontend_dir or Path(os.getenv("LEAD_SCRAPER_FRONTEND_DIR", "frontend/dist"))
    if (frontend_dir / "index.html").is_file():
        app.mount("/", SpaStaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app


def _execute_run(
    config: ScraperConfig,
    run_id: str,
    active_check: Callable[[], bool] | None = None,
) -> None:
    repo = RunRepository(config.database_path)
    try:
        run_pipeline(
            config,
            resume_run_id=run_id,
            cancel_check=lambda: repo.is_cancelled(run_id)
            or bool(active_check and not active_check()),
            active_check=active_check,
        )
    finally:
        repo.engine.dispose()


def _execute_discovery(
    config: ScraperConfig,
    run_id: str,
    continuation: bool,
    source_mode: str | None = None,
    active_check: Callable[[], bool] | None = None,
) -> None:
    repo = RunRepository(config.database_path)
    try:
        status = repo.run_status(run_id)
        source_mode = source_mode or _source_mode(config.search_provider)
        provider = {"local": "osm_local", "web": "auto", "both": "hybrid"}[source_mode]
        effective_config = config.model_copy(update={"search_provider": provider})
        current_domains = repo.candidate_domains(run_id)
        market_domains = repo.seen_domains(config.niche, config.location, exclude_run_id=run_id)
        excluded = current_domains | (market_domains if config.discovery_mode == "new_only" else set())
        previous_discovery = status.get("discovery", {})
        next_pages = dict(previous_discovery.get("next_pages") or {})
        fallback_page = (
            previous_discovery.get("next_search_page", 0)
            if previous_discovery.get("source_mode") in {None, source_mode}
            else 0
        )
        start_page = int(
            next_pages.get(
                "web" if source_mode == "both" else source_mode, fallback_page if continuation else 0
            )
        )
        local_start_page = (
            int(next_pages.get("local", 0))
            if continuation and source_mode == "both"
            else start_page
            if source_mode == "local"
            else 0
        )
        discovery: dict[str, Any] = {
            "mode": config.discovery_mode,
            "source_mode": source_mode,
            "continuation": continuation,
            "current_run_domains": len(current_domains),
            "previous_market_domains": len(market_domains),
        }
        found_sites = search_business_sites(
            effective_config,
            excluded_domains=excluded,
            diagnostics=discovery,
            start_page=start_page,
            local_start_page=local_start_page,
            cancel_check=lambda: repo.is_cancelled(run_id) or bool(active_check and not active_check()),
            progress_callback=lambda: repo.touch_search(run_id),
            deadline=time.monotonic() + _search_timeout_seconds(),
        )
        sites = _select_discovery_batch(found_sites, config.max_sites, source_mode)
        if active_check and not active_check():
            raise SearchStopped("Search was superseded by a newer job")
        next_page = int(discovery.get("next_search_page", start_page + 1))
        next_pages[source_mode] = next_page
        if source_mode == "both":
            next_pages["local"] = int(discovery.get("next_local_page", local_start_page + 1))
            next_pages["web"] = next_page
        discovery["next_pages"] = next_pages
        discovery["new_candidates"] = len(sites)
        repo.add_candidates(run_id, sites, discovery)
    except SearchStopped as exc:
        if active_check and not active_check():
            return
        try:
            if repo.run_status(run_id)["status"] == "searching":
                repo.finish_run(run_id, "stopped", {"reason": str(exc)})
        except KeyError:
            pass
    except KeyError:
        pass
    except Exception as exc:
        with suppress(KeyError):
            repo.finish_run(
                run_id,
                "failed",
                {"error_type": type(exc).__name__, "message": str(exc)[:1000]},
            )
    finally:
        repo.engine.dispose()


def _source_mode(provider: str) -> str:
    if provider == "osm_local":
        return "local"
    if provider == "hybrid":
        return "both"
    return "web"


def _select_discovery_batch(
    sites: list[dict[str, Any]], limit: int, source_mode: str
) -> list[dict[str, Any]]:
    if source_mode != "both":
        return sites[:limit]
    merged = [site for site in sites if {"local", "web"}.issubset(site.get("sources") or [])]
    local = [site for site in sites if "local" in (site.get("sources") or []) and site not in merged]
    web = [site for site in sites if "web" in (site.get("sources") or []) and site not in merged]
    selected = merged[:limit]
    while len(selected) < limit and (local or web):
        if local:
            selected.append(local.pop(0))
        if len(selected) < limit and web:
            selected.append(web.pop(0))
    if len(selected) < limit:
        selected.extend(site for site in sites if site not in selected)
    return selected[:limit]


def _search_timeout_seconds() -> int:
    return max(15, int(os.getenv("LEAD_SEARCH_TIMEOUT_SECONDS", "90")))


def _search_stale_seconds() -> int:
    return max(_search_timeout_seconds() + 30, 45)


def _download_filename(stem: str, extension: str) -> str:
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem.strip()).strip("._-")
    safe_stem = safe_stem or "leadroom_export"
    downloaded_at = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    return f"{safe_stem}_downloaded_{downloaded_at}.{extension}"


def _problem(status: int, problem: str, cause: str, fix: str) -> JSONResponse:
    payload = Problem(problem=problem, cause=cause, fix=fix)
    return JSONResponse(status_code=status, content=payload.model_dump())


def _csv_value(value: Any) -> str:
    if isinstance(value, list):
        text = "; ".join(str(item) for item in value)
    elif isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value) if value is not None else ""
    return f"'{text}" if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


app = create_app()
