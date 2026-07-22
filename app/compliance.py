from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import (
    Base,
    CandidateRecord,
    EventRecord,
    RepositoryLeadRecord,
    RunRepository,
)
from app.outreach_ai import CampaignBrief, compose_outreach_message
from app.scoring import has_verified_evidence

GENERIC_MAILBOXES = {
    "admin",
    "bookings",
    "contact",
    "enquiries",
    "hello",
    "info",
    "office",
    "reception",
    "sales",
    "team",
}
DAILY_EXPORT_LIMIT = 25


class SuppressionRecord(Base):
    __tablename__ = "suppressions"
    __table_args__ = (UniqueConstraint("kind", "value_hash", name="uq_suppression_kind_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(20))
    value_hash: Mapped[str] = mapped_column(String(64))
    display_hint: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OutreachDraftRecord(Base):
    __tablename__ = "outreach_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    lead_domain: Mapped[str] = mapped_column(String(255), index=True)
    recipient_email: Mapped[str] = mapped_column(String(320), index=True)
    subscriber_type: Mapped[str] = mapped_column(String(30))
    consent_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    lawful_basis_note: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    approved_by: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutreachDeliveryRecord(Base):
    __tablename__ = "outreach_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("outreach_drafts.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    provider_message_id: Mapped[str] = mapped_column(String(255), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ComplianceService:
    def __init__(self, database_path: Path) -> None:
        self.repository = RunRepository(database_path)
        Base.metadata.create_all(self.repository.engine)

    def close(self) -> None:
        self.repository.engine.dispose()

    def add_suppression(self, value: str, kind: str, reason: str) -> dict[str, Any]:
        normalized = _normalize(value, kind)
        if kind not in {"email", "domain"}:
            raise ValueError("Suppression kind must be email or domain")
        if not reason.strip():
            raise ValueError("Suppression reason is required")
        value_hash = _hash(normalized)
        with self.repository.sessions.begin() as session:
            existing = session.query(SuppressionRecord).filter_by(kind=kind, value_hash=value_hash).first()
            if existing is None:
                existing = SuppressionRecord(
                    kind=kind,
                    value_hash=value_hash,
                    display_hint=_hint(normalized, kind),
                    reason=reason.strip(),
                    created_at=_now(),
                )
                session.add(existing)
                session.flush()
            drafts = session.query(OutreachDraftRecord).filter(
                OutreachDraftRecord.status.in_({"draft", "approved", "queued", "sending"})
            )
            drafts = (
                drafts.filter(OutreachDraftRecord.recipient_email == normalized)
                if kind == "email"
                else drafts.filter(OutreachDraftRecord.lead_domain == normalized)
            )
            for draft in drafts.all():
                draft.status = "blocked"
            return _suppression_dict(existing)

    def list_suppressions(self) -> list[dict[str, Any]]:
        with self.repository.sessions() as session:
            rows = session.query(SuppressionRecord).order_by(SuppressionRecord.created_at.desc()).all()
            return [_suppression_dict(row) for row in rows]

    def create_draft(
        self,
        run_id: str,
        domain: str,
        subscriber_type: str,
        lawful_basis_note: str,
        sender_identity: str,
        opt_out_address: str,
        offer_summary: str,
        consent_confirmed: bool = False,
        tone: str = "professional",
        links: list[str] | None = None,
        ai_personalize: bool = False,
    ) -> dict[str, Any]:
        if subscriber_type not in {"corporate", "sole_trader", "unknown"}:
            raise ValueError("Subscriber type must be corporate, sole_trader, or unknown")
        if subscriber_type != "corporate" and not consent_confirmed:
            raise ValueError("Consent is required for sole traders or unknown subscriber types")
        if not lawful_basis_note.strip():
            raise ValueError("A documented lawful-basis note is required")
        if subscriber_type != "corporate" and "consent" not in lawful_basis_note.lower():
            raise ValueError("The lawful-basis note must document consent for this subscriber type")
        if not sender_identity.strip() or not opt_out_address.strip():
            raise ValueError("Sender identity and a valid opt-out address are required")
        with self.repository.sessions() as session:
            candidate = self.repository._candidate_by_domain(session, run_id, domain)
            if candidate.lead is None:
                raise KeyError(f"No lead exists for candidate: {domain}")
            lead = json.loads(candidate.lead.data_json)
            email = str(lead.get("generic_email") or "").strip().lower()
            if not _is_generic_email(email):
                raise ValueError("Only verified generic business mailboxes are eligible for outreach")
            if not has_verified_evidence(lead, "generic_email"):
                raise ValueError("Email source evidence is required before drafting outreach")
            evidence = (lead.get("field_evidence") or {}).get("generic_email") or {}
            if int(lead.get("lead_score") or 0) < 7:
                raise ValueError("Lead score must be at least 7 before drafting outreach")
        stored = self.repository.app_settings()
        runtime = {
            "model_provider": stored.get("model_provider", "ollama"),
            "model_name": stored.get("model_name", "llama3.2:3b"),
            "model_endpoint": stored.get("model_endpoint", "http://localhost:11434"),
        }
        subject, body, personalization = compose_outreach_message(
            lead,
            CampaignBrief(
                base_message=offer_summary.strip(),
                tone=tone.strip() or "professional",
                links=tuple(links or []),
                sender_identity=sender_identity,
                opt_out_address=opt_out_address,
            ),
            runtime,
            stored.get("llm_api_key", ""),
            personalize=ai_personalize,
        )
        with self.repository.sessions.begin() as session:
            candidate = self.repository._candidate_by_domain(session, run_id, domain)
            if candidate.lead is None:
                raise KeyError(f"No lead exists for candidate: {domain}")
            self._assert_not_suppressed(session, email, domain)
            duplicate = (
                session.query(OutreachDraftRecord)
                .filter(
                    OutreachDraftRecord.recipient_email == email,
                    OutreachDraftRecord.status.in_({"draft", "approved", "queued", "sent", "exported"}),
                )
                .first()
            )
            if duplicate:
                raise ValueError("An active outreach draft already exists for this recipient")
            row = OutreachDraftRecord(
                id=str(uuid.uuid4()),
                run_id=run_id,
                lead_domain=domain,
                recipient_email=email,
                subscriber_type=subscriber_type,
                consent_confirmed=consent_confirmed,
                lawful_basis_note=lawful_basis_note.strip(),
                subject=subject,
                body=body,
                evidence_json=json.dumps(
                    {
                        "email": evidence,
                        "lead_score": lead.get("lead_score"),
                        "personalization": personalization,
                        "links": links or [],
                    }
                ),
                status="draft",
                created_at=_now(),
            )
            session.add(row)
            session.flush()
            return _draft_dict(row)

    def list_drafts(self, run_id: str | None = None) -> list[dict[str, Any]]:
        with self.repository.sessions() as session:
            query = session.query(OutreachDraftRecord)
            if run_id:
                query = query.filter(OutreachDraftRecord.run_id == run_id)
            rows = query.order_by(OutreachDraftRecord.created_at.desc()).all()
            return [_draft_dict(row, _latest_delivery(session, row.id)) for row in rows]

    def preflight_run(self, run_id: str, domains: list[str] | None = None) -> dict[str, Any]:
        requested = set(domains or [])
        with self.repository.sessions() as session:
            run = self.repository._require_run(session, run_id)
            results: list[dict[str, Any]] = []
            for candidate in run.candidates:
                if candidate.lead is None or (requested and candidate.domain not in requested):
                    continue
                lead = json.loads(candidate.lead.data_json)
                email = str(lead.get("generic_email") or "").strip().lower()
                score = int(lead.get("lead_score") or 0)
                reasons: list[str] = []
                if not email:
                    reasons.append("No verified email")
                elif not _is_generic_email(email):
                    reasons.append("Email is not a generic business mailbox")
                if not has_verified_evidence(lead, "generic_email"):
                    reasons.append("Email evidence is missing")
                if score < 7:
                    reasons.append("Lead score is below 7")
                if email and self._is_suppressed(session, email, candidate.domain):
                    reasons.append("Suppressed")
                duplicate = (
                    session.query(OutreachDraftRecord)
                    .filter(
                        OutreachDraftRecord.recipient_email == email,
                        OutreachDraftRecord.status.in_({"draft", "approved", "queued", "sent", "exported"}),
                    )
                    .first()
                    if email
                    else None
                )
                if duplicate:
                    reasons.append("An active draft already exists")
                results.append(
                    {
                        "domain": candidate.domain,
                        "business_name": str(lead.get("business_name") or candidate.domain),
                        "email": email,
                        "lead_score": score,
                        "eligible": not reasons,
                        "reasons": reasons,
                    }
                )
            eligible = sum(1 for item in results if item["eligible"])
            return {
                "run_id": run_id,
                "total": len(results),
                "eligible": eligible,
                "blocked": len(results) - eligible,
                "results": results,
            }

    def create_drafts_bulk(self, domains: list[str], **shared: Any) -> dict[str, Any]:
        if not domains or len(domains) > 100:
            raise ValueError("Bulk draft selection must contain 1-100 leads")
        created: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        for domain in list(dict.fromkeys(domains)):
            try:
                created.append(self.create_draft(domain=domain, **shared))
            except (KeyError, ValueError) as exc:
                skipped.append({"domain": domain, "reason": str(exc)})
        return {"created": len(created), "skipped": len(skipped), "drafts": created, "errors": skipped}

    def approve_draft(
        self,
        draft_id: str,
        reviewed_by: str,
        corporate_status_confirmed: bool,
        privacy_notice_confirmed: bool,
    ) -> dict[str, Any]:
        if not reviewed_by.strip() or not privacy_notice_confirmed:
            raise ValueError("Reviewer and privacy-notice checks are required")
        with self.repository.sessions.begin() as session:
            row = _require_draft(session, draft_id)
            if row.status != "draft":
                raise ValueError(f"Cannot approve outreach in {row.status} state")
            if row.subscriber_type == "corporate" and not corporate_status_confirmed:
                raise ValueError("Corporate subscriber status must be confirmed")
            if row.subscriber_type != "corporate" and not row.consent_confirmed:
                raise ValueError("Recorded consent is required for this subscriber type")
            self._assert_not_suppressed(session, row.recipient_email, row.lead_domain)
            row.status = "approved"
            row.approved_by = reviewed_by.strip()
            row.approved_at = _now()
            return _draft_dict(row)

    def approve_drafts_bulk(
        self,
        draft_ids: list[str],
        reviewed_by: str,
        corporate_status_confirmed: bool,
        privacy_notice_confirmed: bool,
    ) -> dict[str, Any]:
        unique_ids = list(dict.fromkeys(draft_ids))
        if not unique_ids or len(unique_ids) > 100:
            raise ValueError("Bulk approval must contain 1-100 drafts")
        if not reviewed_by.strip() or not privacy_notice_confirmed:
            raise ValueError("Reviewer and privacy-notice checks are required")
        with self.repository.sessions.begin() as session:
            rows = [_require_draft(session, draft_id) for draft_id in unique_ids]
            for row in rows:
                if row.status != "draft":
                    raise ValueError("Every selected item must be an unapproved draft")
                if row.subscriber_type == "corporate" and not corporate_status_confirmed:
                    raise ValueError("Corporate subscriber status must be confirmed")
                if row.subscriber_type != "corporate" and not row.consent_confirmed:
                    raise ValueError("Recorded consent is required for every non-corporate recipient")
                self._assert_not_suppressed(session, row.recipient_email, row.lead_domain)
            now = _now()
            for row in rows:
                row.status = "approved"
                row.approved_by = reviewed_by.strip()
                row.approved_at = now
            return {"approved": len(rows), "drafts": [_draft_dict(row) for row in rows]}

    def queue_deliveries(self, draft_ids: list[str]) -> list[str]:
        unique_ids = list(dict.fromkeys(draft_ids))
        if not unique_ids or len(unique_ids) > DAILY_EXPORT_LIMIT:
            raise ValueError(f"Send batch must contain 1-{DAILY_EXPORT_LIMIT} drafts")
        with self.repository.sessions.begin() as session:
            day_start = _now() - timedelta(hours=24)
            sent_today = (
                session.query(OutreachDeliveryRecord)
                .filter(
                    OutreachDeliveryRecord.status == "sent",
                    OutreachDeliveryRecord.completed_at >= day_start,
                )
                .count()
            )
            if sent_today + len(unique_ids) > DAILY_EXPORT_LIMIT:
                raise ValueError("Daily outreach send limit exceeded")
            rows = [_require_draft(session, draft_id) for draft_id in unique_ids]
            for row in rows:
                if row.status != "approved":
                    raise ValueError("Every outreach draft must be approved before sending")
                self._assert_not_suppressed(session, row.recipient_email, row.lead_domain)
            for row in rows:
                row.status = "queued"
            return unique_ids

    def recover_interrupted_deliveries(self) -> int:
        """Release unsent queue entries and quarantine deliveries that may have reached SMTP."""
        now = _now()
        with self.repository.sessions.begin() as session:
            rows = (
                session.query(OutreachDraftRecord)
                .filter(OutreachDraftRecord.status.in_({"queued", "sending"}))
                .all()
            )
            for row in rows:
                interrupted_status = row.status
                started_delivery = _latest_delivery(session, row.id)
                row.status = "approved" if interrupted_status == "queued" else "uncertain"
                session.add(
                    OutreachDeliveryRecord(
                        id=str(uuid.uuid4()),
                        draft_id=row.id,
                        status="released" if interrupted_status == "queued" else "uncertain",
                        error=(
                            "Application restarted before SMTP delivery started."
                            if interrupted_status == "queued"
                            else "Application restarted after SMTP delivery started; delivery requires reconciliation."
                        ),
                        provider_message_id=(
                            started_delivery.provider_message_id
                            if interrupted_status == "sending" and started_delivery is not None
                            else ""
                        ),
                        attempted_at=now,
                        completed_at=now,
                    )
                )
            return len(rows)

    def mark_delivery_started(self, draft_id: str, provider_message_id: str = "") -> None:
        with self.repository.sessions.begin() as session:
            row = _require_draft(session, draft_id)
            if row.status != "queued":
                raise ValueError(f"Cannot start outreach in {row.status} state")
            self._assert_not_suppressed(session, row.recipient_email, row.lead_domain)
            row.status = "sending"
            if provider_message_id:
                session.add(
                    OutreachDeliveryRecord(
                        id=str(uuid.uuid4()),
                        draft_id=draft_id,
                        status="sending",
                        provider_message_id=provider_message_id,
                        attempted_at=_now(),
                    )
                )

    def mark_delivery_uncertain(self, draft_id: str, provider_message_id: str, error: str) -> None:
        now = _now()
        with self.repository.sessions.begin() as session:
            row = _require_draft(session, draft_id)
            row.status = "uncertain"
            session.add(
                OutreachDeliveryRecord(
                    id=str(uuid.uuid4()),
                    draft_id=draft_id,
                    status="uncertain",
                    provider_message_id=provider_message_id,
                    error=error[:2000],
                    attempted_at=now,
                    completed_at=now,
                )
            )

    def delivery_payload(self, draft_id: str) -> dict[str, str]:
        with self.repository.sessions() as session:
            row = _require_draft(session, draft_id)
            if row.status not in {"queued", "sending"}:
                raise ValueError(f"Cannot send outreach in {row.status} state")
            self._assert_not_suppressed(session, row.recipient_email, row.lead_domain)
            return {
                "recipient": row.recipient_email,
                "subject": row.subject,
                "body": row.body,
            }

    def complete_delivery(
        self,
        draft_id: str,
        status: str,
        provider_message_id: str = "",
        error: str = "",
    ) -> dict[str, Any]:
        if status not in {"sent", "failed"}:
            raise ValueError("Delivery status must be sent or failed")
        now = _now()
        with self.repository.sessions.begin() as session:
            row = _require_draft(session, draft_id)
            if row.status not in {"sending", "blocked"}:
                raise ValueError(f"Cannot complete outreach in {row.status} state")
            delivery_status = (
                "sent_after_suppression" if status == "sent" and row.status == "blocked" else status
            )
            delivery = OutreachDeliveryRecord(
                id=str(uuid.uuid4()),
                draft_id=draft_id,
                status=delivery_status,
                provider_message_id=provider_message_id,
                error=error[:2000],
                attempted_at=now,
                completed_at=now,
            )
            session.add(delivery)
            if status == "sent" and row.status != "blocked":
                row.status = "sent"
            elif row.status != "blocked":
                row.status = "approved"
            session.flush()
            return _draft_dict(row, delivery)

    def release_queued(self, draft_ids: list[str]) -> int:
        with self.repository.sessions.begin() as session:
            rows = (
                session.query(OutreachDraftRecord)
                .filter(
                    OutreachDraftRecord.id.in_(draft_ids),
                    OutreachDraftRecord.status == "queued",
                )
                .all()
            )
            for row in rows:
                row.status = "approved"
            return len(rows)

    def export_approved(self, draft_ids: list[str]) -> list[dict[str, Any]]:
        if not draft_ids or len(draft_ids) > DAILY_EXPORT_LIMIT:
            raise ValueError(f"Export batch must contain 1-{DAILY_EXPORT_LIMIT} drafts")
        with self.repository.sessions.begin() as session:
            day_start = _now() - timedelta(hours=24)
            exported_today = (
                session.query(OutreachDraftRecord)
                .filter(OutreachDraftRecord.exported_at >= day_start)
                .count()
            )
            if exported_today + len(draft_ids) > DAILY_EXPORT_LIMIT:
                raise ValueError("Daily outreach export limit exceeded")
            rows = [_require_draft(session, draft_id) for draft_id in draft_ids]
            for row in rows:
                if row.status != "approved":
                    raise ValueError("Every outreach draft must be approved before export")
                self._assert_not_suppressed(session, row.recipient_email, row.lead_domain)
            now = _now()
            for row in rows:
                row.status = "exported"
                row.exported_at = now
            return [_draft_dict(row) for row in rows]

    def purge_drafts(self, retention_days: int = 90) -> int:
        if retention_days < 30:
            raise ValueError("Outreach retention cannot be shorter than 30 days")
        cutoff = _now() - timedelta(days=retention_days)
        with self.repository.sessions.begin() as session:
            rows = session.query(OutreachDraftRecord).filter(OutreachDraftRecord.created_at < cutoff).all()
            count = len(rows)
            for row in rows:
                session.delete(row)
            return count

    def delete_lead_data(self, run_id: str, domain: str, reason: str) -> dict[str, Any]:
        with self.repository.sessions() as session:
            candidates = session.query(CandidateRecord).filter(CandidateRecord.domain == domain).all()
            emails = {
                str(json.loads(row.lead.data_json).get("generic_email") or "").strip().lower()
                for row in candidates
                if row.lead is not None
            }
            repository_row = session.get(RepositoryLeadRecord, domain)
            if repository_row is not None:
                repository_data = json.loads(repository_row.data_json)
                emails.update(str(value).strip().lower() for value in repository_data.get("emails", []))
        for email in sorted(value for value in emails if value):
            self.add_suppression(email, "email", reason)
        self.add_suppression(domain, "domain", reason)
        with self.repository.repository_write_lock(), self.repository.sessions.begin() as session:
            candidates = session.query(CandidateRecord).filter(CandidateRecord.domain == domain).all()
            for candidate in candidates:
                if candidate.lead is not None:
                    session.delete(candidate.lead)
            repository_row = session.get(RepositoryLeadRecord, domain)
            if repository_row is not None:
                session.delete(repository_row)
            drafts = (
                session.query(OutreachDraftRecord).filter(OutreachDraftRecord.lead_domain == domain).all()
            )
            for draft in drafts:
                session.delete(draft)
            events = session.query(EventRecord).filter(EventRecord.payload_json.contains(domain)).all()
            for event in events:
                try:
                    payload = json.loads(event.payload_json)
                except json.JSONDecodeError:
                    continue
                if _payload_references_domain(payload, domain):
                    session.delete(event)
        return {"domain": domain, "deleted": True, "suppression_preserved": True}

    @staticmethod
    def _assert_not_suppressed(session, email: str, domain: str) -> None:
        hashes = {_hash(email.lower()), _hash(domain.lower())}
        blocked = session.query(SuppressionRecord).filter(SuppressionRecord.value_hash.in_(hashes)).first()
        if blocked:
            raise ValueError("Recipient is on the suppression list")

    @staticmethod
    def _is_suppressed(session, email: str, domain: str) -> bool:
        hashes = {_hash(email.lower()), _hash(domain.lower())}
        return (
            session.query(SuppressionRecord).filter(SuppressionRecord.value_hash.in_(hashes)).first()
            is not None
        )


def _is_generic_email(email: str) -> bool:
    match = re.fullmatch(r"([^@]+)@([^@]+)", email)
    return bool(match and match.group(1).lower() in GENERIC_MAILBOXES)


def _normalize(value: str, kind: str) -> str:
    normalized = value.strip().lower()
    if kind == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+", normalized):
        raise ValueError("Invalid suppression email")
    if kind == "domain":
        normalized = normalized.removeprefix("www.")
        if "." not in normalized or "/" in normalized:
            raise ValueError("Invalid suppression domain")
    return normalized


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _payload_references_domain(value: Any, domain: str) -> bool:
    if isinstance(value, dict):
        return any(_payload_references_domain(item, domain) for item in value.values())
    if isinstance(value, list):
        return any(_payload_references_domain(item, domain) for item in value)
    if not isinstance(value, str):
        return False
    normalized = value.strip().casefold().removeprefix("www.")
    return normalized == domain.casefold()


def _hint(value: str, kind: str) -> str:
    if kind == "domain":
        return value
    local, domain = value.split("@", 1)
    return f"{local[:2]}***@{domain}"


def _require_draft(session, draft_id: str) -> OutreachDraftRecord:
    row = session.get(OutreachDraftRecord, draft_id)
    if row is None:
        raise KeyError(f"Unknown outreach draft: {draft_id}")
    return row


def _suppression_dict(row: SuppressionRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.kind,
        "display_hint": row.display_hint,
        "reason": row.reason,
        "created_at": row.created_at.isoformat(),
    }


def _latest_delivery(session, draft_id: str) -> OutreachDeliveryRecord | None:
    return (
        session.query(OutreachDeliveryRecord)
        .filter_by(draft_id=draft_id)
        .order_by(
            OutreachDeliveryRecord.attempted_at.desc(),
            OutreachDeliveryRecord.completed_at.desc(),
            OutreachDeliveryRecord.id.desc(),
        )
        .first()
    )


def _draft_dict(
    row: OutreachDraftRecord,
    delivery: OutreachDeliveryRecord | None = None,
) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "lead_domain": row.lead_domain,
        "recipient_email": row.recipient_email,
        "subscriber_type": row.subscriber_type,
        "consent_confirmed": row.consent_confirmed,
        "lawful_basis_note": row.lawful_basis_note,
        "subject": row.subject,
        "body": row.body,
        "evidence": json.loads(row.evidence_json),
        "status": row.status,
        "approved_by": row.approved_by,
        "created_at": row.created_at.isoformat(),
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "exported_at": row.exported_at.isoformat() if row.exported_at else None,
        "delivery_status": delivery.status if delivery else "",
        "delivery_error": delivery.error if delivery else "",
        "provider_message_id": delivery.provider_message_id if delivery else "",
        "sent_at": delivery.completed_at.isoformat() if delivery and delivery.status == "sent" else "",
    }


def _now() -> datetime:
    return datetime.now(UTC)
