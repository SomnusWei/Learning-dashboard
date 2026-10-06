"""用户设置：通用设置、主题、背景图、数据备份。"""
import copy
import json
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.knowledge import KnowledgeBase, KnowledgeCard
from app.models.plan import DailyPlan
from app.models.study import StudyLog
from app.models.subject import Subject
from app.models.todo import Todo
from app.models.user import User
from app.models.wrong_question import WrongQuestion

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsIn(BaseModel):
    settings: dict


@router.get("", summary="用户设置")
def get_settings(user: User = Depends(get_current_user)):
    return user.settings or {}


@router.put("", summary="更新设置")
def update_settings(body: SettingsIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    user.settings = copy.deepcopy(body.settings)
    db.commit()
    db.refresh(user)
    return user.settings


@router.post("/theme", summary="保存主题设置")
def save_theme(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    settings = copy.deepcopy(user.settings or {})
    settings["theme"] = body
    user.settings = settings
    db.commit()
    return {"ok": True, "theme": body}


@router.post("/background", summary="上传背景图片")
def upload_background(user: User = Depends(get_current_user)):
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "P2 阶段实现背景图上传")


class FeishuConfigIn(BaseModel):
    app_id: str = ""
    app_secret: str = ""


@router.get("/feishu", summary="获取飞书 OCR 配置")
def get_feishu_config(user: User = Depends(get_current_user)):
    cfg = (user.settings or {}).get("feishu", {})
    return {"app_id": cfg.get("app_id", ""), "app_secret": "••••••••" if cfg.get("app_secret") else ""}


@router.put("/feishu", summary="保存飞书 OCR 配置")
def update_feishu_config(body: FeishuConfigIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    settings = copy.deepcopy(user.settings or {})
    feishu = settings.get("feishu", {})
    feishu["app_id"] = body.app_id
    if body.app_secret and body.app_secret != "••••••••":
        feishu["app_secret"] = body.app_secret
    settings["feishu"] = feishu
    user.settings = settings
    db.commit()
    return {"ok": True, "app_id": feishu.get("app_id", "")}


def _serialize(obj: Any) -> Any:
    """递归序列化 SQLAlchemy 对象为可 JSON 化的字典。"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    if hasattr(obj, "__dict__"):
        return {
            k: _serialize(v)
            for k, v in obj.__dict__.items()
            if not k.startswith("_")
        }
    return obj


@router.get("/export", summary="导出全部数据为 JSON")
def export_data(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """导出当前用户的全部数据（知识库、卡片、学习记录、待办、计划、错题等）。"""
    libraries = db.query(KnowledgeBase).filter(KnowledgeBase.user_id == user.id).all()
    cards = db.query(KnowledgeCard).filter(KnowledgeCard.user_id == user.id).all()
    logs = db.query(StudyLog).filter(StudyLog.user_id == user.id).all()
    subjects = db.query(Subject).filter(Subject.user_id == user.id).all()
    todos = db.query(Todo).filter(Todo.user_id == user.id).all()
    plans = db.query(DailyPlan).filter(DailyPlan.user_id == user.id).all()
    wrongs = db.query(WrongQuestion).filter(WrongQuestion.user_id == user.id).all()

    payload = {
        "exported_at": datetime.utcnow().isoformat(),
        "user": {"username": user.username, "settings": user.settings},
        "knowledge_bases": [_serialize(lib) for lib in libraries],
        "knowledge_cards": [_serialize(c) for c in cards],
        "study_logs": [_serialize(log) for log in logs],
        "subjects": [_serialize(s) for s in subjects],
        "todos": [_serialize(t) for t in todos],
        "daily_plans": [_serialize(p) for p in plans],
        "wrong_questions": [_serialize(w) for w in wrongs],
        "counts": {
            "knowledge_bases": len(libraries),
            "knowledge_cards": len(cards),
            "study_logs": len(logs),
            "todos": len(todos),
            "daily_plans": len(plans),
            "wrong_questions": len(wrongs),
        },
    }
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    filename = f"learning-dashboard-backup-{date.today().isoformat()}.json"
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
