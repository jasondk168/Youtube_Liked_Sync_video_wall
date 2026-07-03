"""
Google Drive 共享文件夹文件列表获取 + 文件下载（无需 OAuth）
"""
import requests
from bs4 import BeautifulSoup
import re

def get_drive_file_list(folder_id: str):
    """
    从 Google Drive 公共共享文件夹获取文件列表
    返回 list[{"name":..., "id":...}]，仅包含 .zip 文件
    """
    urls = [
        f"https://drive.google.com/embeddedfolderview?id={folder_id}",
        f"https://drive.google.com/drive/folders/{folder_id}",
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            files = []
            # 方法1：data-id 属性
            for el in soup.find_all(attrs={"data-id": True}):
                name_el = el.find("a")
                name = name_el.get_text(strip=True) if name_el else ""
                file_id = el.get("data-id")
                if name and file_id:
                    files.append({"name": name, "id": file_id})
            # 方法2：/file/d/ 模式
            if not files:
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    match = re.search(r'/file/d/([^/]+)', href)
                    if match:
                        file_id = match.group(1)
                        name = a.get_text(strip=True)
                        files.append({"name": name, "id": file_id})
            if files:
                # 只返回 .zip 文件
                return [f for f in files if f['name'].lower().endswith('.zip')]
        except Exception:
            continue
    return []

def download_file_from_drive(file_id: str) -> bytes:
    """
    从 Google Drive 下载文件（直接下载）
    返回 bytes
    """
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    with requests.Session() as s:
        resp = s.get(url, headers=headers, stream=True, timeout=60)
        resp.raise_for_status()
        return resp.content