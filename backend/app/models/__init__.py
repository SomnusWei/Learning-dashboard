"""集中导出所有 ORM 模型，便于 Alembic 自动检测与 import 一次性建表。"""
from app.core.database import Base
from app.models.formula_song import FormulaSong
from app.models.knowledge import KnowledgeBase, KnowledgeCard
from app.models.plan import DailyPlan, MonthlyGoal, PlanTemplate
from app.models.study import StudyLog, UserBackground
from app.models.subject import Subject
from app.models.todo import Todo
from app.models.user import User
from app.models.wrong_question import WrongQuestion

__all__ = [
    "Base",
    "User",
    "Subject",
    "WrongQuestion",
    "DailyPlan",
    "MonthlyGoal",
    "PlanTemplate",
    "Todo",
    "KnowledgeBase",
    "KnowledgeCard",
    "StudyLog",
    "UserBackground",
    "FormulaSong",
]
