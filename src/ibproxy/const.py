from pathlib import Path

VERSION = "0.0.7"

# Use the loopback interface for security. If the proxy is hosted on EC2 this
# will mean that requests from the internet will not reach the proxy.
#
API_HOST = "127.0.0.1"
API_PORT = 9000

HEADERS: dict[str, str] = {}

JOURNAL_DIR = Path("./journal/")
