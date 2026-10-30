"""Validated, opt-in environment configuration."""
import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Settings(BaseModel):
    ping_count: int = Field(4, ge=1, le=100)
    timeout_ms: int = Field(1000, ge=100, le=60000)
    concurrency: int = Field(8, ge=1, le=64)
    interval_seconds: float = Field(10, ge=0.1)
    max_scan_hosts: int = Field(1024, ge=1, le=4096)
    report_dir: Path = Path('reports')

    @classmethod
    def from_env(cls, path: str | None = None) -> 'Settings':
        load_dotenv(path, override=False)
        return cls(**{k: os.environ['TETHER_' + k.upper()] for k in cls.model_fields
                      if 'TETHER_' + k.upper() in os.environ})
