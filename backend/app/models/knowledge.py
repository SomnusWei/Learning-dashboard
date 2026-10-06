"""知识库与知识卡片：通用结构，按知识库类型存储不同字段到 fields JSONB。

fields 字段说明（按知识库类型）：
- 中药库: {药名, 性味, 归经, 功效, 用法, 禁忌, 附记}
- 方剂库: {方名, 组成, 用法, 功用, 主治, 方解, 加减, 方剂歌诀}  ← 方剂歌诀以十四五《方剂学》教材为准
- 穴位库: {穴名, 定位, 归经, 主治, 刺灸法, 配伍}

images JSONB：图片列表（中药药材图、穴位定位图，暂为空，后期补录）
"""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class KnowledgeBase(Base):
    """__tablename__ 与 Python 类名冲突，故用单独名 KnowledgeBaseLib。"""

    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 字段定义：[{name, label, type}]
    field_schema: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_preset: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class KnowledgeCard(Base):
    __tablename__ = "knowledge_cards"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    images: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    tags: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")

    # Anki SM-2 字段
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5, server_default="2.5")
    interval_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    repetitions: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    due_date: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    last_reviewed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    is_learned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
