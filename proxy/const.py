from pathlib import Path

VERSION = "0.0.3"

API_HOST = "0.0.0.0"
API_PORT = 9000

HEADERS: dict[str, str] = {}

JOURNAL_DIR = Path("./journal/")
JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
