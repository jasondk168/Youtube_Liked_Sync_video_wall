"""
OAuth 认证 + 获取 YouTube 点赞视频列表
"""
import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

import config as cfg

def get_authenticated_service():
    """返回已认证的 YouTube API service 对象"""
    creds = None
    if cfg.TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(cfg.TOKEN_FILE), cfg.SCOPES)
        except Exception:
            pass
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not cfg.CLIENT_SECRET_FILE.exists():
                raise FileNotFoundError(
                    f"缺少 client_secret.json，请将 OAuth 凭据文件放在 {cfg.CLIENT_SECRET_FILE}")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(cfg.CLIENT_SECRET_FILE), cfg.SCOPES)
            creds = flow.run_local_server(port=0)
        cfg.TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(str(cfg.TOKEN_FILE), "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return build(cfg.API_SERVICE_NAME, cfg.API_VERSION, credentials=creds)

def get_liked_videos(youtube, max_results=0):
    """
    获取已点赞的视频列表
    返回 list[dict]，每个 dict 包含：video_id, title, url, description, channel_title, published_at
    """
    channels = youtube.channels().list(part="contentDetails", mine=True).execute()
    if not channels.get("items"):
        raise Exception("无法获取用户频道信息，请确认 OAuth 授权范围包含 youtube.readonly")
    likes_playlist_id = channels["items"][0]["contentDetails"]["relatedPlaylists"]["likes"]

    videos = []
    next_page = None
    total = 0
    while True:
        params = {
            "part": "snippet",
            "playlistId": likes_playlist_id,
            "maxResults": min(50, max_results - total) if max_results > 0 else 50
        }
        if next_page:
            params["pageToken"] = next_page
        response = youtube.playlistItems().list(**params).execute()
        for item in response.get("items", []):
            snippet = item["snippet"]
            video_id = snippet["resourceId"]["videoId"]
            videos.append({
                "video_id": video_id,
                "title": snippet.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "description": snippet.get("description", ""),
                "channel_title": snippet.get("channelTitle", ""),
                "published_at": snippet.get("publishedAt", ""),
            })
        total = len(videos)
        next_page = response.get("nextPageToken")
        if max_results > 0 and total >= max_results:
            break
        if not next_page:
            break
    return videos