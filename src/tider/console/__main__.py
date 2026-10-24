"""Installed entry point: python -m tider.console or tider-console."""

import argparse
import os

import uvicorn
from dotenv import load_dotenv

from .api import create_app
from .settings import Settings


def main():
    parser = argparse.ArgumentParser(description="Consola local de agentes TiderOps")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    parser.add_argument("--env-file", default=os.environ.get("TIDER_ENV_FILE"))
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=False)
    # Local runs do not send traces to a hosted observability service.
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    uvicorn.run(create_app(Settings.from_env()), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
