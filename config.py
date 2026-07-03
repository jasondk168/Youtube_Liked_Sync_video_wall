import os
from pathlib import Path

_project_dir = Path(__file__).resolve().parent

_portable_root_candidate = _project_dir.parents[1] if len(_project_dir.parents) >= 2 else None
IS_PORTABLE = False
if _portable_root_candidate:
    if (_portable_root_candidate / "python.exe").exists() and (_portable_root_candidate / "bin").exists():
        IS_PORTABLE = True

PROJECT_DIR = _project_dir
DATA_DIR = PROJECT_DIR / "data"
OUTPUT_DIR = PROJECT_DIR / "output"
PENDING_DIR = OUTPUT_DIR / "pending"
TEMP_DIR = PROJECT_DIR / "temp_downloads"
CONFIG_FILE = PROJECT_DIR / "config.json"
CLIENT_SECRET_FILE = PROJECT_DIR / "client_secret.json"
TOKEN_FILE = PROJECT_DIR / "token.json"

if IS_PORTABLE:
    PORTABLE_ROOT = _portable_root_candidate
    BIN_DIR = PORTABLE_ROOT / "bin"
    os.environ["PATH"] = str(BIN_DIR) + ";" + os.environ.get("PATH", "")
else:
    PORTABLE_ROOT = None
    BIN_DIR = None

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

YTDLP_CMD = "yt-dlp_2"
YTDLP_FORMAT = "bestvideo[height<=480]+bestaudio/best[height<=480]"
VIDEOS_PER_PACK = 5
DB_PATH = DATA_DIR / "youtube_liked.db"