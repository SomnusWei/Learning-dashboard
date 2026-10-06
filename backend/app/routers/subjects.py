"""科目标签：自定义增删改查。"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.subject import Subject
from app.models.user import User

router = APIRouter(prefix="/subjects", tags=["subjects"])


class SubjectIn(BaseModel):
    name: str = Field(..., max_length=100)
    color: str = "#4CAF50"
    parent_id: int | None = None
    sort_order: int = 0


class SubjectOut(SubjectIn):
    id: int

    class Config:
        from_attributes = True


@router.get("", response_model=list[SubjectOut], summary="标签列表")
def list_subjects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Subject).filter(Subject.user_id == user.id).order_by(Subject.sort_order).all()


@router.post("", response_model=SubjectOut, status_code=201, summary="新增标签")
def create_subject(body: SubjectIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    subject = Subject(user_id=user.id, **body.model_dump())
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return subject


@router.put("/{subject_id}", response_model=SubjectOut, summary="更新标签")
def update_subject(subject_id: int, body: SubjectIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    subject = db.get(Subject, subject_id)
    if not subject or subject.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "标签不存在")
    for k, v in body.model_dump().items():
        setattr(subject, k, v)
    db.commit()
    db.refresh(subject)
    return subject


@router.delete("/{subject_id}", status_code=204, summary="删除标签")
def delete_subject(subject_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    subject = db.get(Subject, subject_id)
    if not subject or subject.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "标签不存在")
    db.delete(subject)
    db.commit()
