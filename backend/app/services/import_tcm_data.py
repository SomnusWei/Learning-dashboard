"""知识基础数据导入：中药库 + 方剂库。

用法：
  1. API:  POST /api/v1/knowledge-base/import-preset  (需 admin 登录)
  2. CLI:  docker exec ld-backend python -m app.services.import_tcm_data --user-id 1
"""
from __future__ import annotations

import argparse

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.knowledge import KnowledgeBase, KnowledgeCard
from app.models.user import User
from app.services.data.herbs import HERBS
from app.services.data.formulas import FORMULAS
from app.services.data.acupoints import ACUPOINTS

# 知识库名称 -> 数据列表
PRESET_DATASETS: dict[str, list[dict]] = {
    "中药库": HERBS,
    "方剂库": FORMULAS,
    "穴位库": ACUPOINTS,
}


def import_preset_data(user_id: int, db: Session, *, skip_existing: bool = True) -> dict:
    """将预置中药/方剂数据导入到对应用户的知识库中。

    返回每个知识库的导入统计：{lib_name: {"added": int, "skipped": int}}
    """
    stats: dict = {}
    for lib_name, cards in PRESET_DATASETS.items():
        lib = (
            db.query(KnowledgeBase)
            .filter(
                KnowledgeBase.user_id == user_id,
                KnowledgeBase.name == lib_name,
            )
            .first()
        )
        if not lib:
            stats[lib_name] = {"added": 0, "skipped": 0, "error": "知识库不存在"}
            continue

        existing_names = {
            name
            for (name,) in db.query(KnowledgeCard.name)
            .filter(KnowledgeCard.base_id == lib.id)
            .all()
        }
        added = 0
        skipped = 0
        for item in cards:
            name = item["fields"].get("药名") or item["fields"].get("方名") or item["fields"].get("穴名") or ""
            if not name:
                continue
            if skip_existing and name in existing_names:
                skipped += 1
                continue
            db.add(
                KnowledgeCard(
                    user_id=user_id,
                    base_id=lib.id,
                    name=name,
                    fields=item["fields"],
                    tags=item.get("tags", []),
                )
            )
            existing_names.add(name)
            added += 1
        db.commit()
        stats[lib_name] = {"added": added, "skipped": skipped}
    return stats


def _cli() -> None:
    parser = argparse.ArgumentParser(description="导入预置中药/方剂数据")
    parser.add_argument("--user-id", type=int, required=True, help="目标用户 ID")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = db.get(User, args.user_id)
        if not user:
            print(f"用户 {args.user_id} 不存在")
            return
        stats = import_preset_data(args.user_id, db)
        for lib, s in stats.items():
            print(f"{lib}: 新增 {s.get('added', 0)} 条，跳过 {s.get('skipped', 0)} 条"
                  + (f"，错误: {s['error']}" if "error" in s else ""))
    finally:
        db.close()


if __name__ == "__main__":
    _cli()
