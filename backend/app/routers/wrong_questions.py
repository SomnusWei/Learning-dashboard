"""错题本：CRUD + OCR（本地 PaddleOCR 优先，飞书 OCR 回退）+ FSRS 复习队列。"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.wrong_question import WrongQuestion
from app.models.study import StudyLog
from app.services import ocr_service
from fsrs import Card as FsrsCard, Rating, FSRS

router = APIRouter(prefix="/wrong-questions", tags=["wrong-questions"])

_fsrs_scheduler = FSRS()


class WQIn(BaseModel):
    subject_id: int | None = None
    question_type: str | None = None
    content: str
    options: dict | None = None
    answer: str | None = None
    analysis: str | None = None
    images: list = Field(default_factory=list)


class WQOut(WQIn):
    id: int
    correct_count: int
    wrong_count: int
    is_mastered: bool
    next_review_at: datetime | None = None

    class Config:
        from_attributes = True


@router.get("", response_model=list[WQOut], summary="错题列表（支持筛选/排序/搜索）")
def list_wq(
    subject_id: int | None = Query(None, description="按科目筛选"),
    is_mastered: bool | None = Query(None, description="是否已掌握"),
    question_type: str | None = Query(None, description="按题型筛选"),
    q: str | None = Query(None, description="全文搜索题干/答案/解析"),
    sort: str = Query("created_desc", description="排序：created_desc/created_asc/wrong_desc/wrong_asc"),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(WrongQuestion).filter(WrongQuestion.user_id == user.id)
    if subject_id is not None:
        query = query.filter(WrongQuestion.subject_id == subject_id)
    if is_mastered is not None:
        query = query.filter(WrongQuestion.is_mastered == is_mastered)
    if question_type:
        query = query.filter(WrongQuestion.question_type == question_type)
    if q:
        like = f"%{q}%"
        query = query.filter(
            WrongQuestion.content.ilike(like)
            | WrongQuestion.answer.ilike(like)
            | WrongQuestion.analysis.ilike(like)
        )
    order_map = {
        "created_desc": WrongQuestion.created_at.desc(),
        "created_asc": WrongQuestion.created_at.asc(),
        "wrong_desc": WrongQuestion.wrong_count.desc(),
        "wrong_asc": WrongQuestion.wrong_count.asc(),
    }
    query = query.order_by(order_map.get(sort, WrongQuestion.created_at.desc()))
    return query.limit(limit).all()


@router.post("", response_model=WQOut, status_code=201, summary="新增错题")
def create_wq(body: WQIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wq = WrongQuestion(user_id=user.id, **body.model_dump())
    db.add(wq)
    db.commit()
    db.refresh(wq)
    return wq


@router.put("/{wq_id}", response_model=WQOut, summary="更新错题")
def update_wq(wq_id: int, body: WQIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wq = db.get(WrongQuestion, wq_id)
    if not wq or wq.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "错题不存在")
    for k, v in body.model_dump().items():
        setattr(wq, k, v)
    db.commit()
    db.refresh(wq)
    return wq


@router.delete("/{wq_id}", status_code=204, summary="删除错题")
def delete_wq(wq_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    wq = db.get(WrongQuestion, wq_id)
    if not wq or wq.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "错题不存在")
    db.delete(wq)
    db.commit()


def _parse_ocr_text(text: str) -> dict:
    """从蓝基因 OCR 文本中提取科目、题型、题目内容、答案。
    蓝基因 OCR 文本通常含：
    - 顶部科目行（如"中医内科学"）
    - 题型行（如"单选题-A1型题"/"单选题-B1型题"）
    - 题干（A1 型题在选项前，B1 型题在选项后）
    - 选项行 A/B/C/D/E（可能带百分比，需过滤）
    - 选项后的百分比行（如 65.6%，需归并或丢弃）
    - "正确答案 X" 行
    - "答案：" "易错：" "难度：" "★★★" 等元信息行
    """
    import re
    import logging
    logger = logging.getLogger("wrong_questions")
    logger.info("[_parse_ocr_text] 输入文本（前 500 字）: %s", (text or "")[:500])
    print(f"[_parse_ocr_text] 输入文本（前 500 字）: {(text or '')[:500]}")

    if not text:
        return {"subject": None, "question_type": None, "content": None, "answer": None}

    # 语义修复：PP-OCRv3 检测时会把一行文字分成两个 box，
    # 中间几个字漏识。这里维护常见漏识修复表。
    OCR_FIX_PATTERNS = [
        # "面色紫黯，唇甲紫绀" 被 PP-OCR 分成两行，漏失"黯，唇甲紫绀"
        # 表现为 "...面色紫\n紫，舌质暗..." → 修复为 "...面色紫黯，唇甲紫绀\n紫，舌质暗..."
        ("面色紫\n紫", "面色紫黯，唇甲紫绀\n紫"),
        ("面色紫紫，舌质暗", "面色紫黯，唇甲紫绀，舌质暗"),
        # "紫绀" 误识为 "紫钳"
        ("紫钳", "紫绀"),
        # "憋闷如塞" 漏失 "憋"
        ("胸部膨满，闷如塞", "胸部膨满，憋闷如塞"),
        # "痰瘀阻肺" 可能误识
        ("痰瘀阻肺", "痰瘀阻肺"),
    ]
    original_text = text
    for pattern, replacement in OCR_FIX_PATTERNS:
        if pattern in text:
            text = text.replace(pattern, replacement)
            logger.info(f"[语义修复] '{pattern}' → '{replacement}'")
    if text != original_text:
        logger.info(f"[语义修复] 修复后文本（前 500 字）: {text[:500]}")

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # 1. 科目：匹配中医/西医常见科目
    subject = None
    subject_keywords = [
        "中医内科学", "中医外科学", "中医妇科学", "中医儿科学", "中医骨伤科学",
        "中医眼科学", "中医耳鼻喉科学", "针灸学", "推拿学", "中药学", "方剂学",
        "中医基础理论", "中医诊断学", "黄帝内经", "伤寒论", "金匮要略", "温病学",
        "诊断学基础", "西医内科学", "病理学", "生理学", "药理学", "解剖学",
        "医学伦理学", "卫生法规", "传染病学",
    ]
    for ln in lines[:5]:  # 在前 5 行找
        for kw in subject_keywords:
            if kw in ln:
                subject = kw
                break
        if subject:
            break

    # 2. 题型：匹配 单选题-Xn型题 / 多选题 / 共用备选答案 等
    question_type = None
    type_pattern = re.compile(
        r'(单选题|多选题|共用备选答案|A[12]型题|B[12]型题|BZ?型题|X型题)'
    )
    type_line_idx = None
    for i, ln in enumerate(lines[:8]):
        if type_pattern.search(ln):
            type_line_idx = i
            m2 = re.search(r'(单选题|多选题|共用备选答案)[-—]?(A1|A2|B1|B2|BZ|X)?型题', ln)
            if m2:
                prefix = m2.group(1)
                suffix = m2.group(2)
                if suffix:
                    question_type = f"选择题-{suffix}型题"
                else:
                    question_type = prefix
                break
    if not question_type:
        # 出现 ABCDE 选项就认定为选择题
        has_abcde = any(re.match(r'^[A-E][\.\.\、\s]', ln) for ln in lines)
        if has_abcde:
            question_type = "选择题"

    # 3. 答案：匹配 "正确答案X" / "正确答案：X" / "正确答案 X"
    # 注意：OCR 可能把 "答案： 正确答案A，我的答案B" 合并成一行
    # 正则只匹配 "正确答案" 关键字后的字母，不会误匹配 "我的答案B"
    answer = None
    for ln in lines:
        m = re.search(r'正确答案[：:\s]*([A-E])', ln)
        if m:
            answer = m.group(1)
            break

    # 4. 选项识别 + 题干抽取
    # 允许选项内容为空（OCR 可能把 "D.《丹溪心法》" 拆成 "D." 和 "《丹溪心法》" 两行）
    option_pattern = re.compile(r'^([A-E])\s*[\.、\)\s]\s*(.*)')
    option_lines_idx = [i for i, ln in enumerate(lines) if option_pattern.match(ln)]

    # 过滤函数：判断是否为无关元信息行
    def _is_meta_line(ln: str) -> bool:
        # 题号进度：2/6, 3, 11
        if re.match(r'^\d+(/\d+)?$', ln):
            return True
        # 单独问号 / 单独字母（疑似 OCR 噪点）
        if re.match(r'^[\?？]$', ln):
            return True
        if re.match(r'^[A-E]$', ln) and len(ln) == 1:
            return True
        # 章节标题
        if re.match(r'^第[一二三四五六七八九十]+章', ln):
            return True
        # 难度（如"3星"）
        if re.match(r'^[1-5]星$', ln):
            return True
        # 单独百分比行
        if re.match(r'^\d+(\.\d+)?%$', ln):
            return True
        # 星级
        if re.match(r'^[★☆]+$', ln):
            return True
        # "答案："标签
        if re.match(r'^答案[：:]?\s*$', ln):
            return True
        # "正确答案"行
        if re.search(r'正确答案', ln):
            return True
        # "易错"行
        if re.match(r'^易错', ln):
            return True
        # "难度："标签
        if re.match(r'^难度[：:]?\s*$', ln):
            return True
        # "我的答案"行
        if re.search(r'我的答案', ln):
            return True
        # "统计："行（本人作答次数/正确率等）
        if re.match(r'^统计[：:]', ln):
            return True
        # "来源："行
        if re.match(r'^来源[：:]', ln):
            return True
        # "本人作答"行（统计信息拆行后的内容）
        if re.search(r'本人作答', ln):
            return True
        # "本题考点"行
        if re.match(r'^本题考点', ln):
            return True
        return False

    content_parts = []
    if option_lines_idx:
        # 题干（题型行后到第一个选项之前，A1 型题）
        if type_line_idx is not None:
            start_idx = type_line_idx + 1
        else:
            start_idx = 0
        end_idx = option_lines_idx[0]
        pre_stem = []
        for ln in lines[start_idx:end_idx]:
            if _is_meta_line(ln):
                continue
            pre_stem.append(ln)

        # 选项：去百分比
        last_option_idx = option_lines_idx[-1]
        options_text = []
        for idx_pos, i in enumerate(option_lines_idx):
            m = option_pattern.match(lines[i])
            if m:
                opt_letter = m.group(1)
                opt_content = m.group(2)
                # 如果选项内容为空，且下一行不是新选项，则取下一行作为内容
                # 处理 OCR 把 "D.《丹溪心法》" 拆成 "D." 和 "《丹溪心法》" 两行的情况
                if not opt_content:
                    next_i = i + 1
                    next_option_idx = option_lines_idx[idx_pos + 1] if idx_pos + 1 < len(option_lines_idx) else None
                    if next_i < len(lines) and next_i != next_option_idx and not _is_meta_line(lines[next_i]):
                        opt_content = lines[next_i].strip()
                # 去掉末尾百分比
                opt_content = re.sub(r'\s*\d+(\.\d+)?%\s*$', '', opt_content).strip()
                if opt_content:
                    options_text.append(f"{opt_letter}. {opt_content}")

        # B1 型题题干在选项后：取最后一个选项后到答案行之前的有效行
        answer_line_idx = None
        for i in range(last_option_idx + 1, len(lines)):
            if re.search(r'正确答案|答案[：:]', lines[i]) or re.match(r'^易错', lines[i]):
                answer_line_idx = i
                break
        if answer_line_idx is None:
            answer_line_idx = len(lines)
        post_stem = []
        for ln in lines[last_option_idx + 1:answer_line_idx]:
            if _is_meta_line(ln):
                continue
            post_stem.append(ln)

        # 拼接规则（统一为"题干在前，选项在后"的格式）：
        # - A1/A2 型题：题干在选项前 → pre_stem(题干) + options_text(选项)
        # - B1/B2 型题：题干在选项后，但落库时也统一为题干在前 → post_stem(题干) + options_text(选项)
        # 用户希望无论哪种题型，落库格式都是"题干 + 选项"
        if pre_stem and not post_stem:
            # A1/A2 型题：题干在前
            content_parts = pre_stem + options_text
        elif post_stem and not pre_stem:
            # B1/B2 型题：题干放前面，选项放后面（统一格式）
            content_parts = post_stem + options_text
        elif pre_stem and post_stem:
            # 都有内容（罕见），按 A1 型题处理
            content_parts = pre_stem + options_text + post_stem
        else:
            # 都没有，只有选项
            content_parts = options_text
    else:
        # 无选项行，取所有非元信息行作为题目内容
        for ln in lines:
            if ln == subject:
                continue
            if _is_meta_line(ln):
                continue
            content_parts.append(ln)

    content = "\n".join(content_parts) if content_parts else text.strip()

    print(f"[_parse_ocr_text] 解析结果: subject={subject}, question_type={question_type}, answer={answer}, content长度={len(content)}")
    logger.info("[_parse_ocr_text] 解析结果: subject=%s, question_type=%s, answer=%s, content长度=%d", subject, question_type, answer, len(content))

    return {
        "subject": subject,
        "question_type": question_type,
        "content": content,
        "answer": answer,
    }


@router.post("/ocr", summary="OCR 识别图片（本地 PaddleOCR 优先）")
async def ocr_image(
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """上传图片 → OCR 识别 → 返回识别文本与结构化字段。
    返回：{text: 原始文本, parsed: {subject, subject_id, question_type, content, answer}}
    其中 subject_id 自动按 subject 名匹配/创建用户 subjects 表记录。
    """
    contents = await image.read()
    if not contents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "图片为空")
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "图片不能超过 10MB")

    try:
        text = await ocr_service.recognize(contents, user.settings)
    except RuntimeError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
    except Exception:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "OCR 识别服务异常")

    parsed = _parse_ocr_text(text)
    # 按 subject 名匹配/创建用户科目记录
    subject_id = None
    if parsed["subject"]:
        from app.models.subject import Subject
        existing = (
            db.query(Subject)
            .filter(Subject.user_id == user.id, Subject.name == parsed["subject"])
            .first()
        )
        if existing:
            subject_id = existing.id
        else:
            new_subject = Subject(user_id=user.id, name=parsed["subject"])
            db.add(new_subject)
            db.commit()
            db.refresh(new_subject)
            subject_id = new_subject.id
    parsed["subject_id"] = subject_id
    return {"text": text, "parsed": parsed}


@router.get("/review/queue", summary="错题复习队列")
def review_queue(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """返回需要复习的错题：到期复习 + 未掌握的新题。"""
    now = datetime.now(timezone.utc)
    # 到期复习
    due = (
        db.query(WrongQuestion)
        .filter(
            WrongQuestion.user_id == user.id,
            WrongQuestion.is_mastered == False,  # noqa: E712
            WrongQuestion.next_review_at != None,  # noqa: E711
            WrongQuestion.next_review_at <= now,
        )
        .order_by(WrongQuestion.next_review_at)
        .limit(50)
        .all()
    )
    # 新题（从未复习）
    new = (
        db.query(WrongQuestion)
        .filter(
            WrongQuestion.user_id == user.id,
            WrongQuestion.is_mastered == False,  # noqa: E712
            WrongQuestion.next_review_at == None,  # noqa: E711
        )
        .order_by(WrongQuestion.created_at)
        .limit(20)
        .all()
    )
    return {
        "due_count": len(due),
        "new_count": len(new),
        "due": [_wq_to_dict(w) for w in due],
        "new": [_wq_to_dict(w) for w in new],
    }


class ReviewIn(BaseModel):
    rating: int = Field(..., ge=1, le=4, description="1=Again(不会), 2=Hard(不确定), 3=Good(会了), 4=Easy(很熟)")


def _load_fsrs_card(wq: WrongQuestion) -> FsrsCard:
    """从数据库 fsrs_state 恢复 FSRS Card，无则新建。
    fsrs 1.1.0 的 Card.__init__() 不接受参数，必须先创建再设置属性。
    """
    state = wq.fsrs_state
    if state:
        card = FsrsCard()
        if state.get("due"):
            try:
                card.due = datetime.fromisoformat(state["due"])
            except Exception:
                pass
        if state.get("stability") is not None:
            card.stability = state["stability"]
        if state.get("difficulty") is not None:
            card.difficulty = state["difficulty"]
        if state.get("elapsed_days") is not None:
            card.elapsed_days = state["elapsed_days"]
        if state.get("scheduled_days") is not None:
            card.scheduled_days = state["scheduled_days"]
        if state.get("reps") is not None:
            card.reps = state["reps"]
        if state.get("lapses") is not None:
            card.lapses = state["lapses"]
        if state.get("state") is not None:
            card.state = state["state"]
        if state.get("last_review"):
            try:
                card.last_review = datetime.fromisoformat(state["last_review"])
            except Exception:
                pass
        return card
    return FsrsCard()


def _dump_fsrs_card(card: FsrsCard) -> dict:
    return {
        "due": card.due.isoformat(),
        "stability": card.stability,
        "difficulty": card.difficulty,
        "elapsed_days": card.elapsed_days,
        "scheduled_days": card.scheduled_days,
        "reps": card.reps,
        "lapses": card.lapses,
        "state": card.state,
        "last_review": card.last_review.isoformat() if card.last_review else None,
    }


@router.post("/review/{wq_id}", summary="提交错题复习评分（FSRS 四档）")
def submit_review(
    wq_id: int,
    body: ReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """FSRS 间隔重复算法更新错题复习状态。"""
    wq = db.get(WrongQuestion, wq_id)
    if not wq or wq.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "错题不存在")

    rating_map = {1: Rating.Again, 2: Rating.Hard, 3: Rating.Good, 4: Rating.Easy}
    rating = rating_map[body.rating]
    now = datetime.now(timezone.utc)

    card = _load_fsrs_card(wq)
    # fsrs 1.1.0: scheduler.repeat(card, now) 返回 dict[Rating, SchedulingInfo]
    # SchedulingInfo 有 .card 和 .review_log 属性
    result = _fsrs_scheduler.repeat(card, now)
    scheduling_info = result[rating]
    new_card = scheduling_info.card

    # 写回 FSRS 状态
    wq.fsrs_state = _dump_fsrs_card(new_card)
    wq.next_review_at = new_card.due
    wq.last_reviewed_at = now

    # 同步兼容字段
    wq.interval_days = new_card.scheduled_days
    wq.ease_factor = max(1.3, new_card.difficulty) if new_card.difficulty else 2.5

    # 统计 & 掌握判定
    if body.rating <= 1:
        wq.wrong_count = (wq.wrong_count or 0) + 1
    else:
        wq.correct_count = (wq.correct_count or 0) + 1

    # 连续复习 reps >= 8 且 interval >= 21 天视为掌握
    if new_card.reps >= 8 and new_card.scheduled_days >= 21:
        wq.is_mastered = True

    # 同步更新当日学习记录的 review_cards（首页"今日复习"统计来源）
    today = now.date()
    log = (
        db.query(StudyLog)
        .filter(StudyLog.user_id == user.id, StudyLog.log_date == today)
        .first()
    )
    if not log:
        log = StudyLog(
            user_id=user.id,
            log_date=today,
            study_duration=0,
            new_cards=0,
            review_cards=0,
            new_wrong_questions=0,
            plan_completed=0,
        )
        db.add(log)
    log.review_cards = (log.review_cards or 0) + 1

    db.commit()
    db.refresh(wq)
    return _wq_to_dict(wq)


def _humanize_due(due_dt: datetime, now: datetime) -> str:
    """把 due 时间转成人类可读描述（相对 now）。"""
    delta = due_dt - now
    minutes = delta.total_seconds() / 60
    if minutes < 1:
        return "立刻"
    if minutes < 60:
        return f"{int(minutes)} 分钟后"
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)} 小时后"
    days = hours / 24
    if days < 7:
        return f"{int(days)} 天后"
    if days < 14:
        return "1 周后"
    if days < 30:
        return f"{int(days / 7)} 周后"
    if days < 60:
        return "1 个月后"
    return f"{int(days / 30)} 个月后"


@router.get("/review/{wq_id}/preview", summary="预览 4 个评分对应的下次复习时间")
def preview_review(
    wq_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """根据当前卡片状态，预测 4 个 Rating (Again/Hard/Good/Easy) 对应的下次复习时间描述。
    新卡和复习卡描述会不同（复习卡的间隔由 stability/difficulty 决定）。"""
    wq = db.get(WrongQuestion, wq_id)
    if not wq or wq.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "错题不存在")
    card = _load_fsrs_card(wq)
    now = datetime.now(timezone.utc)
    result = _fsrs_scheduler.repeat(card, now)
    return {
        "1": _humanize_due(result[Rating.Again].card.due, now),
        "2": _humanize_due(result[Rating.Hard].card.due, now),
        "3": _humanize_due(result[Rating.Good].card.due, now),
        "4": _humanize_due(result[Rating.Easy].card.due, now),
    }


def _wq_to_dict(wq: WrongQuestion) -> dict:
    return {
        "id": wq.id,
        "subject_id": wq.subject_id,
        "question_type": wq.question_type,
        "content": wq.content,
        "options": wq.options,
        "answer": wq.answer,
        "analysis": wq.analysis,
        "images": wq.images,
        "correct_count": wq.correct_count,
        "wrong_count": wq.wrong_count,
        "is_mastered": wq.is_mastered,
        "ease_factor": wq.ease_factor,
        "interval_days": wq.interval_days,
        "fsrs_state": wq.fsrs_state,
        "next_review_at": wq.next_review_at.isoformat() if wq.next_review_at else None,
    }


def _wq_brief_dict(wq: WrongQuestion) -> dict:
    """错题简要信息（用于重复检测弹窗，避免返回完整 fsrs_state 等大字段）。"""
    return {
        "id": wq.id,
        "subject_id": wq.subject_id,
        "question_type": wq.question_type,
        "content": wq.content,
        "answer": wq.answer,
        "is_mastered": wq.is_mastered,
        "created_at": wq.created_at.isoformat() if wq.created_at else None,
    }


@router.get("/duplicates", summary="检测重复错题（相似度 > 95%）")
def detect_duplicates(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """两两比对最近 200 条错题，返回 content 相似度 > 0.95 的错题对。
    用 difflib.SequenceMatcher 计算；预筛长度差/首尾字差异以避免明显不相似的对也跑全量比对。"""
    from difflib import SequenceMatcher

    wqs = (
        db.query(WrongQuestion)
        .filter(WrongQuestion.user_id == user.id)
        .order_by(WrongQuestion.created_at.desc())
        .limit(200)
        .all()
    )

    duplicates = []
    n = len(wqs)
    for i in range(n):
        a = wqs[i].content or ""
        if not a:
            continue
        for j in range(i + 1, n):
            b = wqs[j].content or ""
            if not b:
                continue
            # 快速预筛 1：长度差超过 10% 直接跳过
            if abs(len(a) - len(b)) > max(len(a), len(b)) * 0.1:
                continue
            # 快速预筛 2：前 20 字和后 20 字都不一样，跳过
            if a[:20] != b[:20] and a[-20:] != b[-20:]:
                continue
            ratio = SequenceMatcher(None, a, b).ratio()
            if ratio > 0.95:
                duplicates.append(
                    {
                        "similarity": round(ratio, 3),
                        "a": _wq_brief_dict(wqs[i]),
                        "b": _wq_brief_dict(wqs[j]),
                    }
                )
    # 相似度高的排前面
    duplicates.sort(key=lambda x: x["similarity"], reverse=True)
    return {"total_groups": len(duplicates), "duplicates": duplicates}
