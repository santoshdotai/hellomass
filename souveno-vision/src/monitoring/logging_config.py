"""Structured, rotating, credential-redacting logging (loguru).

* console + rotating text log   logs/souveno_vision_intelligence.log
* rotating JSON-lines log       logs/souveno_vision_intelligence.jsonl
* every record passes through `redact_text` before it is written, so an RTSP
  URL with a password can never leak even if someone logs it by mistake.
* uvicorn/fastapi std-logging records are routed into the same sinks.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from loguru import logger

from src.security.redaction import redact_text

_CONFIGURED = False


class _InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - passthrough
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, redact_text(record.getMessage()))


def _redacting_patcher(record):
    record["message"] = redact_text(record["message"])
    if record["exception"] is not None:
        exc = record["exception"]
        if exc.value is not None and exc.value.args:
            try:
                exc.value.args = tuple(redact_text(a) if isinstance(a, str) else a for a in exc.value.args)
            except Exception:
                pass


def setup_logging(level: str = "INFO", directory: str | Path = "logs", rotation: str = "10 MB",
                  retention: int = 7, base_dir: Path | None = None) -> Path | None:
    global _CONFIGURED
    directory = Path(directory)
    if base_dir and not directory.is_absolute():
        directory = base_dir / directory
    logger.remove()
    logger.configure(patcher=_redacting_patcher)
    logger.add(sys.stderr, level=level, enqueue=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <cyan>{name}</cyan> | {message}")
    log_path = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        log_path = directory / "souveno_vision_intelligence.log"
        logger.add(log_path, level="DEBUG", rotation=rotation, retention=retention, enqueue=True,
                   format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {name}:{function}:{line} | {message}")
        logger.add(directory / "souveno_vision_intelligence.jsonl", level="INFO", rotation=rotation,
                   retention=retention, enqueue=True, serialize=True)
    except OSError as exc:  # read-only location — console logging still works
        logger.warning(f"File logging disabled: {exc}")
    if not _CONFIGURED:
        logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
            logging.getLogger(name).handlers = [_InterceptHandler()]
            logging.getLogger(name).propagate = False
        _CONFIGURED = True
    return log_path
