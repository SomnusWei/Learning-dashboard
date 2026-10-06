"""仪表盘：统计卡片、热力图、图表。"""
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
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

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _today_range():
    today = date.today()
    start = datetime.combine(today, time.min)
    return today, start


@router.get("/stats", summary="仪表盘统计卡片")
def stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    today, today_start = _today_range()

    # 今日学习记录
    log = (
        db.query(StudyLog)
        .filter(StudyLog.user_id == user.id, StudyLog.log_date == today)
        .first()
    )

    # 今日已复习卡片数（来自 study_logs）
    today_review = log.review_cards if log and log.review_cards else 0

    # 今日错题：今日新增
    today_wrong = (
        db.query(func.count(WrongQuestion.id))
        .filter(
            WrongQuestion.user_id == user.id,
            WrongQuestion.created_at >= today_start,
        )
        .scalar()
        or 0
    )

    # 今日待办：未完成
    today_todo = (
        db.query(func.count(Todo.id))
        .filter(
            Todo.user_id == user.id,
            Todo.status != "done",
        )
        .scalar()
        or 0
    )

    # 学习时长（秒）
    study_duration = log.study_duration if log and log.study_duration else 0

    # 连续打卡天数：从今天往前，有学习记录（study_duration > 0 或 new_cards > 0 或 review_cards > 0）
    # 即 StudyLog 存在且至少一项 > 0 的连续天数
    streak = 0
    check_day = today
    while True:
        row = (
            db.query(StudyLog)
            .filter(StudyLog.user_id == user.id, StudyLog.log_date == check_day)
            .first()
        )
        if row and (row.study_duration > 0 or row.new_cards > 0 or row.review_cards > 0):
            streak += 1
            check_day -= timedelta(days=1)
        else:
            break

    # 本周计划完成率：本周 7 天 daily_plans 的 items 已完成数 / 总数
    week_start = today - timedelta(days=today.weekday())  # 周一
    week_end = week_start + timedelta(days=6)
    plans = (
        db.query(DailyPlan)
        .filter(
            DailyPlan.user_id == user.id,
            DailyPlan.plan_date >= week_start,
            DailyPlan.plan_date <= week_end,
        )
        .all()
    )
    total_items = 0
    done_items = 0
    for p in plans:
        for it in p.items or []:
            total_items += 1
            if it.get("status") == "done":
                done_items += 1
    weekly_completion_rate = (done_items / total_items) if total_items > 0 else 0.0

    return {
        "today_review": today_review,
        "today_wrong": today_wrong,
        "today_todo": today_todo,
        "study_duration": study_duration,
        "streak_days": streak,
        "weekly_completion_rate": weekly_completion_rate,
    }


@router.get("/heatmap", summary="近 1 年热力图（补齐无数据天为 0）")
def heatmap(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    end = date.today()
    start = end - timedelta(days=364)  # 近 365 天
    rows = (
        db.query(StudyLog)
        .filter(
            StudyLog.user_id == user.id,
            StudyLog.log_date >= start,
            StudyLog.log_date <= end,
        )
        .all()
    )
    by_date = {r.log_date: r for r in rows}

    data = []
    cur = start
    while cur <= end:
        r = by_date.get(cur)
        data.append(
            {
                "date": cur.isoformat(),
                "duration": r.study_duration if r else 0,
                "new_cards": r.new_cards if r else 0,
                "review_cards": r.review_cards if r else 0,
                "new_wrong": r.new_wrong_questions if r else 0,
            }
        )
        cur += timedelta(days=1)

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "data": data,
    }


@router.get("/charts", summary="图表数据")
def charts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    today, _ = _today_range()
    week_start = today - timedelta(days=today.weekday())

    # 本周学习时长趋势（按天）
    durations = []
    cur = week_start
    for i in range(7):
        r = (
            db.query(StudyLog)
            .filter(StudyLog.user_id == user.id, StudyLog.log_date == cur)
            .first()
        )
        durations.append({"date": cur.isoformat(), "duration": r.study_duration if r else 0})
        cur += timedelta(days=1)

    # 各科目错题占比（饼图）
    subj_rows = (
        db.query(WrongQuestion.subject_id, func.count(WrongQuestion.id))
        .filter(WrongQuestion.user_id == user.id)
        .group_by(WrongQuestion.subject_id)
        .all()
    )
    subject_map = {s.id: s.name for s in db.query(Subject).filter(Subject.user_id == user.id).all()}
    subject_wrong_distribution = []
    for subj_id, count in subj_rows:
        name = subject_map.get(subj_id, "未分类") if subj_id else "未分类"
        subject_wrong_distribution.append({"name": name, "value": count})

    # 复习完成率趋势（近 7 天复习卡片数）
    review_trend = []
    cur = today - timedelta(days=6)
    for i in range(7):
        r = (
            db.query(StudyLog)
            .filter(StudyLog.user_id == user.id, StudyLog.log_date == cur)
            .first()
        )
        review_trend.append(
            {
                "date": cur.isoformat(),
                "review_cards": r.review_cards if r else 0,
                "new_cards": r.new_cards if r else 0,
            }
        )
        cur += timedelta(days=1)

    # 知识库掌握度雷达（每个知识库已学卡片占比）
    libs = db.query(KnowledgeBase).filter(KnowledgeBase.user_id == user.id).all()
    radar = {}
    for lib in libs:
        total = (
            db.query(func.count(KnowledgeCard.id))
            .filter(KnowledgeCard.base_id == lib.id, KnowledgeCard.user_id == user.id)
            .scalar()
            or 0
        )
        learned = (
            db.query(func.count(KnowledgeCard.id))
            .filter(
                KnowledgeCard.base_id == lib.id,
                KnowledgeCard.user_id == user.id,
                KnowledgeCard.is_learned == True,  # noqa: E712
            )
            .scalar()
            or 0
        )
        mastery = (learned / total) if total > 0 else 0.0
        radar[lib.name] = round(mastery, 3)

    return {
        "weekly_duration_trend": durations,
        "subject_wrong_distribution": subject_wrong_distribution,
        "review_completion_trend": review_trend,
        "knowledge_mastery_radar": radar,
    }
