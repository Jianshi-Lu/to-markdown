"""日志入口。"""

import logging


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
