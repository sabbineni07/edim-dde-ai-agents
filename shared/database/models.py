"""Database models."""

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class CostUsageLog(Base):
    __tablename__ = "cost_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(UUID(as_uuid=True), default=uuid.uuid4, index=True)
    job_id = Column(String(255), index=True, nullable=True)
    user_id = Column(String(255), nullable=True)
    workspace_id = Column(String(255), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=func.now(), index=True)
    model_name = Column(String(50), nullable=False, index=True)
    chain_name = Column(String(50), nullable=False, index=True)
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    total_tokens = Column(Integer, nullable=False)
    cost_usd = Column(Numeric(10, 6), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())


class DailyCostSummary(Base):
    __tablename__ = "daily_cost_summary"

    date = Column(Date, primary_key=True)
    total_requests = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    total_cost_usd = Column(Numeric(10, 2), default=0)
    avg_cost_per_request = Column(Numeric(10, 6), default=0)
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())


class RequestLog(Base):
    """Log of each API request (success or failure). Generic across endpoints."""

    __tablename__ = "request_logs"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(UUID(as_uuid=True), unique=True, index=True, default=uuid.uuid4)
    endpoint = Column(String(255), nullable=False, index=True)
    request_params = Column(JSONB, nullable=False, default=dict)
    job_id = Column(
        String(255), nullable=True, index=True
    )  # denormalized for fast queries (recommendation endpoint)
    timestamp = Column(DateTime(timezone=True), default=func.now(), index=True)
    status = Column(String(50), nullable=False, index=True)
    duration_ms = Column(Integer, nullable=True)
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    user_id = Column(String(255), nullable=True)
    workspace_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())


class RecommendationHistory(Base):
    __tablename__ = "recommendations_history"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(UUID(as_uuid=True), unique=True, index=True, default=uuid.uuid4)
    request_log_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("request_logs.request_id"),
        nullable=True,
        index=True,
    )
    job_id = Column(String(255), nullable=False, index=True)
    job_run_id = Column(String(255), nullable=True, index=True)
    user_id = Column(String(255), nullable=True)
    workspace_id = Column(String(255), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=func.now(), index=True)
    recommendation = Column(JSONB, nullable=False)
    explanation = Column(Text, nullable=True)
    pattern_analysis = Column(Text, nullable=True)
    risk_assessment = Column(JSONB, nullable=True)
    token_usage_analysis = Column(JSONB, nullable=True)
    comparison = Column(JSONB, nullable=True)
    reason_codes = Column(JSONB, nullable=True)
    lifecycle_status = Column(String(64), nullable=True, index=True)
    lifecycle_updated_at = Column(DateTime(timezone=True), nullable=True)
    lifecycle_updated_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())


class RecommendationLifecycleEvent(Base):
    """Audit trail for recommendation adoption lifecycle transitions."""

    __tablename__ = "recommendation_lifecycle_events"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("recommendations_history.request_id"),
        nullable=False,
        index=True,
    )
    from_status = Column(String(64), nullable=True)
    to_status = Column(String(64), nullable=False, index=True)
    changed_by = Column(String(255), nullable=False)
    changed_at = Column(DateTime(timezone=True), default=func.now(), index=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())


class WorkspaceConnection(Base):
    """Workspace-scoped integration (non-secret config in JSONB)."""

    __tablename__ = "workspace_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    workspace_id = Column(String(255), nullable=False, index=True)
    workspace_name = Column(String(512), nullable=True)
    connection_type = Column(String(64), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    config = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())


class WorkspaceAgent(Base):
    """Agent enabled on a workspace with connection bindings per role."""

    __tablename__ = "workspace_agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    workspace_id = Column(String(255), nullable=False, index=True)
    workspace_name = Column(String(512), nullable=True)
    agent_id = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    bindings = Column(JSONB, nullable=False, default=dict)
    agent_settings = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
