"""待办事项：含浏览器扩展剪藏来源。"""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import ForeignKey, Index, Integer, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Todo(Base):
    __tablename__ = "todos"
    __table_args__ = (Index("idx_todos_ref", "ref_type", "ref_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # manual/extension/formula_song
    priority: Mapped[int] = mapped_column(Integer, default=2, server_default="2")  # 1高 2中 3低
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    due_date: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    ref_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # 关联类型，如 'formula_song'
    ref_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 关联对象 ID
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
