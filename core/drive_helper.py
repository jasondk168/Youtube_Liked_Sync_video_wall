"""Google Drive 共享文件夹文件列表获取 + 文件下载（无需 OAuth）
增强版：处理大文件确认页面 + 病毒扫描警告页面 + 验证 ZIP 魔数
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
                return [f for f in files if f['name'].lower().endswith('.zip')]
        except Exception:
            continue
    return []

def download_file_from_drive(file_id: str) -> bytes:
    """
    从 Google Drive 下载文件（自动绕过病毒扫描警告页面）
    返回 bytes，并验证 ZIP 魔数
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    
    # 第一步：请求下载（可能会被重定向到警告页面）
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = session.get(url, timeout=60, allow_redirects=True)
    response.raise_for_status()

    # 检查返回的是文件还是 HTML 警告页面
    content_type = response.headers.get('content-type', '')
    if 'text/html' in content_type:
        # 检测病毒扫描警告页面
        soup = BeautifulSoup(response.text, 'html.parser')
        title_tag = soup.find('title')
        page_title = title_tag.get_text(strip=True) if title_tag else ''
        is_virus_warning = 'Virus scan warning' in page_title
        
        # 提取确认参数（多种方法）
        confirm_param = None
        
        # 方法 A：从表单 hidden input 提取
        for form in soup.find_all('form'):
            for inp in form.find_all('input', type='hidden'):
                if inp.get('name') == 'confirm':
                    confirm_param = inp.get('value')
                    break
        
        # 方法 B：从页面 JavaScript 或 URL 中正则提取
        if not confirm_param:
            match = re.search(r'confirm=([a-zA-Z0-9_-]+)', response.text)
            if match:
                confirm_param = match.group(1)
        
        # 方法 C：如果页面有 download_warning cookie 或者 t 参数
        if not confirm_param:
            # 有些警告页面使用 't' 作为参数名
            match = re.search(r'[?&]t=([a-zA-Z0-9_-]+)', response.text)
            if match:
                confirm_param = match.group(1)
        
        # 如果找到了确认参数，重新请求
        if confirm_param:
            params = {
                'export': 'download',
                'id': file_id,
                'confirm': confirm_param,
            }
            response = session.get('https://drive.google.com/uc', params=params, 
                                    timeout=60, allow_redirects=True)
            response.raise_for_status()
            
            # 如果仍然是 HTML，可能是下载警告 cookie 需要处理
            if 'text/html' in response.headers.get('content-type', ''):
                # 检查 cookie 中是否有 download_warning
                if 'download_warning' in dict(session.cookies):
                    # 已经取得 cookie，重试原始请求
                    response = session.get(url, timeout=60, allow_redirects=True)
                    response.raise_for_status()
                else:
                    # 尝试提交表单（模拟点击 "Download anyway"）
                    soup2 = BeautifulSoup(response.text, 'html.parser')
                    for form2 in soup2.find_all('form'):
                        action = form2.get('action', '')
                        inputs = form2.find_all('input')
                        params2 = {}
                        for inp in inputs:
                            name = inp.get('name')
                            value = inp.get('value', '')
                            if name:
                                params2[name] = value
                        if params2:
                            if action.startswith('/'):
                                action = 'https://drive.google.com' + action
                            response = session.get(action, params=params2, 
                                                    timeout=60, allow_redirects=True)
                            response.raise_for_status()
                            if 'text/html' not in response.headers.get('content-type', ''):
                                break
                    # 如果还是 HTML，抛出详细的错误
                    if 'text/html' in response.headers.get('content-type', ''):
                        raise RuntimeError(f"下载失败：未能绕过 Google Drive 的确认页面。")
        else:
            # 没有找到确认参数，可能是需要 cookie 或重试
            raise RuntimeError(f"下载失败：无法从警告页面中提取确认参数。页面标题: {page_title}")
    
    # 验证 ZIP 魔数
    content = response.content
    if len(content) < 4 or content[:4] != b'PK\x03\x04':
        raise RuntimeError(f"下载的文件不是有效的 ZIP 格式（magic: {content[:4].hex()}）")
    
    return content
