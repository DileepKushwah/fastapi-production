from datetime import datetime
from sqlalchemy import String, Text, DateTime, Float, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class AISummary(Base):
    __tablename__ = "ai_summaries"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    text_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    execution_time_ms: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())