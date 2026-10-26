"""Persistence for TraceRecords. SQLite by default (one file, zero setup); pass a Postgres URL
and the same schema applies, because the dashboard and `llm-cost-tracer report` read Storage,
not a specific database -- swapping LLM_COST_TRACER_DB_URL is the only change needed to move
from a laptop to a shared Postgres instance.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, Float, Integer, String, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from llm_cost_tracer.models import TraceRecord


class Base(DeclarativeBase):
    pass


class TraceRow(Base):
    __tablename__ = "llm_cost_tracer_records"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    latency_ms: Mapped[float] = mapped_column(Float)
    provider: Mapped[str] = mapped_column(String, index=True)
    model: Mapped[str] = mapped_column(String, index=True)
    operation: Mapped[str] = mapped_column(String, index=True)
    project: Mapped[str] = mapped_column(String, index=True)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[float] = mapped_column(Float)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class Storage:
    def __init__(self, url: str = "sqlite:///llm_cost_tracer.db") -> None:
        self.engine = create_engine(url, future=True)
        Base.metadata.create_all(self.engine)
        self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def save(self, record: TraceRecord) -> None:
        row = TraceRow(
            id=record.id,
            started_at=datetime.fromtimestamp(record.started_at, tz=timezone.utc),
            latency_ms=record.latency_ms,
            provider=record.provider,
            model=record.model,
            operation=record.operation,
            project=record.project,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            cost_usd=record.cost_usd,
            quality_score=record.quality_score,
            status=record.status,
            error=record.error,
            metadata_json=record.metadata,
        )
        with self._session_factory() as session:
            session.merge(row)
            session.commit()

    def query(
        self,
        *,
        project: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        status: str | None = None,
        limit: int = 500,
    ) -> list[TraceRow]:
        stmt = select(TraceRow).order_by(TraceRow.started_at.desc()).limit(limit)
        if project:
            stmt = stmt.where(TraceRow.project == project)
        if provider:
            stmt = stmt.where(TraceRow.provider == provider)
        if model:
            stmt = stmt.where(TraceRow.model == model)
        if status:
            stmt = stmt.where(TraceRow.status == status)
        with self._session_factory() as session:
            return list(session.scalars(stmt))

    def summary(self, *, project: str | None = None) -> dict[str, Any]:
        stmt = select(
            func.count(TraceRow.id),
            func.coalesce(func.sum(TraceRow.cost_usd), 0.0),
            func.coalesce(func.avg(TraceRow.latency_ms), 0.0),
            func.coalesce(func.sum(TraceRow.input_tokens), 0),
            func.coalesce(func.sum(TraceRow.output_tokens), 0),
            func.avg(TraceRow.quality_score),
        )
        if project:
            stmt = stmt.where(TraceRow.project == project)
        with self._session_factory() as session:
            count, total_cost, avg_latency, in_tok, out_tok, avg_quality = session.execute(
                stmt
            ).one()
        return {
            "calls": count,
            "total_cost_usd": float(total_cost),
            "avg_latency_ms": float(avg_latency),
            "input_tokens": int(in_tok),
            "output_tokens": int(out_tok),
            "avg_quality_score": float(avg_quality) if avg_quality is not None else None,
        }
