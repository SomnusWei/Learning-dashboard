"""学习计划：每日计划 + 月历视图 + 模板。"""
import random
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.plan import DailyPlan, PlanTemplate
from app.models.user import User
from app.models.wrong_question import WrongQuestion

router = APIRouter(prefix="/plans", tags=["plans"])

# 计划类型说明
# - wrong_question: 复习错题库（从错题表随机抽取未掌握的错题）
# - manual: 手动待办事项
TYPE_LIB_MAP = {
    "wrong_question": None,  # 错题从 wrong_questions 表取
}


class DailyPlanIn(BaseModel):
    plan_date: date
    items: list = Field(default_factory=list)


class PlanItemIn(BaseModel):
    title: str = Field(..., max_length=500)
    description: str | None = None
    subject_id: int | None = None
    url: str | None = None
    done: bool = False
    source: str = "manual"
    type: str = "manual"  # manual | formula | acupoint | herb | wrong_question | morning_reading
    target: int = 1       # 目标数量
    current: int = 0      # 当前进度


class TemplateIn(BaseModel):
    name: str = Field(..., max_length=100)
    description: str | None = None
    items: list = Field(default_factory=list)


class ApplyTemplateIn(BaseModel):
    plan_date: date


@router.get("/daily/{plan_date}", summary="每日计划")
def get_daily(plan_date: date, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    plan = db.query(DailyPlan).filter(DailyPlan.user_id == user.id, DailyPlan.plan_date == plan_date).first()
    if plan:
        # 兼容旧数据：补全 type/target/current 字段
        import re as _re
        normalized = []
        for it in (plan.items or []):
            it = dict(it)
            t = it.get("type") or ""
            if not t or t == "manual":
                title = it.get("title", "")
                if "错题" in title:
                    t = "wrong_question"
                else:
                    t = "manual"
            it["type"] = t
            target = int(it.get("target") or 0)
            if target <= 0:
                m = _re.search(r"(\d+)\s*个", it.get("title", ""))
                target = int(m.group(1)) if m else 1
            it["target"] = target
            it.setdefault("current", 0)
            normalized.append(it)
        plan.items = normalized
        return plan
    return {"id": None, "plan_date": plan_date.isoformat(), "items": [], "created_at": None}


@router.post("/daily", summary="创建/更新每日计划（整体）")
def upsert_daily(body: DailyPlanIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    plan = db.query(DailyPlan).filter(DailyPlan.user_id == user.id, DailyPlan.plan_date == body.plan_date).first()
    if plan:
        plan.items = body.items
    else:
        plan = DailyPlan(user_id=user.id, plan_date=body.plan_date, items=body.items)
        db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.post("/daily/item", summary="添加单项到日计划")
def add_item(body: PlanItemIn, plan_date: date, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    plan = db.query(DailyPlan).filter(DailyPlan.user_id == user.id, DailyPlan.plan_date == plan_date).first()
    if not plan:
        plan = DailyPlan(user_id=user.id, plan_date=plan_date, items=[])
        db.add(plan)
    import uuid
    item = {
        "id": str(uuid.uuid4()),
        "title": body.title,
        "description": body.description or "",
        "subject_id": body.subject_id,
        "url": body.url or "",
        "done": body.done,
        "source": body.source,
        "type": body.type,
        "target": body.target,
        "current": body.current,
    }
    plan.items = (plan.items or []) + [item]
    db.commit()
    db.refresh(plan)
    return plan


class ProgressIn(BaseModel):
    delta: int = 1


@router.post("/daily/item/{item_id}/progress", summary="增加计划项学习进度")
def add_progress(
    item_id: str,
    body: ProgressIn,
    plan_date: date,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """点击学习：current += delta，达到 target 自动标记 done。"""
    plan = db.query(DailyPlan).filter(DailyPlan.user_id == user.id, DailyPlan.plan_date == plan_date).first()
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "当日计划不存在")
    items = list(plan.items or [])
    found = False
    for idx, it in enumerate(items):
        if it.get("id") == item_id:
            # 兼容旧数据：从标题推断 target
            target = int(it.get("target") or 0)
            if target <= 0:
                import re
                m = re.search(r"(\d+)\s*个", it.get("title", ""))
                target = int(m.group(1)) if m else 1
            current = int(it.get("current") or 0)
            new_current = min(current + body.delta, target)
            items[idx] = dict(it)
            items[idx]["current"] = new_current
            items[idx]["target"] = target
            items[idx]["done"] = new_current >= target
            found = True
            break
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "计划项不存在")
    plan.items = items
    db.commit()
    db.refresh(plan)
    return plan


@router.put("/daily/item/{item_id}", summary="更新日计划单项")
def update_item(item_id: str, body: dict, plan_date: date, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    plan = db.query(DailyPlan).filter(DailyPlan.user_id == user.id, DailyPlan.plan_date == plan_date).first()
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "当日计划不存在")
    items = list(plan.items or [])
    found = False
    for idx, it in enumerate(items):
        if it.get("id") == item_id:
            new_it = dict(it)
            new_it.update(body)
            items[idx] = new_it
            found = True
            break
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "计划项不存在")
    plan.items = items
    db.commit()
    db.refresh(plan)
    return plan


@router.delete("/daily/item/{item_id}", summary="删除日计划单项")
def delete_item(item_id: str, plan_date: date, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    plan = db.query(DailyPlan).filter(DailyPlan.user_id == user.id, DailyPlan.plan_date == plan_date).first()
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "当日计划不存在")
    items = [it for it in (plan.items or []) if it.get("id") != item_id]
    plan.items = items
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/monthly/{year}/{month}", summary="月历计划概要")
def get_monthly(year: int, month: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """返回该月每天的计划概要：日期、计划项数、完成数。"""
    if month < 1 or month > 12:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "月份无效")
    # 该月第一天和最后一天
    first_day = date(year, month, 1)
    if month == 12:
        next_first = date(year + 1, 1, 1)
    else:
        next_first = date(year, month + 1, 1)
    last_day = next_first - timedelta(days=1)

    plans = (
        db.query(DailyPlan)
        .filter(
            DailyPlan.user_id == user.id,
            DailyPlan.plan_date >= first_day,
            DailyPlan.plan_date <= last_day,
        )
        .all()
    )
    plan_map = {p.plan_date.isoformat(): p for p in plans}

    days = []
    d = first_day
    while d <= last_day:
        key = d.isoformat()
        p = plan_map.get(key)
        items = p.items if p else []
        total = len(items)
        done = sum(1 for it in items if it.get("done"))
        days.append({
            "date": key,
            "total": total,
            "done": done,
        })
        d += timedelta(days=1)

    return {"year": year, "month": month, "days": days}


@router.get("/templates", summary="模板列表")
def list_templates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(PlanTemplate).filter(PlanTemplate.user_id == user.id).order_by(PlanTemplate.created_at.desc()).all()


@router.post("/template", summary="保存计划模板")
def create_template(body: TemplateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = PlanTemplate(
        user_id=user.id,
        name=body.name,
        description=body.description,
        items=body.items,
    )
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.delete("/template/{template_id}", summary="删除模板")
def delete_template(template_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tpl = db.get(PlanTemplate, template_id)
    if not tpl or tpl.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "模板不存在")
    db.delete(tpl)
    db.commit()
    return {"ok": True}


@router.post("/template/{template_id}/apply", summary="应用模板到指定日期")
def apply_template(
    template_id: int,
    body: ApplyTemplateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tpl = db.get(PlanTemplate, template_id)
    if not tpl or tpl.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "模板不存在")

    plan = db.query(DailyPlan).filter(DailyPlan.user_id == user.id, DailyPlan.plan_date == body.plan_date).first()
    if not plan:
        plan = DailyPlan(user_id=user.id, plan_date=body.plan_date, items=[])
        db.add(plan)

    import uuid
    existing = list(plan.items or [])
    for it in tpl.items:
        # 给模板项生成新 id
        new_item = dict(it)
        new_item["id"] = str(uuid.uuid4())
        new_item.setdefault("done", False)
        new_item.setdefault("source", "template")
        existing.append(new_item)
    plan.items = existing
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/study-card", summary="获取随机学习卡片")
def get_study_card(
    type: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """根据计划类型获取学习卡片。

    type: wrong_question
    """
    if type == "wrong_question":
        # 随机抽取一道未掌握的错题
        wq = (
            db.query(WrongQuestion)
            .filter(WrongQuestion.user_id == user.id, WrongQuestion.is_mastered == False)
            .all()
        )
        if not wq:
            # 没有未掌握错题，尝试任意错题
            wq = db.query(WrongQuestion).filter(WrongQuestion.user_id == user.id).all()
        if not wq:
            return {
                "type": type,
                "name": "暂无错题",
                "fields": {"提示": "错题本为空，请先添加错题"},
                "is_placeholder": True,
            }
        card = random.choice(wq)
        fields = {"题目": card.content}
        if card.options:
            opts = card.options
            if isinstance(opts, dict):
                for k, v in opts.items():
                    fields[f"选项{k}"] = v
            elif isinstance(opts, list):
                for i, v in enumerate(opts, 1):
                    fields[f"选项{i}"] = v
        if card.answer:
            fields["答案"] = card.answer
        if card.analysis:
            fields["解析"] = card.analysis
        return {
            "type": type,
            "id": card.id,
            "name": f"错题 #{card.id}",
            "fields": fields,
            "is_placeholder": False,
        }

    raise HTTPException(status.HTTP_400_BAD_REQUEST, "不支持的学习类型")
