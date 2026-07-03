"""SQLite 数据库操作 - 记录已下载视频，支持 pending/zipped 状态"""
import sqlite3
import datetime
from config import DB_PATH

def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_database():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS downloaded_videos (
            video_id TEXT PRIMARY KEY,
            title TEXT,
            url TEXT,
            clip_name TEXT DEFAULT '',
            downloaded_at TEXT,
            pack_zip TEXT,
            status TEXT DEFAULT 'pending'
        )
    """)
    conn.commit()
    conn.close()

def is_already_downloaded(video_id: str) -> bool:
    conn = get_connection()
    cur = conn.execute("SELECT 1 FROM downloaded_videos WHERE video_id=?", (video_id,))
    exists = cur.fetchone() is not None
    conn.close()
    return exists

def mark_downloaded(video_id: str, title: str, url: str, clip_name: str = "",
                    pack_zip: str = None, status: str = "pending"):
    """记录下载视频，增加 clip_name 字段"""
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO downloaded_videos "
        "(video_id, title, url, clip_name, downloaded_at, pack_zip, status) "
        "VALUES (?,?,?,?,?,?,?)",
        (video_id, title, url, clip_name,
         datetime.datetime.now().isoformat(),
         pack_zip or '', status)
    )
    conn.commit()
    conn.close()

def update_status(video_id: str, status: str, pack_zip: str = None):
    """更新下载状态和打包文件名"""
    conn = get_connection()
    if pack_zip:
        conn.execute("UPDATE downloaded_videos SET status=?, pack_zip=? WHERE video_id=?",
                     (status, pack_zip, video_id))
    else:
        conn.execute("UPDATE downloaded_videos SET status=? WHERE video_id=?",
                     (status, video_id))
    conn.commit()
    conn.close()

def get_pending_video_ids() -> list:
    """获取所有 pending 状态的 video_id 列表"""
    conn = get_connection()
    cur = conn.execute("SELECT video_id FROM downloaded_videos WHERE status='pending'")
    ids = [row["video_id"] for row in cur.fetchall()]
    conn.close()
    return ids

def get_pending_count() -> int:
    conn = get_connection()
    cur = conn.execute("SELECT COUNT(*) as cnt FROM downloaded_videos WHERE status='pending'")
    cnt = cur.fetchone()["cnt"]
    conn.close()
    return cnt

def get_clip_name_by_video_id(video_id: str) -> str:
    conn = get_connection()
    cur = conn.execute("SELECT clip_name FROM downloaded_videos WHERE video_id=?", (video_id,))
    row = cur.fetchone()
    conn.close()
    return row["clip_name"] if row else ""