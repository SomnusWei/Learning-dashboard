"""学习中心：今日队列、复习评分(SM-2)、统计。"""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.knowledge import KnowledgeCard
from app.models.study import StudyLog
from app.models.user import User

router = APIRouter(prefix="/study", tags=["study"])


def apply_sm2(card: KnowledgeCard, rating: int) -> None:
    """SM-2 间隔重复算法。

    rating: 0=完全不记得 / 1=吃力 / 2=正常 / 3=轻松。
    标准 SM-2 中 q ∈ [0,5]，此处将 rating+2 映射为 q ∈ [2,5]。
    """
    if rating not in (0, 1, 2, 3):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "rating 取值 0-3")

    q = rating + 2  # 映射到 SM-2 的 q

    if q < 3:
        # 未记住：重置间隔，重新学习
        card.repetitions = 0
        card.interval_days = 1
    else:
        if card.repetitions == 0:
            card.interval_days = 1
        elif card.repetitions == 1:
            card.interval_days = 6
        else:
            card.interval_days = max(1, round(card.interval_days * card.ease_factor))
        card.repetitions += 1

    # 更新 ease_factor
    ef = card.ease_factor + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    card.ease_factor = max(1.3, round(ef, 3))

    now = datetime.now(timezone.utc)
    card.last_reviewed_at = now
    card.due_date = now + timedelta(days=card.interval_days)
    if card.interval_days >= 1:
        card.is_learned = True


def _touch_study_log(db: Session, user_id: int, *, is_new: bool) -> None:
    """更新当日学习记录。"""
    today = datetime.now(timezone.utc).date()
    log = (
        db.query(StudyLog)
        .filter(StudyLog.user_id == user_id, StudyLog.log_date == today)
        .first()
    )
    if not log:
        log = StudyLog(
            user_id=user_id,
            log_date=today,
            study_duration=0,
            new_cards=0,
            review_cards=0,
            new_wrong_questions=0,
            plan_completed=0,
        )
        db.add(log)
    log.review_cards = (log.review_cards or 0) + 1
    if is_new:
        log.new_cards = (log.new_cards or 0) + 1


@router.get("/queue", summary="今日学习队列")
def queue(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    today = now.date()

    # 读取学习设置
    study_settings = (user.settings or {}).get("study", {})
    new_per_day = int(study_settings.get("new_per_day", 20))
    review_per_day = int(study_settings.get("review_per_day", 100))

    # 今日已学习记录
    log = (
        db.query(StudyLog)
        .filter(StudyLog.user_id == user.id, StudyLog.log_date == today)
        .first()
    )
    today_new_done = log.new_cards if log and log.new_cards else 0
    today_review_done = log.review_cards if log and log.review_cards else 0

    # 剩余额度
    new_quota = max(0, new_per_day - today_new_done)
    review_quota = max(0, review_per_day - today_review_done)

    due = (
        db.query(KnowledgeCard)
        .filter(
            KnowledgeCard.user_id == user.id,
            KnowledgeCard.is_learned == True,  # noqa: E712
            KnowledgeCard.due_date <= now,
        )
        .order_by(KnowledgeCard.due_date)
        .limit(review_quota)
        .all()
    )
    new = (
        db.query(KnowledgeCard)
        .filter(KnowledgeCard.user_id == user.id, KnowledgeCard.is_learned == False)  # noqa: E712
        .order_by(KnowledgeCard.created_at)
        .limit(new_quota)
        .all()
    )
    return {
        "due_count": len(due),
        "new_count": len(new),
        "due": [
            {"id": c.id, "name": c.name, "fields": c.fields, "images": c.images,
             "ease_factor": c.ease_factor, "interval_days": c.interval_days}
            for c in due
        ],
        "new": [
            {"id": c.id, "name": c.name, "fields": c.fields, "images": c.images}
            for c in new
        ],
    }


class ReviewIn(BaseModel):
    rating: int = Field(..., ge=0, le=3)


@router.post("/review/{card_id}", summary="提交复习评分")
def review(card_id: int, body: ReviewIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    card = db.get(KnowledgeCard, card_id)
    if not card or card.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "卡片不存在")
    is_new = not card.is_learned
    apply_sm2(card, body.rating)
    _touch_study_log(db, user.id, is_new=is_new)
    db.commit()
    db.refresh(card)
    return {
        "id": card.id,
        "ease_factor": card.ease_factor,
        "interval_days": card.interval_days,
        "repetitions": card.repetitions,
        "due_date": card.due_date.isoformat() if card.due_date else None,
        "is_new": is_new,
    }


@router.get("/stats", summary="学习统计")
def stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.models.knowledge import KnowledgeBase

    total = db.query(KnowledgeCard).filter(KnowledgeCard.user_id == user.id).count()
    learned = db.query(KnowledgeCard).filter(
        KnowledgeCard.user_id == user.id,
        KnowledgeCard.is_learned == True,  # noqa: E712
    ).count()

    # 今日学习记录
    today = datetime.now(timezone.utc).date()
    log = (
        db.query(StudyLog)
        .filter(StudyLog.user_id == user.id, StudyLog.log_date == today)
        .first()
    )
    today_new = log.new_cards if log and log.new_cards else 0
    today_review = log.review_cards if log and log.review_cards else 0
    study_duration = log.study_duration if log and log.study_duration else 0

    # 各知识库掌握度
    libs = db.query(KnowledgeBase).filter(KnowledgeBase.user_id == user.id).all()
    lib_stats = []
    for lib in libs:
        lib_total = db.query(KnowledgeCard).filter(
            KnowledgeCard.user_id == user.id,
            KnowledgeCard.base_id == lib.id,
        ).count()
        lib_learned = db.query(KnowledgeCard).filter(
            KnowledgeCard.user_id == user.id,
            KnowledgeCard.base_id == lib.id,
            KnowledgeCard.is_learned == True,  # noqa: E712
        ).count()
        lib_stats.append({
            "lib_id": lib.id,
            "lib_name": lib.name,
            "total": lib_total,
            "learned": lib_learned,
            "mastery_rate": round(lib_learned / lib_total, 4) if lib_total > 0 else 0,
        })

    return {
        "total": total,
        "learned": learned,
        "unlearned": total - learned,
        "mastery_rate": round(learned / total, 4) if total > 0 else 0,
        "today_new": today_new,
        "today_review": today_review,
        "study_duration": study_duration,
        "by_library": lib_stats,
    }


class DurationIn(BaseModel):
    seconds: int = Field(..., ge=1, le=86400)


@router.patch("/log/duration", summary="上报学习时长（秒）")
def report_duration(body: DurationIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """前端定时上报学习时长，累加到今日 study_duration。"""
    today = datetime.now(timezone.utc).date()
    log = (
        db.query(StudyLog)
        .filter(StudyLog.user_id == user.id, StudyLog.log_date == today)
        .first()
    )
    if not log:
        log = StudyLog(
            user_id=user.id, log_date=today,
            study_duration=0, new_cards=0, review_cards=0,
            new_wrong_questions=0, plan_completed=0,
        )
        db.add(log)
    log.study_duration = (log.study_duration or 0) + body.seconds
    db.commit()
    return {"study_duration": log.study_duration}
