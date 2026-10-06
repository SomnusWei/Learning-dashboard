"""用户表：单用户架构，但保留 user_id 便于日后扩展多用户/鸿蒙端。"""
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=lambda: {}, server_default="{}")
    # 系统级标记：是否已完成首次启动初始化
    # 单用户场景下：users 表是否有记录 = 系统是否已初始化
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
