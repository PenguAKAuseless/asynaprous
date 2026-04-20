"""Environment variable loading helpers for local development."""

import os


def _strip_quotes(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return value


def _unescape(value):
    return (
        value.replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\'", "'")
        .replace("\\\\", "\\")
    )


def load_dotenv(env_path=None, override=False):
    """Load key-value pairs from .env file into process environment."""
    if env_path is None:
        root_dir = os.path.dirname(os.path.abspath(__file__))
        env_path = os.path.join(root_dir, ".env")

    if not os.path.exists(env_path):
        return {}

    loaded = {}
    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("export "):
                line = line[7:].strip()

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = _strip_quotes(value.strip())
            value = _unescape(value)

            if not key:
                continue

            if not override and key in os.environ:
                loaded[key] = os.environ[key]
                continue

            os.environ[key] = value
            loaded[key] = value

    return loaded
