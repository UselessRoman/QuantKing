# -*- coding: utf-8 -*-
"""
重试装饰器模块

提供 @retry_on_failure 装饰器，对网络请求等易失败操作自动重试。

特性:
    - 指数退避: 等待时间依次为 base_delay * 2^attempt
    - 最大重试次数限制
    - 可指定捕获的异常类型
    - 失败时日志记录

使用方式:
    from utils.retry import retry_on_failure

    @retry_on_failure(max_retries=3, base_delay=1.0)
    def fetch_data(url: str):
        ...
"""
import time
import functools
from typing import Callable, Type, Tuple
from utils.logging import get_logger

_logger = get_logger("retry")


def retry_on_failure(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    logger=None,
) -> Callable:
    """
    自动重试装饰器

    参数:
        max_retries: 最大重试次数
        base_delay:  基准延迟秒数（指数退避）
        exceptions:  触发重试的异常类型
        logger:      日志器（默认自动获取）

    返回:
        装饰后的函数
    """
    log = logger or _logger

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        log.warning(
                            "%s 第 %d/%d 次失败 (%s)，%.1f秒后重试...",
                            func.__name__, attempt + 1, max_retries, e, delay,
                        )
                        time.sleep(delay)
                    else:
                        log.error(
                            "%s 重试 %d 次后仍失败: %s",
                            func.__name__, max_retries, e, exc_info=True,
                        )
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator
