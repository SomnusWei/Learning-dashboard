"""后端配置：读取环境变量，集中管理设置。"""
from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "Learning Dashboard"
    APP_ENV: str = "prod"  # dev / prod
    API_PREFIX: str = "/api/v1"

    # 数据库
    DATABASE_URL: str = "postgresql://learning:learning@postgres:5432/learning"

    # JWT
    JWT_SECRET: str = "CHANGE_ME_IN_PRODUCTION"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 天
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # CORS（白名单，逗号分隔）
    CORS_ORIGINS: List[str] = [
        "https://your-domain.com:8443",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # 文件上传
    UPLOAD_DIR: str = "/app/data/uploads"
    BACKGROUND_DIR: str = "/app/data/backgrounds"
    MAX_UPLOAD_MB: int = 5

    # OCR 服务
    OCR_BASE_URL: str = "http://ocr:8866"

    # 初始化标志（运行时持久化到数据库 users 表是否存在记录）
    # 此变量仅用于首次启动判断的辅助；以数据库实际状态为准。

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
