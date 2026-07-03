"""YouTube Liked Downloader - Streamlit 主程序
本地模式：同步并下载 + 手动勾选打包 + 导入浏览
云端模式：仅导入浏览
所有标题自动显示中文翻译（优先读取 Translated Title，否则双引擎实时翻译）
"""
import sys, os, json, zipfile, base64, tempfile, shutil, time, re, sqlite3
from pathlib import Path
from io import BytesIO
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components

# ===== 环境检测（必须放在其他导入之前）=====
project_dir = Path(__file__).resolve().parent
portable_root_candidate = project_dir.parents[1] if len(project_dir.parents) >= 2 else None
IS_PORTABLE = False
if portable_root_candidate and (portable_root_candidate / "python.exe").exists() and (portable_root_candidate / "bin").exists():
    IS_PORTABLE = True

if IS_PORTABLE:
    bin_path = portable_root_candidate / "bin"
    os.environ["PATH"] = str(bin_path) + ";" + os.environ.get("PATH", "")

# ===== 双引擎翻译器（本地优先 googletrans，云端回退 deep-translator）=====
_translator = None
try:
    from googletrans import Translator as GT
    _translator = GT()
    _trans_engine = "googletrans"
except Exception:
    try:
        from deep_translator import GoogleTranslator as DT
        _translator = DT(source='auto', target='zh-CN')
        _trans_engine = "deep-translator"
    except Exception:
        _translator = None
        _trans_engine = None

def _translate_text(text: str) -> str:
    """实时翻译标题为中文，失败返回空字符串"""
    if not _translator or not text:
        return ""
    try:
        if _trans_engine == "googletrans":
            result = _translator.translate(text, dest='zh-cn')
            return result.text if result else ""
        else:
            return _translator.translate(text)
    except Exception:
        return ""

# ===== 导入自有模块 =====
from config import (
    IS_PORTABLE as CFG_IS_PORTABLE,
    DATA_DIR, OUTPUT_DIR, PENDING_DIR, CONFIG_FILE,
    VIDEOS_PER_PACK, DB_PATH
)
if IS_PORTABLE:
    from core.youtube_api import get_authenticated_service, get_liked_videos
    from core.downloader import download_video_480p
    from core.db_helper import (
        init_database, is_already_downloaded, mark_downloaded,
        update_status, get_pending_count
    )
from core.drive_helper import get_drive_file_list, download_file_from_drive
from core.packager import pack_clips_into_zip

# ===== 辅助函数（放在最前面，避免调用时未定义）=====
def _import_zip_from_bytes(zip_bytes):
    """解析 ZIP bytes，填充 st.session_state.reviews，并尝试提取/翻译标题"""
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        if 'manifest.json' not in zf.namelist():
            st.error("ZIP 中缺少 manifest.json")
            return
        manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
        items = manifest.get('items', [])
        if not items:
            st.warning("manifest 中沒有條目")
            return
        tmp_dir = Path(tempfile.mkdtemp())
        try:
            zf.extractall(tmp_dir)
        except Exception:
            pass
        reviews = []
        for item in items:
            clip_name = item['clip_name']
            text_name = item['text_name']
            thumbnail_name = item.get('thumbnail_name', None)
            clip_bytes = (tmp_dir / 'clips' / clip_name).read_bytes() if (tmp_dir / 'clips' / clip_name).exists() else None
            text_bytes = (tmp_dir / 'texts' / text_name).read_bytes() if (tmp_dir / 'texts' / text_name).exists() else None
            thumb_bytes = None
            if thumbnail_name and (tmp_dir / 'thumbnails' / thumbnail_name).exists():
                thumb_bytes = (tmp_dir / 'thumbnails' / thumbnail_name).read_bytes()
            # 优先从 txt 读取翻译标题
            translated_title = None
            if text_bytes:
                try:
                    content = text_bytes.decode('utf-8')
                    for line in content.splitlines():
                        if line.startswith('Translated Title:'):
                            translated_title = line[17:].strip()
                            break
                except Exception:
                    pass
            # 若没有翻译，实时翻译（仅本地，云端也可尝试）
            if not translated_title and item.get('text'):
                translated_title = _translate_text(item['text'])
            reviews.append({
                'index': item.get('index', 0),
                'text': item.get('text', ''),
                'translated_title': translated_title,
                'clip_name': clip_name,
                'text_name': text_name,
                'clip_bytes': clip_bytes,
                'text_bytes': text_bytes,
                'thumbnail_bytes': thumb_bytes,
                'url': item.get('url', ''),
                'actual_duration': item.get('actual_duration', 0),
            })
        st.session_state.reviews = reviews
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass

# ===== 初始化目录和数据库 =====
if IS_PORTABLE:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    (PENDING_DIR / "clips").mkdir(exist_ok=True)
    (PENDING_DIR / "texts").mkdir(exist_ok=True)
    (PENDING_DIR / "thumbnails").mkdir(exist_ok=True)
    init_database()

# ===== config.json 读写 =====
def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}
def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# ===== session_state 初始化 =====
if 'reviews' not in st.session_state:
    st.session_state.reviews = []
if 'drive_file_list' not in st.session_state:
    st.session_state.drive_file_list = []
if 'drive_file_list_fetched' not in st.session_state:
    st.session_state.drive_file_list_fetched = False
if 'download_running' not in st.session_state:
    st.session_state.download_running = False
if 'selected_clips' not in st.session_state:
    st.session_state.selected_clips = {}

# ===== Streamlit 页面 =====
st.set_page_config(page_title="YouTube Liked Downloader", layout="wide")
st.title("🎬 YouTube 點讚影片下載 + 手動打包 + 瀏覽")

# ===== 侧边栏菜单 =====
if IS_PORTABLE:
    mode = st.sidebar.radio("選擇功能", ["📥 同步與打包", "📂 匯入並瀏覽"])
else:
    mode = "📂 匯入並瀏覽"
    st.sidebar.info("☁️ 雲端模式：僅提供匯入瀏覽功能")

# ========== 模式一：同步與打包 ==========
if mode == "📥 同步與打包" and IS_PORTABLE:
    st.header("📥 同步點讚影片並下載 480P（手動勾選打包）")

    pending_count = get_pending_count()
    st.sidebar.info(f"📦 已下載待打包影片：{pending_count}")

    if st.button("🔄 開始同步並下載", type="primary", disabled=st.session_state.download_running):
        st.session_state.download_running = True
        try:
            youtube = get_authenticated_service()
            videos = get_liked_videos(youtube, max_results=0)
            st.info(f"取得 {len(videos)} 個點讚影片")

            new_vids = [v for v in videos if not is_already_downloaded(v['video_id'])]
            if not new_vids:
                st.success("所有點讚影片均已下載過！")
                st.session_state.download_running = False
                st.stop()

            st.info(f"需要下載 {len(new_vids)} 個新影片")

            # 获取当前 pending 中最大的序号（从 clips 子目录读取）
            existing_clips = sorted([p.stem for p in (PENDING_DIR / "clips").glob("Clip_*.mp4")])
            next_index = 1
            if existing_clips:
                max_num = max(int(f.split('_')[1]) for f in existing_clips)
                next_index = max_num + 1

            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, v in enumerate(new_vids):
                status_text.text(f"正在下載 ({i+1}/{len(new_vids)}): {v['title'][:50]}...")
                try:
                    clip_idx = next_index + i
                    entry = download_video_480p(v['url'], clip_idx, PENDING_DIR)
                    mark_downloaded(
                        video_id=v['video_id'],
                        title=v['title'],
                        url=v['url'],
                        clip_name=entry['clip_name'],
                        status='pending'
                    )
                except Exception as e:
                    st.warning(f"下載失敗 {v['url']}: {e}")
                progress_bar.progress((i+1)/len(new_vids))

            st.session_state.download_running = False
            st.success(f"下載完成，新增 {len(new_vids)} 個影片到待打包區")
            st.rerun()
        except Exception as e:
            st.error(f"錯誤：{e}")
            st.session_state.download_running = False

    # ---------- 手动选择打包区域 ----------
    st.markdown("---")
    st.subheader("📋 待打包影片清單（勾選要打包的影片）")

    pending_clips = sorted((PENDING_DIR / "clips").glob("Clip_*.mp4"))

    if st.checkbox("顯示偵錯資訊", value=False):
        st.write(f"PENDING_DIR: {PENDING_DIR}")
        st.write(f"找到檔案數: {len(pending_clips)}")
        for p in pending_clips:
            st.write(p.name)

    if not pending_clips:
        st.info("目前沒有待打包的影片，請先執行同步下載。")
    else:
        clip_info_list = []
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.cursor()
        for clip_path in pending_clips:
            clip_name = clip_path.name
            cur.execute("SELECT title, video_id FROM downloaded_videos WHERE clip_name=? AND status='pending'", (clip_name,))
            row = cur.fetchone()
            if row:
                title = row[0]
                video_id = row[1]
            else:
                text_path = PENDING_DIR / "texts" / clip_name.replace('.mp4', '.txt')
                title = clip_name
                if text_path.exists():
                    content = text_path.read_text(encoding='utf-8')
                    for line in content.splitlines():
                        if line.startswith('Title:'):
                            title = line[6:].strip()
                            break
                video_id = ""
            clip_info_list.append({
                "clip_name": clip_name,
                "title": title,
                "video_id": video_id
            })
        conn.close()

        if not clip_info_list:
            st.info("没有可显示的影片文件。")
        else:
            col_list, col_btn = st.columns([3, 1])
            with col_list:
                for info in clip_info_list:
                    key = info['clip_name']
                    checked = st.checkbox(
                        f"**{key}**：{info['title'][:60]}",
                        key=f"chk_{key}",
                        value=st.session_state.selected_clips.get(key, False)
                    )
                    st.session_state.selected_clips[key] = checked

            with col_btn:
                st.write("")
                if st.button("🔄 刷新清單"):
                    st.rerun()

            selected_names = [name for name, sel in st.session_state.selected_clips.items() if sel]
            selected_count = len(selected_names)

            if selected_count == 0:
                st.info(f"請勾選影片後點擊打包（至少勾選 {VIDEOS_PER_PACK} 個）")
            elif selected_count < VIDEOS_PER_PACK:
                st.warning(f"只勾選了 {selected_count} 個，需要至少 {VIDEOS_PER_PACK} 個才能打包。")
            else:
                pack_names = selected_names[:VIDEOS_PER_PACK]
                if st.button(f"📦 打包選取的 {len(pack_names)} 個影片", type="primary"):
                    clip_entries = []
                    for clip_name in pack_names:
                        clip_path = PENDING_DIR / "clips" / clip_name
                        text_path = PENDING_DIR / "texts" / clip_name.replace('.mp4', '.txt')
                        thumb_path = PENDING_DIR / "thumbnails" / clip_name.replace('.mp4', '.jpg')
                        title = clip_name
                        url = ""
                        video_id = ""
                        if text_path.exists():
                            content = text_path.read_text(encoding='utf-8')
                            for line in content.splitlines():
                                if line.startswith('Title:'):
                                    title = line[6:].strip()
                                elif line.startswith('URL:'):
                                    url = line[4:].strip()
                        conn2 = sqlite3.connect(str(DB_PATH))
                        cur2 = conn2.cursor()
                        cur2.execute("SELECT video_id FROM downloaded_videos WHERE clip_name=? AND status='pending'", (clip_name,))
                        row2 = cur2.fetchone()
                        if row2:
                            video_id = row2[0]
                        conn2.close()
                        clip_entries.append({
                            'clip_name': clip_name,
                            'text_name': clip_name.replace('.mp4', '.txt'),
                            'thumbnail_name': clip_name.replace('.mp4', '.jpg') if thumb_path.exists() else None,
                            'title': title,
                            'url': url,
                            'actual_duration': 0,
                            'clip_path': str(clip_path),
                            'text_path': str(text_path),
                            'thumbnail_path': str(thumb_path) if thumb_path.exists() else None,
                            'video_id': video_id
                        })

                    first_title = clip_entries[0].get('title', 'video')
                    safe_title = re.sub(r'[\\/:*?"<>|]', '_', first_title)[:50]
                    now_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                    zip_name = f"{safe_title}_{now_str}.zip"
                    zip_path = OUTPUT_DIR / zip_name
                    zip_path = pack_clips_into_zip(clip_entries, 1, OUTPUT_DIR)

                    for entry in clip_entries:
                        Path(entry['clip_path']).unlink(missing_ok=True)
                        Path(entry['text_path']).unlink(missing_ok=True)
                        if entry.get('thumbnail_path'):
                            Path(entry['thumbnail_path']).unlink(missing_ok=True)

                    for entry in clip_entries:
                        if entry['video_id']:
                            update_status(entry['video_id'], 'zipped', zip_name)

                    for name in pack_names:
                        st.session_state.selected_clips.pop(name, None)

                    st.success(f"打包完成：{zip_name}")
                    st.rerun()

# ========== 模式二：匯入並瀏覽 ==========
if mode == "📂 匯入並瀏覽":
    st.header("📂 匯入 ZIP 包，瀏覽剪輯")

    # ----- 侧边栏：Google Drive 获取 -----
    st.sidebar.subheader("☁️ 從 Google Drive 取得")
    cfg = load_config()
    drive_id = cfg.get("drive_folder_id", "")
    if not drive_id:
        with st.sidebar.expander("設定 Google Drive 共享資料夾 ID", expanded=True):
            new_id = st.text_input("資料夾 ID", value="", key="local_drive_id")
            if st.button("儲存", key="save_drive_id"):
                if new_id.strip():
                    save_config({"drive_folder_id": new_id.strip()})
                    st.success("已儲存")
                    st.rerun()
                else:
                    st.error("請輸入 ID")
    else:
        if st.button("📋 取得檔案清單", key="fetch_drive_list"):
            with st.spinner("正在取得檔案清單..."):
                files = get_drive_file_list(drive_id)
                if not files:
                    st.warning("資料夾中沒有 .zip 檔案，或無法存取")
                else:
                    st.session_state.drive_file_list = files
                    st.session_state.drive_file_list_fetched = True
                    st.success(f"找到 {len(files)} 個 ZIP 檔案")
        if st.session_state.drive_file_list_fetched and st.session_state.drive_file_list:
            file_names = [f['name'] for f in st.session_state.drive_file_list]
            selected_name = st.sidebar.selectbox("選擇 ZIP", file_names, key="drive_zip_select")
            selected_file = next((f for f in st.session_state.drive_file_list if f['name'] == selected_name), None)
            if selected_file and st.sidebar.button("⬇️ 下載並匯入", key="drive_import"):
                try:
                    with st.spinner("正在下載..."):
                        zip_bytes = download_file_from_drive(selected_file['id'])
                    _import_zip_from_bytes(zip_bytes)
                    st.success(f"已從 Google Drive 匯入 {selected_file['name']}")
                except Exception as e:
                    st.error(f"下載/匯入失敗：{e}")

    # ----- 侧边栏：本地上传 -----
    st.sidebar.subheader("📁 本地上傳 ZIP")
    uploaded_zip = st.sidebar.file_uploader("選擇 .zip 檔案", type=["zip"], key="upload_zip")
    if uploaded_zip is not None:
        try:
            _import_zip_from_bytes(uploaded_zip.getbuffer())
            st.success(f"已匯入 {uploaded_zip.name}")
        except Exception as e:
            st.error(f"匯入失敗：{e}")

    # ----- 主区域：双行展示（含中英文标题、自适应播放器） -----
    if not st.session_state.reviews:
        st.info("請透過側邊欄上傳或從 Google Drive 匯入一個 ZIP 檔案")
    else:
        st.subheader(f"共 {len(st.session_state.reviews)} 個剪輯")
        for i, entry in enumerate(st.session_state.reviews):
            col_a, col_b = st.columns([2.5, 3.5])
            with col_a:
                raw_title = entry.get('text', '')[:80]
                translated = entry.get('translated_title', None)
                if translated:
                    display_text = f"{raw_title}\n\n中文：{translated}"
                else:
                    display_text = raw_title
                st.markdown(f"**{entry.get('index', i+1):03d}**  {display_text}")

                text_bytes = entry.get('text_bytes')
                if text_bytes:
                    st.text_area("文字內容", text_bytes.decode('utf-8', errors='ignore'), height=200)
                thumb_bytes = entry.get('thumbnail_bytes')
                if thumb_bytes and len(thumb_bytes) > 0:
                    st.image(thumb_bytes, width=150)
            with col_b:
                clip_bytes = entry.get('clip_bytes')
                if clip_bytes:
                    b64 = base64.b64encode(clip_bytes).decode()
                    ext = entry.get('clip_name', 'clip.mp4').rsplit('.', 1)[-1].lower()
                    mime = 'video/mp4' if ext == 'mp4' else f'video/{ext}'
                    uid = f"vid_{i}_{int(time.time())}"
                    html = f"""
                    <div style="display:flex; flex-direction:column; gap:6px; width:100%;">
                        <video id="{uid}" style="width:100%; height:auto; max-height:400px; object-fit:contain; background:#000;" controls>
                            <source src="data:{mime};base64,{b64}" type="{mime}">
                        </video>
                        <div style="display:flex; gap:8px; flex-wrap:wrap;">
                            <button onclick="document.getElementById('{uid}').play()" style="padding:4px 12px; border:1px solid #888; border-radius:4px; background:#f0f0f0; cursor:pointer;">▶ 播放</button>
                            <button onclick="document.getElementById('{uid}').pause()" style="padding:4px 12px; border:1px solid #888; border-radius:4px; background:#f0f0f0; cursor:pointer;">⏸ 暫停</button>
                            <button onclick="var v=document.getElementById('{uid}'); v.pause(); v.currentTime=0;" style="padding:4px 12px; border:1px solid #888; border-radius:4px; background:#f0f0f0; cursor:pointer;">⏹ 停止</button>
                            <button onclick="var v=document.getElementById('{uid}'); if(v.requestFullscreen) v.requestFullscreen();" style="padding:4px 12px; border:1px solid #888; border-radius:4px; background:#f0f0f0; cursor:pointer;">⛶ 全螢幕</button>
                        </div>
                    </div>
                    """
                    components.html(html, height=450)
                else:
                    st.warning("影片資料缺失")
            st.markdown("---")