"""学习记录与用户背景图。"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, TIMESTAMP, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StudyLog(Base):
    """每日学习记录，热力图与统计的数据源。"""

    __tablename__ = "study_logs"
    __table_args__ = (UniqueConstraint("user_id", "log_date", name="uq_user_log_date"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    log_date: Mapped[str] = mapped_column(Date, nullable=False)
    study_duration: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # 秒
    new_cards: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    review_cards: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    new_wrong_questions: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    plan_completed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class UserBackground(Base):
    __tablename__ = "user_backgrounds"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    image_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_dark: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
