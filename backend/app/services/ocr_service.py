"""统一 OCR 服务：优先本地 PaddleOCR，回退飞书 OCR。"""
import os
from typing import Optional

import httpx

from .feishu_ocr import is_configured as feishu_configured
from .feishu_ocr import recognize_image as feishu_recognize

OCR_SERVICE_URL = os.getenv("OCR_SERVICE_URL", "http://ocr:8866")


async def recognize(image_bytes: bytes, user_settings: Optional[dict] = None) -> str:
    """识别图片文字，优先本地 PaddleOCR，失败回退飞书 OCR。"""
    # 1. 尝试本地 PaddleOCR
    try:
        text = await _recognize_local(image_bytes)
        if text:
            return text
    except Exception as e:
        # 本地 OCR 失败，记录日志并回退
        import logging
        logging.getLogger("ocr").warning(f"本地 PaddleOCR 失败: {e}，尝试飞书 OCR")

    # 2. 回退飞书 OCR
    if feishu_configured(user_settings):
        try:
            return await feishu_recognize(image_bytes, user_settings)
        except Exception as e:
            raise RuntimeError(f"OCR 识别失败（本地+飞书均失败）: {e}")

    raise RuntimeError("本地 PaddleOCR 不可用，且未配置飞书 OCR")


async def _recognize_local(image_bytes: bytes) -> str:
    """调用本地 PaddleOCR 服务。"""
    async with httpx.AsyncClient(timeout=60) as client:
        files = {"image": ("image.png", image_bytes, "image/png")}
        resp = await client.post(f"{OCR_SERVICE_URL}/ocr", files=files)
        if resp.status_code != 200:
            raise RuntimeError(f"本地 OCR 服务返回 {resp.status_code}: {resp.text}")
        data = resp.json()
        return data.get("text", "")
