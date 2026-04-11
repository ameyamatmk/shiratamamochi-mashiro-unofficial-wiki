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


def _fallback_html(tweet_url: str, entry: dict | None = None) -> str:
    """センシティブコンテンツ等で oEmbed が使えないツイート用のカスタム HTML

    Args:
        tweet_url: ツイートの URL
        entry: キャッシュエントリ（text, date があれば表示に使う）
    """
    if entry and entry.get("text"):
        text_html = entry["text"].replace("\n", "<br>")
        date = entry.get("date", "")
        return (
            '<div class="tweet-fallback">'
            f'<a href="{tweet_url}" target="_blank"'
            ' class="tweet-fallback__overlay"></a>'
            '<div class="tweet-fallback__header">'
            '<div class="tweet-fallback__avatar">'
            '<img src="https://pbs.twimg.com/profile_images/'
            '1995874320061771776/0-Z5U3dj_normal.jpg" alt="">'
            "</div>"
            '<div class="tweet-fallback__author">'
            '<span class="tweet-fallback__name">白玉餅ましろ</span>'
            '<span class="tweet-fallback__handle">@umamochi_shiro</span>'
            "</div>"
            '<div class="tweet-fallback__logo">'
            '<svg viewBox="0 0 24 24" width="20" height="20">'
            '<path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17'
            "l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08"
            "l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"
            '"/></svg></div>'
            "</div>"
            f'<div class="tweet-fallback__text">{text_html}</div>'
            '<div class="tweet-fallback__meta">'
            f'<span class="tweet-fallback__date">{date}</span>'
            '<span class="tweet-fallback__note">'
            "※ 埋め込み表示できないポストです</span>"
            "</div>"
            "</div>"
        )
    return (
        f'<p><a href="{tweet_url}" target="_blank">'
        f"🔗 ポストを見る（X）</a>"
        f"<br><small>※ 埋め込み表示できないポストです</small></p>"
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
    def thumbnail_notice() -> str:
        """サムネイル画像の説明文

        Returns:
            サムネイル画像についての説明文（admonition付き）
        """
        return """!!! info ""
    サムネイル画像をクリックすると動画ページを開きます。  
    サムネイル画像は img.youtube.com から取得しています。"""

    @env.macro
    def youtube_thumbnail(
        video_id_or_url: str, width: int = 120, *, short: bool = False
    ) -> str:
        """YouTube サムネイル画像リンク

        Args:
            video_id_or_url: YouTube の VIDEO_ID または URL
            width: サムネイル画像の幅（デフォルト: 120）
            short: True の場合 /shorts/ リンクを生成する

        Returns:
            サムネイル画像付きリンクの Markdown
        """
        video_id = _extract_video_id(video_id_or_url)
        if short:
            url = f"https://www.youtube.com/shorts/{video_id}"
        else:
            url = f"https://www.youtube.com/watch?v={video_id}"
        thumb_url = f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
        return f"[![]({thumb_url}){{ width={width} }}]({url})"

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

        return f"""<div class="video-wrapper">
<iframe src="{src}" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
</div>"""

    # ビルド開始時に一度だけ読み込み
    cache = _load_cache()

    @env.macro
    def twitter(tweet_url: str) -> str:
        """Twitter/X 埋め込み（oEmbed API 経由、キャッシュ付き）

        Args:
            tweet_url: ツイートの URL

        Returns:
            埋め込み用 HTML（script タグは除去済み）
        """
        tweet_id = _extract_tweet_id(tweet_url)

        if tweet_id in cache:
            # フォールバックエントリはカスタム HTML で表示
            if cache[tweet_id].get("fallback"):
                return _fallback_html(tweet_url, cache[tweet_id])
            html = cache[tweet_id]["html"]
        else:
            # キャッシュになければ API を叩く
            api_url = "https://publish.twitter.com/oembed?" + urllib.parse.urlencode(
                {
                    "url": tweet_url,
                    "lang": "ja",
                }
            )
            try:
                with urllib.request.urlopen(api_url) as res:
                    data = json.loads(res.read())
            except urllib.error.HTTPError:
                # センシティブコンテンツ等で埋め込み不可の場合はリンクで表示
                return _fallback_html(tweet_url)

            cache[tweet_id] = {
                "url": tweet_url,
                "html": data["html"],
            }
            _save_cache(cache)
            html = data["html"]

        # script タグを除去（widgets.js は別途1回だけ読み込む）
        html = re.sub(
            r"<script[^>]*twitter\.com/widgets\.js[^>]*></script>",
            "",
            html,
            flags=re.IGNORECASE,
        )
        return html
