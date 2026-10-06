"""知识库管理：三大预置库 + 自定义库；卡片 CRUD。"""
import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.knowledge import KnowledgeBase, KnowledgeCard
from app.models.user import User
from app.services.import_tcm_data import import_preset_data

router = APIRouter(prefix="/knowledge-base", tags=["knowledge-base"])


class LibraryIn(BaseModel):
    name: str = Field(..., max_length=100)
    description: str | None = None
    field_schema: list = Field(default_factory=list)


class LibraryOut(LibraryIn):
    id: int
    is_preset: bool

    class Config:
        from_attributes = True


class CardIn(BaseModel):
    name: str = Field(..., max_length=200)
    fields: dict = {}
    images: list = Field(default_factory=list)
    tags: list = Field(default_factory=list)


class CardOut(CardIn):
    id: int
    base_id: int

    class Config:
        from_attributes = True


# ===== 知识库 =====

@router.get("/libraries", response_model=list[LibraryOut], summary="知识库列表")
def list_libraries(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(KnowledgeBase).filter(KnowledgeBase.user_id == user.id).all()


@router.post("/libraries", response_model=LibraryOut, status_code=201, summary="创建知识库")
def create_library(body: LibraryIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lib = KnowledgeBase(user_id=user.id, **body.model_dump())
    db.add(lib)
    db.commit()
    db.refresh(lib)
    return lib


@router.delete("/libraries/{lib_id}", status_code=204, summary="删除知识库")
def delete_library(lib_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lib = db.get(KnowledgeBase, lib_id)
    if not lib or lib.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "知识库不存在")
    if lib.is_preset:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "预置知识库不可删除")
    db.query(KnowledgeCard).filter(KnowledgeCard.base_id == lib_id).delete()
    db.delete(lib)
    db.commit()


# ===== 卡片 =====

@router.get("/{lib_id}/cards", response_model=list[CardOut], summary="卡片列表")
def list_cards(lib_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return (
        db.query(KnowledgeCard)
        .filter(KnowledgeCard.user_id == user.id, KnowledgeCard.base_id == lib_id)
        .order_by(KnowledgeCard.created_at.desc())
        .limit(200)
        .all()
    )


@router.post("/{lib_id}/cards", response_model=CardOut, status_code=201, summary="新增卡片")
def create_card(lib_id: int, body: CardIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lib = db.get(KnowledgeBase, lib_id)
    if not lib or lib.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "知识库不存在")
    card = KnowledgeCard(user_id=user.id, base_id=lib_id, **body.model_dump())
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


@router.put("/cards/{card_id}", response_model=CardOut, summary="更新卡片")
def update_card(card_id: int, body: CardIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    card = db.get(KnowledgeCard, card_id)
    if not card or card.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "卡片不存在")
    for k, v in body.model_dump().items():
        setattr(card, k, v)
    db.commit()
    db.refresh(card)
    return card


@router.delete("/cards/{card_id}", status_code=204, summary="删除卡片")
def delete_card(card_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    card = db.get(KnowledgeCard, card_id)
    if not card or card.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "卡片不存在")
    db.delete(card)
    db.commit()


class ImportIn(BaseModel):
    lib_id: int
    cards: list[CardIn]
    skip_existing: bool = True


@router.post("/import", summary="批量导入卡片（JSON）")
def import_cards(body: ImportIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lib = db.get(KnowledgeBase, body.lib_id)
    if not lib or lib.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "知识库不存在")
    existing_names = {
        c[0]
        for c in db.query(KnowledgeCard.name)
        .filter(KnowledgeCard.base_id == body.lib_id, KnowledgeCard.user_id == user.id)
        .all()
    }
    added, skipped = 0, 0
    for card_in in body.cards:
        if body.skip_existing and card_in.name in existing_names:
            skipped += 1
            continue
        card = KnowledgeCard(user_id=user.id, base_id=body.lib_id, **card_in.model_dump())
        db.add(card)
        existing_names.add(card_in.name)
        added += 1
    db.commit()
    return {"added": added, "skipped": skipped, "total": len(body.cards)}


@router.post("/import-preset", summary="导入预置中药/方剂数据")
def import_preset(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """将内置的中药库、方剂库预置数据导入到当前用户的知识库。幂等：已存在的卡片按名称跳过。"""
    stats = import_preset_data(user.id, db)
    return {"stats": stats}


@router.get("/export/{lib_id}", summary="批量导出知识库卡片")
def export_lib(
    lib_id: int,
    format: str = Query("json", description="导出格式：json 或 csv"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    lib = db.get(KnowledgeBase, lib_id)
    if not lib or lib.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "知识库不存在")
    cards = (
        db.query(KnowledgeCard)
        .filter(KnowledgeCard.base_id == lib_id, KnowledgeCard.user_id == user.id)
        .order_by(KnowledgeCard.created_at)
        .all()
    )
    if format == "csv":
        output = io.StringIO()
        if cards:
            fieldnames = ["name"]
            # 收集所有字段名
            for c in cards:
                for k in (c.fields or {}).keys():
                    if k not in fieldnames:
                        fieldnames.append(k)
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for c in cards:
                row = {"name": c.name}
                for k in fieldnames[1:]:
                    row[k] = (c.fields or {}).get(k, "")
                writer.writerow(row)
        content = output.getvalue().encode("utf-8-sig")
        filename = f"{lib.name}.csv"
        media = "text/csv"
    else:
        data = [
            {"name": c.name, "fields": c.fields, "tags": c.tags, "images": c.images}
            for c in cards
        ]
        content = json.dumps({"library": lib.name, "cards": data}, ensure_ascii=False, indent=2).encode("utf-8")
        filename = f"{lib.name}.json"
        media = "application/json"
    return StreamingResponse(
        iter([content]),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
