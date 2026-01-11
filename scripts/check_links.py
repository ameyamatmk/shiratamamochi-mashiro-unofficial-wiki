#!/usr/bin/env python3
"""リンク切れ検出スクリプト

docs/ 配下のMarkdownファイルからX(Twitter)とYouTubeのリンクを抽出し、
oEmbed APIを使用してリンクの有効性をチェックする。

GitHub Actions環境では、リンク切れ検出時にIssueを自動作成/更新する。
"""

import argparse
import asyncio
import json
import os
import re
import sys
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx


@dataclass
class LinkInfo:
    """リンク情報"""

    file: str
    line: int
    url: str
    link_type: str  # "twitter" or "youtube"
    status: str = "unknown"  # "valid", "invalid", "error"
    error: str = ""


@dataclass
class CheckResult:
    """チェック結果"""

    checked_at: str = ""
    total: int = 0
    valid: int = 0
    invalid: int = 0
    error: int = 0
    links: list[LinkInfo] = field(default_factory=list)

    def to_dict(self) -> dict:
        """辞書に変換"""
        return {
            "checked_at": self.checked_at,
            "total": self.total,
            "valid": self.valid,
            "invalid": self.invalid,
            "error": self.error,
            "results": [
                {
                    "file": link.file,
                    "line": link.line,
                    "url": link.url,
                    "type": link.link_type,
                    "status": link.status,
                    "error": link.error,
                }
                for link in self.links
            ],
        }


# リンク抽出用の正規表現パターン
PATTERNS = {
    "twitter_macro": re.compile(
        r'\{\{\s*twitter\s*\(\s*["\']([^"\']+)["\']\s*\)', re.IGNORECASE
    ),
    "youtube_macro": re.compile(
        r'\{\{\s*youtube(?:_thumbnail)?\s*\(\s*["\']([^"\']+)["\']\s*\)', re.IGNORECASE
    ),
    "twitter_link": re.compile(
        r"\]\((https?://(?:twitter\.com|x\.com)/[^)]+)\)", re.IGNORECASE
    ),
    "youtube_link": re.compile(
        r"\]\((https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^)]+)\)", re.IGNORECASE
    ),
}

# YouTube VIDEO_ID抽出用
YOUTUBE_ID_PATTERNS = [
    re.compile(r"^[\w-]{11}$"),  # VIDEO_ID直接指定
    re.compile(r"[?&]v=([\w-]{11})"),  # youtube.com/watch?v=
    re.compile(r"youtu\.be/([\w-]{11})"),  # youtu.be/
    re.compile(r"embed/([\w-]{11})"),  # youtube.com/embed/
]

# チェック対象外のURLパターン
SKIP_PATTERNS = [
    # X/Twitter 検索・ハッシュタグ（oEmbed非対応）
    re.compile(r"x\.com/search\?", re.IGNORECASE),
    re.compile(r"x\.com/hashtag/", re.IGNORECASE),
    re.compile(r"twitter\.com/search\?", re.IGNORECASE),
    re.compile(r"twitter\.com/hashtag/", re.IGNORECASE),
    # YouTube チャンネル・プレイリスト（oEmbed非対応）
    re.compile(r"youtube\.com/@", re.IGNORECASE),
    re.compile(r"youtube\.com/channel/", re.IGNORECASE),
    re.compile(r"youtube\.com/playlist\?", re.IGNORECASE),
    re.compile(r"youtube\.com/c/", re.IGNORECASE),
]


def should_skip_url(url: str) -> bool:
    """チェック対象外のURLかどうか判定"""
    return any(pattern.search(url) for pattern in SKIP_PATTERNS)


def extract_youtube_video_id(video_id_or_url: str) -> str | None:
    """YouTube VIDEO_IDを抽出"""
    for pattern in YOUTUBE_ID_PATTERNS:
        match = pattern.search(video_id_or_url)
        if match:
            return match.group(1) if match.lastindex else video_id_or_url
    return None


def extract_links_from_file(file_path: Path, docs_root: Path) -> list[LinkInfo]:
    """ファイルからリンクを抽出"""
    links: list[LinkInfo] = []
    relative_path = str(file_path.relative_to(docs_root.parent))

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  警告: {file_path} の読み込みに失敗: {e}", file=sys.stderr)
        return links

    for line_num, line in enumerate(content.splitlines(), start=1):
        # Twitter マクロ
        for match in PATTERNS["twitter_macro"].finditer(line):
            url = match.group(1)
            if not should_skip_url(url):
                links.append(
                    LinkInfo(
                        file=relative_path,
                        line=line_num,
                        url=url,
                        link_type="twitter",
                    )
                )

        # YouTube マクロ
        for match in PATTERNS["youtube_macro"].finditer(line):
            video_id = extract_youtube_video_id(match.group(1))
            if video_id:
                url = f"https://www.youtube.com/watch?v={video_id}"
                if not should_skip_url(url):
                    links.append(
                        LinkInfo(
                            file=relative_path,
                            line=line_num,
                            url=url,
                            link_type="youtube",
                        )
                    )

        # Twitter リンク
        for match in PATTERNS["twitter_link"].finditer(line):
            url = match.group(1)
            if not should_skip_url(url):
                links.append(
                    LinkInfo(
                        file=relative_path,
                        line=line_num,
                        url=url,
                        link_type="twitter",
                    )
                )

        # YouTube リンク
        for match in PATTERNS["youtube_link"].finditer(line):
            url = match.group(1)
            if not should_skip_url(url):
                links.append(
                    LinkInfo(
                        file=relative_path,
                        line=line_num,
                        url=url,
                        link_type="youtube",
                    )
                )

    return links


def deduplicate_links(links: list[LinkInfo]) -> list[LinkInfo]:
    """重複するURLを除去（最初の出現を保持）"""
    seen: set[str] = set()
    unique: list[LinkInfo] = []
    for link in links:
        if link.url not in seen:
            seen.add(link.url)
            unique.append(link)
    return unique


async def check_twitter_link(client: httpx.AsyncClient, link: LinkInfo) -> None:
    """Twitter/X リンクをoEmbed APIでチェック"""
    oembed_url = "https://publish.twitter.com/oembed?" + urllib.parse.urlencode(
        {"url": link.url}
    )
    try:
        response = await client.get(oembed_url)
        if response.status_code == 200:
            link.status = "valid"
        else:
            link.status = "invalid"
            link.error = f"HTTP {response.status_code}"
    except httpx.TimeoutException:
        link.status = "error"
        link.error = "Timeout"
    except Exception as e:
        link.status = "error"
        link.error = str(e)


async def check_youtube_link(client: httpx.AsyncClient, link: LinkInfo) -> None:
    """YouTube リンクをoEmbed APIでチェック"""
    oembed_url = "https://www.youtube.com/oembed?" + urllib.parse.urlencode(
        {"url": link.url, "format": "json"}
    )
    try:
        response = await client.get(oembed_url)
        if response.status_code == 200:
            link.status = "valid"
        elif response.status_code in (401, 403, 404):
            link.status = "invalid"
            link.error = f"HTTP {response.status_code} (削除または非公開)"
        else:
            link.status = "invalid"
            link.error = f"HTTP {response.status_code}"
    except httpx.TimeoutException:
        link.status = "error"
        link.error = "Timeout"
    except Exception as e:
        link.status = "error"
        link.error = str(e)


async def check_link(
    client: httpx.AsyncClient, link: LinkInfo, semaphore: asyncio.Semaphore
) -> None:
    """リンクをチェック（セマフォでレート制限）"""
    async with semaphore:
        if link.link_type == "twitter":
            await check_twitter_link(client, link)
        elif link.link_type == "youtube":
            await check_youtube_link(client, link)

        # レート制限対策
        await asyncio.sleep(0.3)


async def check_all_links(links: list[LinkInfo]) -> None:
    """全リンクを並列チェック"""
    # 同時接続数を制限
    semaphore = asyncio.Semaphore(5)

    async with httpx.AsyncClient(timeout=10.0) as client:
        tasks = [check_link(client, link, semaphore) for link in links]
        await asyncio.gather(*tasks)


def print_summary(result: CheckResult) -> None:
    """結果サマリーを表示"""
    print("\n" + "=" * 60)
    print("リンクチェック結果")
    print("=" * 60)
    print(f"チェック日時: {result.checked_at}")
    print(f"総リンク数: {result.total}")
    print(f"  有効: {result.valid}")
    print(f"  無効: {result.invalid}")
    print(f"  エラー: {result.error}")

    if result.invalid > 0 or result.error > 0:
        print("\n問題のあるリンク:")
        print("-" * 60)
        for link in result.links:
            if link.status in ("invalid", "error"):
                print(f"  [{link.status.upper()}] {link.file}:{link.line}")
                print(f"    URL: {link.url}")
                print(f"    理由: {link.error}")
                print()


def create_issue_body(result: CheckResult, run_url: str = "") -> str:
    """GitHub Issue用の本文を生成"""
    invalid_links = [
        link for link in result.links if link.status in ("invalid", "error")
    ]

    # GitHubリポジトリ情報を取得（ファイルリンク生成用）
    github_repository = os.environ.get("GITHUB_REPOSITORY", "")
    github_server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    github_ref = os.environ.get("GITHUB_REF_NAME", "main")

    lines = [
        "## リンク切れレポート",
        "",
        f"チェック日時: {result.checked_at}",
        "",
        "| ファイル | 外部リンク | エラー |",
        "|----------|-----------|--------|",
    ]

    for link in invalid_links:
        # ファイルパスをGitHubリンクに変換
        file_path = link.file.replace("\\", "/")  # Windows対応
        if github_repository:
            file_link = f"[{file_path}:{link.line}]({github_server_url}/{github_repository}/blob/{github_ref}/{file_path}#L{link.line})"
        else:
            file_link = f"{file_path}:{link.line}"

        lines.append(f"| {file_link} | {link.url} | {link.error} |")

    lines.append("")
    lines.append("---")

    if run_url:
        lines.append(
            f"*このIssueは [GitHub Actions]({run_url}) によって自動生成されました。*"
        )
    else:
        lines.append("*このIssueは check_links.py によって自動生成されました。*")

    return "\n".join(lines)


async def create_issue(result: CheckResult) -> None:
    """GitHub Issueを作成"""
    github_token = os.environ.get("GITHUB_TOKEN")
    github_repository = os.environ.get("GITHUB_REPOSITORY")
    github_server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    github_run_id = os.environ.get("GITHUB_RUN_ID", "")

    if not github_token or not github_repository:
        print("GitHub環境変数が設定されていないため、Issue作成をスキップします。")
        return

    run_url = ""
    if github_run_id:
        run_url = (
            f"{github_server_url}/{github_repository}/actions/runs/{github_run_id}"
        )

    issue_title = f"リンク切れを検出しました ({result.checked_at[:10]})"
    issue_body = create_issue_body(result, run_url)
    label = "link-check"

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    api_base = f"https://api.github.com/repos/{github_repository}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        create_url = f"{api_base}/issues"
        response = await client.post(
            create_url,
            headers=headers,
            json={
                "title": issue_title,
                "body": issue_body,
                "labels": ["link-check"],
            },
        )
        if response.status_code == 201:
            new_issue = response.json()
            print(f"Issue #{new_issue['number']} を作成しました")
        else:
            print(f"Issue作成に失敗: HTTP {response.status_code}")
            print(response.text)


def main() -> int:
    """メイン処理"""
    parser = argparse.ArgumentParser(description="リンク切れ検出スクリプト")
    parser.add_argument(
        "--create-issue",
        action="store_true",
        help="リンク切れ検出時にGitHub Issueを作成/更新する（GITHUB_TOKEN環境変数が必要）",
    )
    args = parser.parse_args()

    # プロジェクトルートを特定
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    docs_dir = project_root / "docs"

    if not docs_dir.exists():
        print(f"エラー: docs ディレクトリが見つかりません: {docs_dir}", file=sys.stderr)
        return 1

    print("リンクチェックを開始します...")
    print(f"対象ディレクトリ: {docs_dir}")

    # Markdownファイルからリンクを抽出
    all_links: list[LinkInfo] = []
    md_files = list(docs_dir.rglob("*.md"))
    print(f"対象ファイル数: {len(md_files)}")

    for md_file in md_files:
        links = extract_links_from_file(md_file, docs_dir)
        all_links.extend(links)

    # 重複を除去
    unique_links = deduplicate_links(all_links)
    print(f"抽出したリンク数: {len(all_links)} (ユニーク: {len(unique_links)})")

    if not unique_links:
        print("チェック対象のリンクがありません。")
        return 0

    # リンクをチェック
    print("\nリンクをチェック中...")
    asyncio.run(check_all_links(unique_links))

    # 結果を集計
    result = CheckResult(
        checked_at=datetime.now(timezone.utc).isoformat(),
        total=len(unique_links),
        valid=sum(1 for link in unique_links if link.status == "valid"),
        invalid=sum(1 for link in unique_links if link.status == "invalid"),
        error=sum(1 for link in unique_links if link.status == "error"),
        links=unique_links,
    )

    # 結果を表示
    print_summary(result)

    # JSONファイルに保存
    output_file = project_root / "link-check-results.json"
    output_file.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n結果を保存しました: {output_file}")

    # GitHub Issue作成 or ローカル用にIssue body形式で表示
    if args.create_issue:
        if result.invalid > 0 or result.error > 0:
            asyncio.run(create_issue(result))
    else:
        # ローカル実行時はIssue body形式で表示（コピペ用）
        if result.invalid > 0 or result.error > 0:
            print("\n" + "=" * 60)
            print("Issue Body")
            print("=" * 60)
            print(create_issue_body(result))

    # 無効なリンクがあれば終了コード1
    if result.invalid > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
