"""方歌库：CRUD + 搜索 + 切换加入待办状态。"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.formula_song import FormulaSong
from app.models.todo import Todo
from app.models.user import User

router = APIRouter(prefix="/formula-songs", tags=["formula-songs"])


class FormulaSongIn(BaseModel):
    name: str = Field(..., max_length=100)
    song: str
    related_formula: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    is_mastered: bool = False


class FormulaSongOut(FormulaSongIn):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


@router.get("", response_model=list[FormulaSongOut], summary="方歌列表（支持搜索）")
def list_songs(
    q: str | None = Query(None, description="按方剂名/方歌模糊搜索"),
    is_mastered: bool | None = Query(None, description="是否已掌握"),
    limit: int = Query(500, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(FormulaSong).filter(FormulaSong.user_id == user.id)
    if q:
        like = f"%{q}%"
        query = query.filter(
            FormulaSong.name.ilike(like) | FormulaSong.song.ilike(like)
        )
    if is_mastered is not None:
        query = query.filter(FormulaSong.is_mastered == is_mastered)
    return query.order_by(FormulaSong.created_at.desc()).limit(limit).all()


@router.post("", response_model=FormulaSongOut, status_code=201, summary="新增方歌")
def create_song(body: FormulaSongIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # 方剂名重复检测：同用户同名已存在则拒绝
    exists = db.query(FormulaSong).filter(
        FormulaSong.user_id == user.id,
        FormulaSong.name == body.name,
    ).first()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, f"方剂「{body.name}」已存在，不可重复入库")
    song = FormulaSong(user_id=user.id, **body.model_dump())
    db.add(song)
    db.commit()
    db.refresh(song)
    return song


@router.get("/{song_id}", response_model=FormulaSongOut, summary="获取方歌详情")
def get_song(song_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    song = db.get(FormulaSong, song_id)
    if not song or song.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "方歌不存在")
    return song


@router.put("/{song_id}", response_model=FormulaSongOut, summary="更新方歌")
def update_song(song_id: int, body: FormulaSongIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    song = db.get(FormulaSong, song_id)
    if not song or song.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "方歌不存在")
    for k, v in body.model_dump().items():
        setattr(song, k, v)
    db.commit()
    db.refresh(song)
    return song


@router.delete("/{song_id}", status_code=204, summary="删除方歌")
def delete_song(song_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    song = db.get(FormulaSong, song_id)
    if not song or song.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "方歌不存在")
    db.delete(song)
    db.commit()


@router.patch("/{song_id}/toggle-todo", response_model=FormulaSongOut, summary="切换加入待办状态")
def toggle_todo(song_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """勾选：创建/恢复关联待办，标记 is_mastered=True；取消勾选：删除关联待办，is_mastered=False。"""
    song = db.get(FormulaSong, song_id)
    if not song or song.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "方歌不存在")
    if song.is_mastered:
        # 取消勾选：删除关联待办
        db.query(Todo).filter(
            Todo.user_id == user.id,
            Todo.ref_type == "formula_song",
            Todo.ref_id == song.id,
        ).delete(synchronize_session=False)
        song.is_mastered = False
    else:
        # 加入待办：已有则恢复 pending，无则新建
        existing = db.query(Todo).filter(
            Todo.user_id == user.id,
            Todo.ref_type == "formula_song",
            Todo.ref_id == song.id,
        ).first()
        if existing:
            existing.status = "pending"
            existing.completed_at = None
        else:
            db.add(Todo(
                user_id=user.id,
                title=f"复习方歌：{song.name}",
                source="formula_song",
                priority=2,
                status="pending",
                ref_type="formula_song",
                ref_id=song.id,
            ))
        song.is_mastered = True
    db.commit()
    db.refresh(song)
    return song


class BatchIn(BaseModel):
    text: str = Field(..., description="批量文本：三行一组（方剂名/方歌行1/方歌行2），组间空行分隔")


@router.post("/batch", summary="批量导入方歌")
def batch_import(body: BatchIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """解析文本：三行一组（方剂名/方歌行1/方歌行2），组间空行分隔。
    返回 {imported, skipped, errors}。"""
    lines = [ln.strip() for ln in body.text.splitlines()]
    # 按空行分组
    groups: list[list[str]] = []
    current: list[str] = []
    for ln in lines:
        if ln:
            current.append(ln)
        else:
            if current:
                groups.append(current)
                current = []
    if current:
        groups.append(current)

    imported = 0
    skipped = 0
    errors: list[str] = []
    for i, g in enumerate(groups, 1):
        if len(g) < 3:
            errors.append(f"第 {i} 组「{g[0] if g else ''}」少于 3 行，跳过")
            skipped += 1
            continue
        name = g[0]
        song = "\n".join(g[1:3])  # 第 2、3 行作为方歌
        # 已存在则跳过
        exists = db.query(FormulaSong).filter(
            FormulaSong.user_id == user.id,
            FormulaSong.name == name,
        ).first()
        if exists:
            skipped += 1
            errors.append(f"「{name}」已存在，跳过")
            continue
        db.add(FormulaSong(
            user_id=user.id,
            name=name,
            song=song,
            is_mastered=False,
        ))
        imported += 1
    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors}

