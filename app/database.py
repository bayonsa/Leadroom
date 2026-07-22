from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import closing, contextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    update,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    joinedload,
    mapped_column,
    relationship,
    sessionmaker,
)

from app.config import ScraperConfig
from app.normalizer import is_contactable_lead, promote_verified_business, unique_phones
from app.scoring import explain_score, score_lead
from app.secrets import protect_secret, reveal_secret

SECRET_SETTING_KEYS = {"llm_api_key", "smtp_password", "email_accounts"}

RUN_TERMINAL = {"completed", "cancelled", "failed", "stopped"}
CANDIDATE_TRANSITIONS = {
    "queued": {"processing", "cancelled"},
    "processing": {"completed", "failed", "queued", "cancelled"},
    "failed": {"queued", "processing", "cancelled"},
    "completed": set(),
    "cancelled": {"queued"},
}
_REPOSITORY_IMPORT_LOCK = threading.RLock()


@contextmanager
def _repository_file_lock(database_path: Path):
    lock_path = database_path.with_suffix(f"{database_path.suffix}.repository.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


class Base(DeclarativeBase):
    pass


class RunRecord(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_name: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(20), default="created", index=True)
    config_json: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[str] = mapped_column(String(30), default="lead-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    candidates: Mapped[list[CandidateRecord]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class CandidateRecord(Base):
    __tablename__ = "candidates"
    __table_args__ = (
        UniqueConstraint("run_id", "domain", name="uq_candidates_run_domain"),
        Index("ix_candidates_claim", "run_id", "status", "lease_until"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    domain: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(Text)
    homepage: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    source_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    run: Mapped[RunRecord] = relationship(back_populates="candidates")
    lead: Mapped[LeadRecord | None] = relationship(back_populates="candidate", cascade="all, delete-orphan")


class LeadRecord(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    score: Mapped[int] = mapped_column(Integer, default=0)
    data_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    candidate: Mapped[CandidateRecord] = relationship(back_populates="lead")


class AppSettingRecord(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RepositoryLeadRecord(Base):
    __tablename__ = "repository_leads"

    domain: Mapped[str] = mapped_column(String(255), primary_key=True)
    data_json: Mapped[str] = mapped_column(Text)
    source_run_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class EventRecord(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SchemaVersion(Base):
    __tablename__ = "schema_version"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def create_sqlite_engine(database_path: Path):
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{database_path}", future=True)

    @event.listens_for(engine, "connect")
    def set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


class RunRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.engine = create_sqlite_engine(database_path)
        Base.metadata.create_all(self.engine)
        _migrate_candidate_source(database_path)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        with self.sessions.begin() as session:
            if session.get(SchemaVersion, 1) is None:
                session.add(SchemaVersion(version=1, applied_at=_now()))
            if session.get(SchemaVersion, 2) is None:
                session.add(SchemaVersion(version=2, applied_at=_now()))
            if session.get(SchemaVersion, 3) is None:
                session.add(SchemaVersion(version=3, applied_at=_now()))

    def create_run(self, config: ScraperConfig) -> str:
        run_id = str(uuid.uuid4())
        now = _now()
        with self.sessions.begin() as session:
            run = RunRecord(
                id=run_id,
                run_name=config.run_name,
                status="searching",
                config_json=config.model_dump_json(),
                created_at=now,
                updated_at=now,
            )
            session.add(run)
            session.flush()
            self._event(session, run_id, "run_created", {"run_name": config.run_name})
        return run_id

    def repository_write_lock(self):
        return _repository_file_lock(self.database_path)

    def load_config(self, run_id: str) -> ScraperConfig:
        with self.sessions() as session:
            run = self._require_run(session, run_id)
            return ScraperConfig.model_validate_json(run.config_json)

    def add_candidates(
        self,
        run_id: str,
        sites: list[dict[str, Any]],
        discovery: dict[str, Any] | None = None,
    ) -> int:
        with self.sessions.begin() as session:
            run = self._require_run(session, run_id)
            if run.status in {"cancelled", "stopped"}:
                self._event(session, run_id, "search_results_discarded", {"count": len(sites)})
                return 0
            existing = {row.domain for row in run.candidates}
            added = 0
            for site in sites:
                if site["domain"] in existing:
                    continue
                session.add(
                    CandidateRecord(
                        run_id=run_id,
                        domain=site["domain"],
                        url=site["url"],
                        homepage=site["homepage"],
                        title=site.get("title", ""),
                        snippet=site.get("snippet", ""),
                        source_json=json.dumps(
                            {
                                key: value
                                for key, value in site.items()
                                if key not in {"title", "url", "homepage", "snippet", "domain", "status"}
                            },
                            ensure_ascii=False,
                        ),
                    )
                )
                existing.add(site["domain"])
                added += 1
            if added:
                run.status = "ready"
            elif run.status == "searching":
                run.status = "completed"
            run.updated_at = _now()
            payload = {"count": added, **(discovery or {})}
            self._event(session, run_id, "candidates_added", payload)
            return added

    def begin_search(self, run_id: str, continuation: bool = False) -> None:
        with self.sessions.begin() as session:
            run = self._require_run(session, run_id)
            if run.status in {"searching", "running"}:
                raise ValueError(f"Run is already {run.status}")
            run.status = "searching"
            run.updated_at = _now()
            self._event(session, run_id, "search_started", {"continuation": continuation})

    def touch_search(self, run_id: str) -> bool:
        with self.sessions.begin() as session:
            run = self._require_run(session, run_id)
            if run.status != "searching":
                return False
            run.updated_at = _now()
            return True

    def stop_stale_searches(self, stale_seconds: int = 120) -> int:
        cutoff = _now() - timedelta(seconds=stale_seconds)
        with self.sessions.begin() as session:
            rows = (
                session.query(RunRecord)
                .filter(RunRecord.status == "searching", RunRecord.updated_at <= cutoff)
                .all()
            )
            for run in rows:
                run.status = "stopped"
                run.updated_at = _now()
                self._event(
                    session,
                    run.id,
                    "run_stopped",
                    {"reason": "Search stopped after it stopped reporting progress."},
                )
            return len(rows)

    def delete_run(self, run_id: str) -> dict[str, str]:
        with self.sessions.begin() as session:
            run = self._require_run(session, run_id)
            session.delete(run)
        return {"id": run_id, "status": "deleted"}

    def list_candidates(self, run_id: str) -> list[dict[str, str]]:
        with self.sessions() as session:
            run = self._require_run(session, run_id)
            return [self._candidate_dict(row) for row in run.candidates]

    def candidate_domains(self, run_id: str) -> set[str]:
        with self.sessions() as session:
            run = self._require_run(session, run_id)
            return {row.domain for row in run.candidates}

    def load_leads(self, run_id: str) -> list[dict[str, Any]]:
        with self.sessions() as session:
            run = self._require_run(session, run_id)
            return [
                _prepare_repository_lead(json.loads(row.lead.data_json))
                for row in run.candidates
                if row.lead is not None
            ]

    def update_lead(self, run_id: str, domain: str, changes: dict[str, Any]) -> dict[str, Any]:
        with self.sessions.begin() as session:
            row = self._candidate_by_domain(session, run_id, domain)
            if row.lead is None:
                raise KeyError(f"No lead exists for candidate: {domain}")
            data = json.loads(row.lead.data_json)
            data.update(changes)
            evidence = data.setdefault("field_evidence", {})
            if "generic_email" in changes:
                data["emails"] = [changes["generic_email"], *_contact_values(data.get("emails"))]
                evidence["generic_email"] = {
                    "value": changes["generic_email"],
                    "source_url": "",
                    "method": "manual",
                }
            if "phone" in changes:
                data["phones"] = [changes["phone"], *_contact_values(data.get("phones"))]
                evidence["phone"] = {
                    "value": changes["phone"],
                    "source_url": "",
                    "method": "manual",
                }
            for field in ("business_name", "city_or_area"):
                if field in changes:
                    evidence[field] = {
                        "value": changes[field],
                        "source_url": "",
                        "method": "manual",
                    }
            data["lead_score"] = score_lead(data)
            data["lead_reason"] = explain_score(data)
            data = _prepare_repository_lead(data)
            row.lead.data_json = json.dumps(data, ensure_ascii=False)
            row.lead.score = int(data.get("lead_score") or 0)
            self._event(session, run_id, "lead_updated", {"domain": domain, "fields": sorted(changes)})
            return data

    def import_repository_leads(
        self,
        run_id: str,
        domains: list[str] | None = None,
    ) -> dict[str, int]:
        requested = set(domains or [])
        added = 0
        updated = 0
        skipped = 0
        with _REPOSITORY_IMPORT_LOCK, self.repository_write_lock(), self.sessions.begin() as session:
            run = self._require_run(session, run_id)
            run_config = json.loads(run.config_json)
            candidates = [
                row
                for row in run.candidates
                if row.lead is not None and (not requested or row.domain in requested)
            ]
            if not candidates:
                raise ValueError("No completed leads were selected for the repository")
            now = _now()
            for candidate in candidates:
                incoming = _prepare_repository_lead(
                    promote_verified_business(json.loads(candidate.lead.data_json))
                )
                if not _repository_eligible(incoming):
                    skipped += 1
                    continue
                incoming["domain"] = candidate.domain
                source_data = json.loads(candidate.source_json or "{}")
                incoming["niches"] = [run_config.get("niche", "")]
                incoming["locations"] = [run_config.get("location", "")]
                incoming["sources"] = list(
                    dict.fromkeys(
                        source_data.get("sources")
                        or (["local"] if source_data.get("source") == "osm_local" else ["web"])
                    )
                )
                record = session.get(RepositoryLeadRecord, candidate.domain)
                if record is None:
                    session.add(
                        RepositoryLeadRecord(
                            domain=candidate.domain,
                            data_json=json.dumps(incoming, ensure_ascii=False),
                            source_run_ids_json=json.dumps([run_id]),
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    added += 1
                    continue
                current = json.loads(record.data_json)
                record.data_json = json.dumps(
                    _merge_repository_lead(current, incoming),
                    ensure_ascii=False,
                )
                source_runs = json.loads(record.source_run_ids_json)
                if run_id not in source_runs:
                    source_runs.append(run_id)
                record.source_run_ids_json = json.dumps(source_runs)
                record.updated_at = now
                updated += 1
        total = len(self.list_repository_leads())
        return {
            "added": added,
            "updated": updated,
            "skipped": skipped,
            "total": total,
        }

    def list_repository_leads(self) -> list[dict[str, Any]]:
        with _REPOSITORY_IMPORT_LOCK, self.repository_write_lock(), self.sessions.begin() as session:
            rows = session.query(RepositoryLeadRecord).order_by(RepositoryLeadRecord.updated_at.desc()).all()
            results: list[dict[str, Any]] = []
            for row in rows:
                data = _prepare_repository_lead(promote_verified_business(json.loads(row.data_json)))
                if not _repository_eligible(data):
                    session.delete(row)
                    continue
                row.data_json = json.dumps(data, ensure_ascii=False)
                source_run_ids = json.loads(row.source_run_ids_json)
                if not data.get("niches") and source_run_ids:
                    source_runs = session.query(RunRecord).filter(RunRecord.id.in_(source_run_ids)).all()
                    run_configs = [json.loads(run.config_json) for run in source_runs]
                    data["niches"] = list(
                        dict.fromkeys(
                            config.get("niche", "").strip()
                            for config in run_configs
                            if config.get("niche", "").strip()
                        )
                    )
                    data["locations"] = list(
                        dict.fromkeys(
                            config.get("location", "").strip()
                            for config in run_configs
                            if config.get("location", "").strip()
                        )
                    )
                if not data.get("niches"):
                    data["niches"] = ["Uncategorised"]
                data.update(
                    {
                        "domain": row.domain,
                        "source_run_ids": source_run_ids,
                        "created_at": row.created_at.isoformat(),
                        "updated_at": row.updated_at.isoformat(),
                    }
                )
                results.append(data)
            return results

    def update_repository_lead(self, domain: str, changes: dict[str, Any]) -> dict[str, Any]:
        allowed = {"business_name", "city_or_area", "website", "emails", "phones", "niches"}
        clean_changes = {key: value for key, value in changes.items() if key in allowed and value is not None}
        with _REPOSITORY_IMPORT_LOCK, self.repository_write_lock(), self.sessions.begin() as session:
            row = session.get(RepositoryLeadRecord, domain)
            if row is None:
                raise KeyError(f"Unknown repository lead: {domain}")
            data = _prepare_repository_lead(json.loads(row.data_json))
            data.update(clean_changes)
            if "emails" in clean_changes:
                data["generic_email"] = clean_changes["emails"][0] if clean_changes["emails"] else ""
            if "phones" in clean_changes:
                data["phone"] = clean_changes["phones"][0] if clean_changes["phones"] else ""
            data = _prepare_repository_lead(data)
            row.data_json = json.dumps(data, ensure_ascii=False)
            row.updated_at = _now()
            result = dict(data)
            result.update(
                {
                    "domain": row.domain,
                    "source_run_ids": json.loads(row.source_run_ids_json),
                    "created_at": row.created_at.isoformat(),
                    "updated_at": row.updated_at.isoformat(),
                }
            )
            return result

    def delete_repository_lead(self, domain: str) -> dict[str, str]:
        with _REPOSITORY_IMPORT_LOCK, self.repository_write_lock(), self.sessions.begin() as session:
            row = session.get(RepositoryLeadRecord, domain)
            if row is None:
                raise KeyError(f"Unknown repository lead: {domain}")
            session.delete(row)
        return {"domain": domain, "status": "deleted"}

    def merge_repository_collections(self, sources: list[str], target: str) -> dict[str, Any]:
        source_names = {value.strip() for value in sources if value.strip()}
        target_name = target.strip()
        if not source_names or not target_name:
            raise ValueError("Source and target collections are required")
        changed = 0
        with _REPOSITORY_IMPORT_LOCK, self.repository_write_lock(), self.sessions.begin() as session:
            rows = session.query(RepositoryLeadRecord).all()
            for row in rows:
                data = _prepare_repository_lead(json.loads(row.data_json))
                niches = list(
                    dict.fromkeys(
                        str(value).strip() for value in data.get("niches", []) if str(value).strip()
                    )
                )
                if not source_names.intersection(niches):
                    continue
                remaining = [value for value in niches if value not in source_names and value != target_name]
                data["niches"] = [*remaining, target_name]
                row.data_json = json.dumps(_prepare_repository_lead(data), ensure_ascii=False)
                row.updated_at = _now()
                changed += 1
        return {
            "status": "merged",
            "sources": sorted(source_names),
            "target": target_name,
            "updated_leads": changed,
        }

    def delete_repository_collection(self, name: str) -> dict[str, Any]:
        collection = name.strip()
        if not collection:
            raise ValueError("Collection name is required")
        if collection == "Uncategorised":
            raise ValueError("The Uncategorised collection cannot be deleted")
        result = self.merge_repository_collections([collection], "Uncategorised")
        return {
            "status": "deleted",
            "collection": collection,
            "moved_to": "Uncategorised",
            "updated_leads": result["updated_leads"],
        }

    def repository_lead_count(self) -> int:
        with self.sessions() as session:
            return session.query(RepositoryLeadRecord).count()

    def app_settings(self) -> dict[str, str]:
        with self.sessions() as session:
            rows = session.query(AppSettingRecord).all()
            return {
                row.key: reveal_secret(row.value) if row.key in SECRET_SETTING_KEYS else row.value
                for row in rows
            }

    def update_app_settings(self, values: dict[str, str]) -> dict[str, str]:
        now = _now()
        with self.sessions.begin() as session:
            for key, value in values.items():
                if key in SECRET_SETTING_KEYS:
                    value = protect_secret(value)
                row = session.get(AppSettingRecord, key)
                if row is None:
                    session.add(AppSettingRecord(key=key, value=value, updated_at=now))
                else:
                    row.value = value
                    row.updated_at = now
        return self.app_settings()

    def find_cached_lead(self, domain: str, exclude_run_id: str = "") -> dict[str, Any] | None:
        with self.sessions() as session:
            query = (
                session.query(CandidateRecord)
                .options(joinedload(CandidateRecord.lead))
                .filter(CandidateRecord.domain == domain, CandidateRecord.status == "completed")
            )
            if exclude_run_id:
                query = query.filter(CandidateRecord.run_id != exclude_run_id)
            row = query.order_by(CandidateRecord.id.desc()).first()
            if row is None or row.lead is None:
                return None
            return _prepare_repository_lead(json.loads(row.lead.data_json))

    def seen_domains(self, niche: str, location: str, exclude_run_id: str = "") -> set[str]:
        with self.sessions() as session:
            run_ids = self._matching_market_run_ids(session, niche, location, exclude_run_id)
            if not run_ids:
                return set()
            rows = session.query(CandidateRecord.domain).filter(CandidateRecord.run_id.in_(run_ids))
            return {domain for (domain,) in rows}

    def market_history(self, niche: str, location: str) -> dict[str, Any]:
        with self.sessions() as session:
            run_ids = self._matching_market_run_ids(session, niche, location)
            if not run_ids:
                return {"previous_runs": 0, "seen_domains": 0, "completed_leads": 0}
            candidates = session.query(CandidateRecord).filter(CandidateRecord.run_id.in_(run_ids))
            return {
                "previous_runs": len(run_ids),
                "seen_domains": candidates.with_entities(CandidateRecord.domain).distinct().count(),
                "completed_leads": candidates.filter(CandidateRecord.status == "completed")
                .with_entities(CandidateRecord.domain)
                .distinct()
                .count(),
            }

    def integrity_check(self) -> str:
        with self.engine.connect() as connection:
            return str(connection.exec_driver_sql("PRAGMA integrity_check").scalar_one())

    def backup_to(self, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with (
            closing(sqlite3.connect(self.database_path)) as source,
            closing(sqlite3.connect(destination)) as target,
        ):
            source.backup(target)
        return destination

    def claim(self, run_id: str, domain: str, lease_seconds: int = 300) -> int:
        with self.sessions.begin() as session:
            candidate_id = session.execute(
                update(CandidateRecord)
                .where(
                    CandidateRecord.run_id == run_id,
                    CandidateRecord.domain == domain,
                    CandidateRecord.status.in_({"queued", "failed"}),
                )
                .values(
                    status="processing",
                    attempts=CandidateRecord.attempts + 1,
                    lease_until=_now() + timedelta(seconds=lease_seconds),
                    last_error="",
                )
                .returning(CandidateRecord.id)
            ).scalar_one_or_none()
            if candidate_id is None:
                row = self._candidate_by_domain(session, run_id, domain)
                raise ValueError(f"Cannot claim candidate in {row.status} state")
            self._event(session, run_id, "candidate_processing", {"domain": domain})
            return int(candidate_id)

    def set_candidate_selected(self, run_id: str, domain: str, selected: bool) -> dict[str, str]:
        with self.sessions.begin() as session:
            row = self._candidate_by_domain(session, run_id, domain)
            if row.status in {"processing", "completed"}:
                raise ValueError(f"Cannot change selection in {row.status} state")
            target = "queued" if selected else "cancelled"
            if row.status != target:
                self._transition(row, target)
            self._event(
                session,
                run_id,
                "candidate_selection_changed",
                {"domain": domain, "selected": selected},
            )
            return self._candidate_dict(row)

    def update_candidate_crawl(self, candidate_id: int, progress: dict[str, Any]) -> None:
        with self.sessions.begin() as session:
            row = session.get(CandidateRecord, candidate_id)
            if row is None or row.status != "processing":
                return
            source = json.loads(row.source_json or "{}")
            source.update(
                {
                    key: value
                    for key, value in progress.items()
                    if key
                    in {
                        "crawl_mode",
                        "crawl_pages_checked",
                        "crawl_page_limit",
                        "crawl_current_url",
                        "crawl_contacts_found",
                    }
                }
            )
            row.source_json = json.dumps(source, ensure_ascii=False)
            run = self._require_run(session, row.run_id)
            run.updated_at = _now()

    def complete(self, candidate_id: int, lead: dict[str, Any]) -> None:
        with self.sessions.begin() as session:
            row = session.get(CandidateRecord, candidate_id)
            if row is None:
                raise KeyError(f"Unknown candidate: {candidate_id}")
            self._transition(row, "completed")
            row.lease_until = None
            lead = _prepare_repository_lead(lead)
            record = row.lead or LeadRecord(candidate_id=row.id, created_at=_now())
            record.score = int(lead.get("lead_score") or 0)
            record.data_json = json.dumps(lead, ensure_ascii=False)
            session.add(record)
            self._event(session, row.run_id, "candidate_completed", {"domain": row.domain})

    def fail(self, candidate_id: int, error: str) -> None:
        with self.sessions.begin() as session:
            row = session.get(CandidateRecord, candidate_id)
            if row is None:
                raise KeyError(f"Unknown candidate: {candidate_id}")
            self._transition(row, "failed")
            row.lease_until = None
            row.last_error = error
            self._event(session, row.run_id, "candidate_failed", {"domain": row.domain, "error": error})

    def recover_for_resume(self, run_id: str) -> int:
        recovered = 0
        with self.sessions.begin() as session:
            run = self._require_run(session, run_id)
            run.status = "running"
            for row in run.candidates:
                if row.status in {"processing", "failed"}:
                    row.status = "queued"
                    row.lease_until = None
                    recovered += 1
            run.updated_at = _now()
            self._event(session, run_id, "run_resumed", {"recovered": recovered})
        return recovered

    def begin_run(self, run_id: str) -> None:
        with self.sessions.begin() as session:
            run = self._require_run(session, run_id)
            if run.status == "running":
                raise ValueError("Run is already running")
            if run.status == "cancelled":
                raise ValueError("Cancelled runs must be retried before starting")
            run.status = "running"
            run.updated_at = _now()
            self._event(session, run_id, "run_started", {})

    def finish_run(self, run_id: str, status: str, details: dict[str, Any] | None = None) -> None:
        if status not in RUN_TERMINAL:
            raise ValueError(f"Invalid terminal run status: {status}")
        with self.sessions.begin() as session:
            run = self._require_run(session, run_id)
            run.status = status
            run.updated_at = _now()
            self._event(session, run_id, f"run_{status}", details or {})

    def run_status(self, run_id: str) -> dict[str, Any]:
        with self.sessions() as session:
            run = self._require_run(session, run_id)
            counts: dict[str, int] = {}
            for row in run.candidates:
                counts[row.status] = counts.get(row.status, 0) + 1
            discovery_event = (
                session.query(EventRecord)
                .filter_by(run_id=run_id, event_type="candidates_added")
                .order_by(EventRecord.id.desc())
                .first()
            )
            return {
                "id": run.id,
                "run_name": run.run_name,
                "status": run.status,
                "counts": counts,
                "discovery": json.loads(discovery_event.payload_json) if discovery_event else {},
            }

    def list_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.sessions() as session:
            rows = session.query(RunRecord).order_by(RunRecord.created_at.desc()).limit(limit).all()
            return [
                {
                    "id": row.id,
                    "run_name": row.run_name,
                    "status": row.status,
                    "created_at": row.created_at.isoformat(),
                    "updated_at": row.updated_at.isoformat(),
                    "counts": self._status_counts(row.candidates),
                }
                for row in rows
            ]

    @staticmethod
    def _status_counts(candidates: list[CandidateRecord]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for candidate in candidates:
            counts[candidate.status] = counts.get(candidate.status, 0) + 1
        return counts

    def list_events(self, run_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        with self.sessions() as session:
            self._require_run(session, run_id)
            rows = (
                session.query(EventRecord)
                .filter(EventRecord.run_id == run_id, EventRecord.id > after_id)
                .order_by(EventRecord.id)
                .all()
            )
            return [
                {
                    "id": row.id,
                    "event": row.event_type,
                    "data": json.loads(row.payload_json),
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]

    def is_cancelled(self, run_id: str) -> bool:
        try:
            return self.run_status(run_id)["status"] in {"cancelled", "stopped"}
        except KeyError:
            return True

    def _event(self, session: Session, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        session.add(
            EventRecord(
                run_id=run_id,
                event_type=event_type,
                payload_json=json.dumps(payload, ensure_ascii=False),
                created_at=_now(),
            )
        )

    @staticmethod
    def _matching_market_run_ids(
        session: Session,
        niche: str,
        location: str,
        exclude_run_id: str = "",
    ) -> list[str]:
        scope = (_scope_value(niche), _scope_value(location))
        query = session.query(RunRecord)
        if exclude_run_id:
            query = query.filter(RunRecord.id != exclude_run_id)
        matching: list[str] = []
        for run in query:
            config = json.loads(run.config_json)
            if (_scope_value(config.get("niche", "")), _scope_value(config.get("location", ""))) == scope:
                matching.append(run.id)
        return matching

    @staticmethod
    def _require_run(session: Session, run_id: str) -> RunRecord:
        run = session.get(RunRecord, run_id)
        if run is None:
            raise KeyError(f"Unknown run: {run_id}")
        return run

    @staticmethod
    def _candidate_by_domain(session: Session, run_id: str, domain: str) -> CandidateRecord:
        row = session.query(CandidateRecord).filter_by(run_id=run_id, domain=domain).one_or_none()
        if row is None:
            raise KeyError(f"Unknown candidate domain: {domain}")
        return row

    @staticmethod
    def _transition(row: CandidateRecord, target: str) -> None:
        if target not in CANDIDATE_TRANSITIONS.get(row.status, set()):
            raise ValueError(f"Illegal candidate transition: {row.status} -> {target}")
        row.status = target

    @staticmethod
    def _candidate_dict(row: CandidateRecord) -> dict[str, Any]:
        result = {
            "title": row.title,
            "url": row.url,
            "homepage": row.homepage,
            "snippet": row.snippet,
            "domain": row.domain,
            "status": row.status,
        }
        with suppress(json.JSONDecodeError):
            result.update(json.loads(row.source_json or "{}"))
        return _repair_mojibake(result)


def _now() -> datetime:
    return datetime.now(UTC)


def _migrate_candidate_source(database_path: Path) -> None:
    with closing(sqlite3.connect(database_path)) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(candidates)")}
        if "source_json" not in columns:
            connection.execute("ALTER TABLE candidates ADD COLUMN source_json TEXT NOT NULL DEFAULT '{}'")
            connection.commit()


def _scope_value(value: str) -> str:
    return " ".join(value.casefold().split())


def _repair_mojibake(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _repair_mojibake(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_repair_mojibake(item) for item in value]
    if not isinstance(value, str) or not any(marker in value for marker in ("Ã", "Â", "â")):
        return value
    try:
        return value.encode("cp1252").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return value


def _prepare_repository_lead(data: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(data)
    emails = [
        str(value).strip().lower()
        for value in [*_contact_values(data.get("emails")), data.get("generic_email", "")]
        if str(value).strip()
    ]
    phones = unique_phones([*_contact_values(data.get("phones")), data.get("phone", "")])
    prepared["emails"] = list(dict.fromkeys(emails))[:3]
    prepared["phones"] = phones
    prepared["generic_email"] = prepared["emails"][0] if prepared["emails"] else ""
    prepared["phone"] = prepared["phones"][0] if prepared["phones"] else ""
    return prepared


def _repository_eligible(data: dict[str, Any]) -> bool:
    return data.get("is_valid_lead") is not False and is_contactable_lead(data)


def _merge_repository_lead(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    current = _prepare_repository_lead(current)
    incoming = _prepare_repository_lead(incoming)
    merged = dict(current)
    for field in ("emails", "phones", "services", "niches", "locations", "sources"):
        existing = current.get(field) if isinstance(current.get(field), list) else []
        fresh = incoming.get(field) if isinstance(incoming.get(field), list) else []
        limit = 3 if field in {"emails", "phones"} else 12
        merged[field] = (
            unique_phones([*existing, *fresh], limit=limit)
            if field == "phones"
            else list(dict.fromkeys([*existing, *fresh]))[:limit]
        )
    for field, value in incoming.items():
        if field not in {"emails", "phones", "services"} and value and not merged.get(field):
            merged[field] = value
    if int(incoming.get("lead_score") or 0) > int(current.get("lead_score") or 0):
        for field in ("lead_score", "lead_reason", "website_quality_note", "city_or_area", "business_type"):
            if incoming.get(field):
                merged[field] = incoming[field]
    merged["generic_email"] = merged["emails"][0] if merged["emails"] else ""
    merged["phone"] = merged["phones"][0] if merged["phones"] else ""
    return merged


def _contact_values(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return [value] if value else []
