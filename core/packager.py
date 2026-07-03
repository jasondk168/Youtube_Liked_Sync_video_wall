"""
将下载好的 clip 打包成 ZIP（每5个一组），包含 manifest.json
"""
import zipfile
import json
from pathlib import Path
from datetime import datetime
import re

def pack_clips_into_zip(clip_entries: list, pack_index: int, output_dir: Path) -> Path:
    """
    将 clip_entries（list[dict]）打包成一个 ZIP 文件
    返回 ZIP 文件路径
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # ZIP 文件名：第一个视频标题 + 当前时间
    first_title = clip_entries[0].get('title', 'video')
    safe_title = re.sub(r'[\\/:*?"<>|]', '_', first_title)[:50]
    now_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    zip_name = f"{safe_title}_{now_str}.zip"
    zip_path = output_dir / zip_name

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            "version": 1,
            "description": "YouTube Liked Videos Pack",
            "items": []
        }
        for entry in clip_entries:
            clip_name = entry['clip_name']
            text_name = entry['text_name']
            thumbnail_name = entry.get('thumbnail_name', None)

            # 写入 clips/
            zf.write(entry['clip_path'], f"clips/{clip_name}")
            # 写入 texts/
            zf.write(entry['text_path'], f"texts/{text_name}")
            # 写入 thumbnails/（如果存在）
            if thumbnail_name and entry.get('thumbnail_path') and Path(entry['thumbnail_path']).exists():
                zf.write(entry['thumbnail_path'], f"thumbnails/{thumbnail_name}")

            manifest["items"].append({
                "index": int(clip_name.split('_')[1].split('.')[0]),
                "text": entry.get('title', ''),
                "clip_name": clip_name,
                "text_name": text_name,
                "thumbnail_name": thumbnail_name,
                "start_sec": 0,
                "end_sec": 0,
                "actual_duration": entry.get('actual_duration', 0),
                "url": entry.get('url', ''),
            })
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    return zip_path