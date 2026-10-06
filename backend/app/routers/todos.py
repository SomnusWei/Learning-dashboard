"""待办事项：CRUD + 浏览器扩展剪藏入口 + 待办转学习计划。"""
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import decode_token
from app.models.formula_song import FormulaSong
from app.models.plan import DailyPlan
from app.models.todo import Todo
from app.models.user import User

router = APIRouter(prefix="/todos", tags=["todos"])


class TodoIn(BaseModel):
    title: str = Field(..., max_length=500)
    description: str | None = None
    url: str | None = None
    source: str = "manual"
    priority: int = 2
    status: str = "pending"
    due_date: datetime | None = None
    completed_at: datetime | None = None
    tags: list = Field(default_factory=list)


class TodoOut(TodoIn):
    id: int
    status: str
    ref_type: str | None = None
    ref_id: int | None = None

    class Config:
        from_attributes = True


def _sync_formula_song_state(db: Session, todo: Todo) -> None:
    """待办状态变化时同步关联方歌的 is_mastered：done→False，pending→True。"""
    if todo.ref_type != "formula_song" or not todo.ref_id:
        return
    song = db.get(FormulaSong, todo.ref_id)
    if not song or song.user_id != todo.user_id:
        return
    song.is_mastered = todo.status == "pending"


@router.get("", response_model=list[TodoOut], summary="待办列表")
def list_todos(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Todo).filter(Todo.user_id == user.id).order_by(Todo.created_at.desc()).limit(100).all()


@router.post("", response_model=TodoOut, status_code=201, summary="新增待办")
def create_todo(body: TodoIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    todo = Todo(user_id=user.id, **body.model_dump())
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return todo


@router.put("/{todo_id}", response_model=TodoOut, summary="更新待办")
def update_todo(todo_id: int, body: TodoIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    todo = db.get(Todo, todo_id)
    if not todo or todo.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "待办不存在")
    old_status = todo.status
    for k, v in body.model_dump().items():
        setattr(todo, k, v)
    # 状态变化时同步关联方歌的勾选状态
    if todo.status != old_status:
        _sync_formula_song_state(db, todo)
    db.commit()
    db.refresh(todo)
    return todo


@router.delete("/{todo_id}", status_code=204, summary="删除待办")
def delete_todo(todo_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    todo = db.get(Todo, todo_id)
    if not todo or todo.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "待办不存在")
    # 删除关联待办时取消方歌勾选
    if todo.ref_type == "formula_song" and todo.ref_id:
        song = db.get(FormulaSong, todo.ref_id)
        if song and song.user_id == user.id:
            song.is_mastered = False
    db.delete(todo)
    db.commit()


@router.post("/from-extension", response_model=TodoOut, status_code=201, summary="扩展剪藏入口")
def from_extension(
    body: TodoIn,
    db: Session = Depends(get_db),
    x_api_token: str = Header(..., alias="X-API-Token"),
):
    """浏览器扩展专用：用 X-API-Token（即 access_token）认证，不需要 Cookie。"""
    try:
        payload = decode_token(x_api_token)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API Token 无效")
    user = db.get(User, int(payload.get("sub", "0")))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    data = body.model_dump()
    data["source"] = "extension"
    todo = Todo(user_id=user.id, **data)
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return todo


class ToPlanIn(BaseModel):
    mark_done: bool = Field(default=False, description="转换后是否标记待办为已完成")


@router.post("/{todo_id}/to-plan", summary="待办转学习计划")
def to_plan(
    todo_id: int,
    body: ToPlanIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """将待办转为今日学习计划项。"""
    todo = db.get(Todo, todo_id)
    if not todo or todo.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "待办不存在")

    today = datetime.now(timezone.utc).date()
    plan = (
        db.query(DailyPlan)
        .filter(DailyPlan.user_id == user.id, DailyPlan.plan_date == today)
        .first()
    )
    if not plan:
        plan = DailyPlan(user_id=user.id, plan_date=today, items=[])
        db.add(plan)

    item_id = f"todo-{todo.id}"
    existing_items = plan.items or []
    # 避免重复添加
    if any(it.get("id") == item_id for it in existing_items):
        if body.mark_done:
            todo.status = "done"
            todo.completed_at = datetime.now(timezone.utc)
            db.commit()
        return {"plan_date": today.isoformat(), "items": plan.items, "added": False}

    existing_items.append({
        "id": item_id,
        "title": todo.title,
        "description": todo.description or "",
        "url": todo.url or "",
        "source": "todo",
        "todo_id": todo.id,
        "done": False,
    })
    plan.items = existing_items

    if body.mark_done:
        todo.status = "done"
        todo.completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(plan)
    return {"plan_date": today.isoformat(), "items": plan.items, "added": True}
