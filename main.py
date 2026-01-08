"""MkDocs マクロ定義

YouTube や X(Twitter) の埋め込みを簡単に記述するためのマクロを提供する。
"""

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

CACHE_FILE = Path("twitter_embeds.json")


def _load_cache() -> dict:
    """Twitter埋め込みキャッシュを読み込む"""
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache: dict) -> None:
    """Twitter埋め込みキャッシュを保存する"""
    CACHE_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _extract_tweet_id(url: str) -> str:
    """URL からツイート ID を抽出"""
    match = re.search(r"/status/(\d+)", url)
    if match:
        return match.group(1)
    raise ValueError(f"Invalid tweet URL: {url}")


def _extract_video_id(video_id_or_url: str) -> str:
    """VIDEO_ID または URL から VIDEO_ID を抽出"""
    # すでに VIDEO_ID の場合（11文字の英数字・ハイフン・アンダースコア）
    if re.match(r"^[\w-]{11}$", video_id_or_url):
        return video_id_or_url

    # youtube.com/watch?v=VIDEO_ID
    match = re.search(r"[?&]v=([\w-]{11})", video_id_or_url)
    if match:
        return match.group(1)

    # youtu.be/VIDEO_ID
    match = re.search(r"youtu\.be/([\w-]{11})", video_id_or_url)
    if match:
        return match.group(1)

    # youtube.com/embed/VIDEO_ID
    match = re.search(r"embed/([\w-]{11})", video_id_or_url)
    if match:
        return match.group(1)

    raise ValueError(f"Invalid YouTube video ID or URL: {video_id_or_url}")


def define_env(env):
    """MkDocs マクロを定義する"""

    @env.macro
    def youtube(video_id_or_url: str, start: int = 0) -> str:
        """YouTube 埋め込み（VIDEO_ID または URL を指定可能）

        Args:
            video_id_or_url: YouTube の VIDEO_ID または URL
            start: 開始位置（秒）

        Returns:
            埋め込み用 HTML
        """
        video_id = _extract_video_id(video_id_or_url)
        src = f"https://www.youtube.com/embed/{video_id}"
        params = []
        if start > 0:
            params.append(f"start={start}")
        if params:
            src += "?" + "&".join(params)

        return f'''<div class="video-wrapper">
<iframe src="{src}" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
</div>'''

    # ビルド開始時に一度だけ読み込み
    cache = _load_cache()

    @env.macro
    def twitter(tweet_url: str) -> str:
        """Twitter/X 埋め込み（oEmbed API 経由、キャッシュ付き）

        Args:
            tweet_url: ツイートの URL

        Returns:
            埋め込み用 HTML
        """
        tweet_id = _extract_tweet_id(tweet_url)

        if tweet_id in cache:
            return cache[tweet_id]["html"]

        # キャッシュになければ API を叩く
        api_url = "https://publish.twitter.com/oembed?" + urllib.parse.urlencode({
            "url": tweet_url,
            "lang": "ja",
        })
        with urllib.request.urlopen(api_url) as res:
            data = json.loads(res.read())

        cache[tweet_id] = {
            "url": tweet_url,
            "html": data["html"],
        }
        _save_cache(cache)

        return data["html"]
