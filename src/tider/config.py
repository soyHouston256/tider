import os


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)
