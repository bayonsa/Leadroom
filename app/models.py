from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LeadExtraction(BaseModel):
    model_config = ConfigDict(extra="allow")

    is_valid_lead: bool | None = None
    business_name: str = ""
    website: str = ""
    city_or_area: str = ""
    business_type: str = ""
    services: list[str] = Field(default_factory=list)
    generic_email: str = ""
    emails: list[str] = Field(default_factory=list)
    phone: str = ""
    phones: list[str] = Field(default_factory=list)
    contact_page: str = ""
    booking_page: str = ""
    instagram_or_social: str = ""
    has_online_booking: bool = False
    website_quality_note: str = ""

    @field_validator(
        "business_name",
        "website",
        "city_or_area",
        "business_type",
        "generic_email",
        "phone",
        "contact_page",
        "booking_page",
        "instagram_or_social",
        "website_quality_note",
        mode="before",
    )
    @classmethod
    def coerce_optional_text(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()


class Lead(BaseModel):
    model_config = ConfigDict(extra="allow")

    is_valid_lead: bool = False
    business_name: str = ""
    website: str = ""
    city_or_area: str = ""
    business_type: str = ""
    services: list[str] = Field(default_factory=list)
    generic_email: str = ""
    emails: list[str] = Field(default_factory=list)
    phone: str = ""
    phones: list[str] = Field(default_factory=list)
    contact_page: str = ""
    booking_page: str = ""
    instagram_or_social: str = ""
    has_online_booking: bool = False
    website_quality_note: str = ""
    lead_score: int = Field(default=0, ge=0, le=10)
    lead_reason: str = ""
    source_url: str = ""
    search_title: str = ""
    search_snippet: str = ""
    domain: str = ""
    field_evidence: dict[str, dict[str, str]] = Field(default_factory=dict)
    enrichment_errors: list[str] = Field(default_factory=list)


class Candidate(BaseModel):
    title: str = ""
    url: str
    homepage: str
    snippet: str = ""
    domain: str


class ScrapeFailure(BaseModel):
    url: str
    error: str
    error_type: str = "unknown"


class RunSummary(BaseModel):
    candidate_count: int = Field(ge=0)
    scraped_count: int = Field(ge=0)
    clean_lead_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    cancelled: bool = False
