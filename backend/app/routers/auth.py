"""auth 路由：登录、刷新 token、当前用户、首次启动设置向导。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    SetupRequest,
    SetupStatusResponse,
    TokenResponse,
    UserInfo,
)
from app.services.init_db import seed_preset_data

router = APIRouter(prefix="/auth", tags=["auth"])


def _is_initialized(db: Session) -> bool:
    """单用户场景：users 表是否有记录 = 系统是否已初始化。"""
    return db.query(User).count() > 0


@router.get("/setup/status", response_model=SetupStatusResponse, summary="检查是否已初始化")
def setup_status(db: Session = Depends(get_db)):
    return SetupStatusResponse(initialized=_is_initialized(db))


@router.post("/setup", response_model=TokenResponse, summary="首次启动设置账号密码")
def setup(body: SetupRequest, db: Session = Depends(get_db)):
    if _is_initialized(db):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "系统已初始化，请直接登录")

    user = User(username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    # 为新用户预置科目标签 + 三大知识库
    seed_preset_data(user.id, db)

    return _make_token(user)


@router.post("/login", response_model=TokenResponse, summary="登录")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    return _make_token(user)


@router.post("/refresh", response_model=TokenResponse, summary="刷新 token")
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "refresh_token 无效")

    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token 类型错误")

    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户不存在")
    return _make_token(user)


@router.get("/me", response_model=UserInfo, summary="当前用户信息")
def me(user: User = Depends(get_current_user)):
    return UserInfo(id=user.id, username=user.username, settings=user.settings or {})


def _make_token(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
        user=UserInfo(id=user.id, username=user.username, settings=user.settings or {}),
    )
