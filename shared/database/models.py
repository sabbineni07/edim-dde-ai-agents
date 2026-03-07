"""Database models."""
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Date, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
import uuid

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


class RecommendationHistory(Base):
    __tablename__ = "recommendations_history"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(UUID(as_uuid=True), unique=True, index=True, default=uuid.uuid4)
    job_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=True)
    workspace_id = Column(String(255), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=func.now(), index=True)
    recommendation = Column(JSONB, nullable=False)
    explanation = Column(Text, nullable=True)
    pattern_analysis = Column(Text, nullable=True)
    risk_assessment = Column(JSONB, nullable=True)
    token_usage_analysis = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
