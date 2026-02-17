"""Retry helpers with exponential backoff for resilient API calls."""

import logging
import time
from functools import wraps
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")


def with_retry(
    max_retries: int = 3,
    base_delay: float = 5.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator that retries a function with exponential backoff."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: Exception | None = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2**attempt)
                        logger.warning(
                            "Retry %d/%d after %s: %s. Waiting %.1fs.",
                            attempt + 1,
                            max_retries,
                            func.__name__,
                            e,
                            delay,
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            "All %d retries failed for %s: %s",
                            max_retries,
                            func.__name__,
                            e,
                        )
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator
