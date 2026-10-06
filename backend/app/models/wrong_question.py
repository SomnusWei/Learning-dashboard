"""错题表：含 OCR 图片附件、Anki 复习算法字段。"""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, TIMESTAMP, DATE
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WrongQuestion(Base):
    __tablename__ = "wrong_questions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    subject_id: Mapped[Optional[int]] = mapped_column(ForeignKey("subjects.id"), nullable=True)

    question_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # choice/fill/essay
    content: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    analysis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    images: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")

    correct_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    wrong_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_reviewed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    next_review_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)

    # Anki SM-2 字段（保留兼容）
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5, server_default="2.5")
    interval_days: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    is_mastered: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # FSRS 调度状态（JSONB：存 fsrs Card 的可序列化字段）
    fsrs_state: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
