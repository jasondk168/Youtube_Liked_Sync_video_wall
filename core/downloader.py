"""使用 yt-dlp 下载 480P 视频 + 缩略图 + 生成文本文件
翻译引擎：本地优先 googletrans，否则 deep-translator
下载文件统一放入 output/pending 的子目录：clips/、texts/、thumbnails/
"""
import re
import requests
import yt_dlp
from pathlib import Path

# ===== 双引擎翻译器（本地优先）=====
_translator_gt = None
_translator_dt = None
try:
    from googletrans import Translator as GT
    _translator_gt = GT()
except Exception:
    pass
if _translator_gt is None:
    try:
        from deep_translator import GoogleTranslator
        _translator_dt = GoogleTranslator(source='auto', target='zh-CN')
    except Exception:
        pass

def _translate_title(title: str) -> str:
    """将标题翻译为中文，失败返回空字符串"""
    if not title:
        return ""
    # 优先 googletrans
    if _translator_gt:
        try:
            result = _translator_gt.translate(title, dest='zh-cn')
            return result.text if result else ""
        except Exception:
            pass
    # 回退 deep-translator
    if _translator_dt:
        try:
            return _translator_dt.translate(title)
        except Exception:
            pass
    return ""

def sanitize_filename(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    return name[:max_len].strip()

def download_video_480p(video_url: str, clip_index: int, output_root: Path) -> dict:
    """
    下载单个视频并返回元数据
    output_root: 应传入 PENDING_DIR（即 output/pending）
    文件将写入 output_root/clips/, output_root/texts/, output_root/thumbnails/
    """
    clips_dir = output_root / "clips"
    texts_dir = output_root / "texts"
    thumbs_dir = output_root / "thumbnails"
    for d in [clips_dir, texts_dir, thumbs_dir]:
        d.mkdir(parents=True, exist_ok=True)

    clip_name = f"Clip_{clip_index:03d}.mp4"
    text_name = f"Clip_{clip_index:03d}.txt"
    thumbnail_name = f"Clip_{clip_index:03d}.jpg"
    clip_path = clips_dir / clip_name
    text_path = texts_dir / text_name
    thumbnail_path = thumbs_dir / thumbnail_name

    # 1. 提取元数据（不下载）
    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
        info = ydl.extract_info(video_url, download=False)
        title = info.get('title', '')
        description = info.get('description', '')
        channel_title = info.get('channel', '') or info.get('uploader', '')
        published_at = info.get('upload_date', '')
        duration = info.get('duration', 0)
        thumbnail_url = info.get('thumbnail', '')

    # 2. 翻译标题
    translated_title = _translate_title(title)

    # 3. 下载缩略图
    if thumbnail_url:
        try:
            resp = requests.get(thumbnail_url, timeout=10)
            if resp.status_code == 200:
                thumbnail_path.write_bytes(resp.content)
        except Exception:
            pass

    # 4. 写入文本文件
    text_lines = [f"Title: {title}"]
    if translated_title:
        text_lines.append(f"Translated Title: {translated_title}")
    text_lines += [
        f"Channel: {channel_title}",
        f"Published: {published_at}",
        f"URL: {video_url}",
        f"Description:\n{description}",
    ]
    text_content = "\n".join(text_lines)
    text_path.write_text(text_content, encoding='utf-8')

    # 5. 下载 480P 视频
    outtmpl = str(clips_dir / f"Clip_{clip_index:03d}.%(ext)s")
    ydl_opts = {
        'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]',
        'outtmpl': outtmpl,
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
        'socket_timeout': 30,
        'retries': 3,
        'fragment_retries': 3,
        'extractor_retries': 3,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    # 6. 确保最终 mp4 存在
    if not clip_path.exists():
        for ext in ['.webm', '.mkv']:
            p = clips_dir / f"Clip_{clip_index:03d}{ext}"
            if p.exists():
                p.rename(clip_path)
                break
    if not clip_path.exists():
        raise RuntimeError(f"下载失败，未找到输出文件：{video_url}")

    return {
        "clip_name": clip_name,
        "text_name": text_name,
        "thumbnail_name": thumbnail_name if thumbnail_path.exists() else None,
        "title": title,
        "translated_title": translated_title,
        "url": video_url,
        "actual_duration": duration,
        "clip_path": str(clip_path),
        "text_path": str(text_path),
        "thumbnail_path": str(thumbnail_path) if thumbnail_path.exists() else None,
        "channel_title": channel_title,
        "published_at": published_at,
    }