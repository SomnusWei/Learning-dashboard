"""认证相关 Pydantic 模型。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SetupRequest(BaseModel):
    """首次启动设置账号密码。"""

    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=6, max_length=64)


class SetupStatusResponse(BaseModel):
    initialized: bool
    """true: 已初始化（不可再调用 /setup）；false: 未初始化（前端跳转到设置向导）。"""


class LoginRequest(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    id: int
    username: str
    settings: dict[str, Any] = {}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserInfo


class RefreshRequest(BaseModel):
    refresh_token: str


TokenResponse.model_rebuild()
