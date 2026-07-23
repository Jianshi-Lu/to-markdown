"""本地服务启动入口。"""

import argparse
import os

import uvicorn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start the to-markdown HTTP service.",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("SERVER_HOST", "127.0.0.1"),
        help="Address to bind (default: SERVER_HOST or 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("SERVER_PORT", "8081")),
        help="Port to bind (default: SERVER_PORT or 8081).",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Restart automatically after source changes; use only for development.",
    )
    parser.add_argument(
        "--log-level",
        choices=("critical", "error", "warning", "info", "debug", "trace"),
        default=os.getenv("SERVER_LOG_LEVEL", "info"),
        help="Uvicorn log level (default: SERVER_LOG_LEVEL or info).",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )

if __name__ == "__main__":
    main()
