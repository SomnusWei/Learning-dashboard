"""方歌库：背诵方剂方歌（独立表，不依赖方剂库）。"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class FormulaSong(Base):
    __tablename__ = "formula_songs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # 方剂名
    song: Mapped[str] = mapped_column(Text, nullable=False)  # 方歌
    related_formula: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # 关联方剂名（文本）
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 备注
    is_mastered: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, onupdate=func.now())
