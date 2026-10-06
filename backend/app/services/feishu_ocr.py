"""飞书 OCR 服务：调用飞书开放平台文字识别 API。

配置优先级：传入参数 > 环境变量。
用户可在设置界面配置 FEISHU_APP_ID / FEISHU_APP_SECRET。
"""
import base64
import os
import time
from typing import Optional

import httpx

# 环境变量作为默认值
ENV_APP_ID = os.getenv("FEISHU_APP_ID", "")
ENV_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")

_token_cache: dict = {"token": "", "expire_at": 0, "app_id": ""}


def resolve_config(user_settings: Optional[dict] = None) -> tuple[str, str]:
    """从用户设置或环境变量解析飞书配置。"""
    feishu_cfg = (user_settings or {}).get("feishu", {})
    app_id = feishu_cfg.get("app_id") or ENV_APP_ID
    app_secret = feishu_cfg.get("app_secret") or ENV_APP_SECRET
    return app_id, app_secret


def is_configured(user_settings: Optional[dict] = None) -> bool:
    app_id, app_secret = resolve_config(user_settings)
    return bool(app_id and app_secret)


async def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    """获取飞书 tenant_access_token，带缓存（按 app_id 区分）。"""
    now = time.time()
    if _token_cache["token"] and _token_cache["app_id"] == app_id and _token_cache["expire_at"] > now:
        return _token_cache["token"]

    if not (app_id and app_secret):
        raise RuntimeError("飞书 OCR 未配置：请在设置界面填写 App ID 和 App Secret")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=15,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取飞书 token 失败: {data.get('msg', '未知错误')}")
        token = data["tenant_access_token"]
        expire = data.get("expire", 7200)
        _token_cache["token"] = token
        _token_cache["app_id"] = app_id
        _token_cache["expire_at"] = now + expire - 300
        return token


async def recognize_image(image_bytes: bytes, user_settings: Optional[dict] = None) -> str:
    """调用飞书 OCR 识别图片文字。"""
    app_id, app_secret = resolve_config(user_settings)
    token = await get_tenant_access_token(app_id, app_secret)
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://open.feishu.cn/open-apis/optical_char_recognition/v1/image/basic_recognize",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={"image": image_b64},
            timeout=30,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书 OCR 识别失败: {data.get('msg', '未知错误')}")
        return data.get("data", {}).get("content", "")
