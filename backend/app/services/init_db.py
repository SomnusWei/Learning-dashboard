"""首次启动时调用：建表 + 预置中医学科标签 + 预置三大知识库（含字段定义）。"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import Base, engine
from app.models import (
    KnowledgeBase,
    Subject,
    User,
)


# 预置科目标签（中医学科）
PRESET_SUBJECTS = [
    {"name": "中医基础理论", "color": "#5B8DEF", "sort_order": 1},
    {"name": "中医诊断学", "color": "#FF6B6B", "sort_order": 2},
    {"name": "中药学", "color": "#51CF7E", "sort_order": 3},
    {"name": "方剂学", "color": "#FFB740", "sort_order": 4},
    {"name": "针灸学", "color": "#A56FF5", "sort_order": 5},
    {"name": "中医内科学", "color": "#26C9DD", "sort_order": 6},
]


# 三大知识库字段定义
HERB_SCHEMA = [
    {"name": "药名", "label": "药名", "type": "text"},
    {"name": "性味", "label": "性味", "type": "text"},
    {"name": "归经", "label": "归经", "type": "text"},
    {"name": "功效", "label": "功效", "type": "text"},
    {"name": "用法", "label": "用法", "type": "text"},
    {"name": "禁忌", "label": "禁忌", "type": "text"},
    {"name": "附记", "label": "附记", "type": "text"},
    {"name": "图片", "label": "药材图片", "type": "images"},
]

PRESCRIPTION_SCHEMA = [
    {"name": "方名", "label": "方名", "type": "text"},
    {"name": "组成", "label": "组成", "type": "text"},
    {"name": "用法", "label": "用法", "type": "text"},
    {"name": "功用", "label": "功用", "type": "text"},
    {"name": "主治", "label": "主治", "type": "text"},
    {"name": "方解", "label": "方解", "type": "text"},
    {"name": "加减", "label": "加减", "type": "text"},
    {"name": "方剂歌诀", "label": "方剂歌诀", "type": "text"},
]

ACUPOINT_SCHEMA = [
    {"name": "穴名", "label": "穴名", "type": "text"},
    {"name": "定位", "label": "定位", "type": "text"},
    {"name": "归经", "label": "归经", "type": "text"},
    {"name": "主治", "label": "主治", "type": "text"},
    {"name": "刺灸法", "label": "刺灸法", "type": "text"},
    {"name": "配伍", "label": "配伍", "type": "text"},
    {"name": "图片", "label": "穴位图片", "type": "images"},
]


def init_database() -> None:
    """创建所有表。PostgreSQL 已存在时直接建表，幂等。"""
    Base.metadata.create_all(bind=engine)
    # 增量迁移：错题表新增 fsrs_state JSONB 列
    with engine.begin() as conn:
        conn.execute(text("""
            ALTER TABLE wrong_questions
            ADD COLUMN IF NOT EXISTS fsrs_state JSONB
        """))


def seed_preset_data(user_id: int, db: Session) -> None:
    """为新用户预置科目标签与三大知识库（仅在该用户首次创建时调用）。"""
    # 1) 预置科目标签
    if not db.query(Subject).filter(Subject.user_id == user_id).first():
        for s in PRESET_SUBJECTS:
            db.add(Subject(user_id=user_id, **s))

    # 2) 预置三大知识库
    existing_libs = {lib.name for lib in db.query(KnowledgeBase).filter(KnowledgeBase.user_id == user_id).all()}
    preset_libs = [
        {"name": "中药库", "description": "预置中药知识库（TCM-MKG V2.0 数据集）", "field_schema": HERB_SCHEMA},
        {"name": "方剂库", "description": "预置方剂知识库（十四五《方剂学》教材为准）", "field_schema": PRESCRIPTION_SCHEMA},
        {"name": "穴位库", "description": "预置穴位知识库（十四经穴 361 穴）", "field_schema": ACUPOINT_SCHEMA},
    ]
    for lib in preset_libs:
        if lib["name"] not in existing_libs:
            db.add(
                KnowledgeBase(
                    user_id=user_id,
                    name=lib["name"],
                    description=lib["description"],
                    field_schema=lib["field_schema"],
                    is_preset=True,
                )
            )
    db.commit()
