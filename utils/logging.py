# -*- coding: utf-8 -*-
"""
项目统一日志配置

基于 settings.LOG_CONFIG 提供全局日志实例。
所有模块统一使用 logger 替代 print()。

使用方式:
    from utils.logging import get_logger
    logger = get_logger(__name__)
    logger.info("处理 %s 完成", code)
    logger.warning("数据异常: %s", reason)
    logger.error("操作失败", exc_info=True)
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from config.settings import LOG_CONFIG


def _init_logger() -> logging.Logger:
    """初始化根日志器"""
    logger = logging.getLogger("quantking")
    logger.setLevel(getattr(logging, LOG_CONFIG.get("level", "INFO"), logging.INFO))

    # 避免重复添加 Handler
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        LOG_CONFIG.get("format", "%(asctime)s [%(levelname)s] %(name)s: %(message)s"),
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台输出
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # 文件输出（自动轮转）
    log_file = LOG_CONFIG.get("file", "")
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=LOG_CONFIG.get("max_bytes", 10 * 1024 * 1024),
            backupCount=LOG_CONFIG.get("backup_count", 5),
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger


_ROOT_LOGGER = _init_logger()


def get_logger(name: str) -> logging.Logger:
    """获取指定模块的日志器"""
    return _ROOT_LOGGER.getChild(name)
