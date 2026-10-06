"""全局搜索：方剂 / 中药 / 穴位 / 方歌 联合搜索与联想提示。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, cast, Text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.knowledge import KnowledgeBase, KnowledgeCard
from app.models.formula_song import FormulaSong
from app.models.user import User

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", summary="搜索方剂/中药/穴位/方歌")
def search(q: str = Query(..., min_length=1), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """跨知识库搜索：名称 + fields 全文匹配，返回中药 / 方剂 / 穴位 / 方歌 四类结果。"""
    pattern = f"%{q}%"
    # 名称匹配优先，其次 fields 文本
    cards = (
        db.query(KnowledgeCard, KnowledgeBase.name.label("lib_name"), KnowledgeBase.id.label("lib_id"))
        .join(KnowledgeBase, KnowledgeCard.base_id == KnowledgeBase.id)
        .filter(KnowledgeCard.user_id == user.id)
        .filter(
            or_(
                KnowledgeCard.name.ilike(pattern),
                cast(KnowledgeCard.fields, Text).ilike(pattern),
            )
        )
        .order_by(KnowledgeCard.name)
        .limit(60)
        .all()
    )
    grouped: dict[str, list] = {}
    for card, lib_name, lib_id in cards:
        grouped.setdefault(lib_name, []).append(
            {
                "id": card.id,
                "base_id": lib_id,
                "name": card.name,
                "fields": card.fields,
                "images": card.images,
            }
        )
    # 方歌库搜索：方剂名 / 方歌 / 关联方剂 / 备注
    songs = (
        db.query(FormulaSong)
        .filter(FormulaSong.user_id == user.id)
        .filter(
            or_(
                FormulaSong.name.ilike(pattern),
                FormulaSong.song.ilike(pattern),
                FormulaSong.related_formula.ilike(pattern),
                FormulaSong.notes.ilike(pattern),
            )
        )
        .order_by(FormulaSong.name)
        .limit(40)
        .all()
    )
    if songs:
        grouped.setdefault("方歌库", []).extend(
            [
                {
                    "id": s.id,
                    "base_id": -1,
                    "name": s.name,
                    "fields": {
                        "方歌": s.song,
                        "关联方剂": s.related_formula or "",
                        "备注": s.notes or "",
                        "已掌握": "是" if s.is_mastered else "否",
                    },
                    "images": [],
                }
                for s in songs
            ]
        )
    return {"query": q, "results": grouped}


@router.get("/suggest", summary="联想提示")
def suggest(q: str = Query("", min_length=1), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    pattern = f"%{q}%"
    names = (
        db.query(KnowledgeCard.name)
        .filter(KnowledgeCard.user_id == user.id, KnowledgeCard.name.ilike(pattern))
        .distinct()
        .order_by(KnowledgeCard.name)
        .limit(12)
        .all()
    )
    suggestions = [n[0] for n in names]
    # 方歌库的方剂名也加入联想
    song_names = (
        db.query(FormulaSong.name)
        .filter(FormulaSong.user_id == user.id, FormulaSong.name.ilike(pattern))
        .distinct()
        .order_by(FormulaSong.name)
        .limit(8)
        .all()
    )
    suggestions.extend([n[0] for n in song_names if n[0] not in suggestions])
    return {"suggestions": suggestions[:15]}

