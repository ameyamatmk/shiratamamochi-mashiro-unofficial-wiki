// ヘッダーにホームリンクシェアアイコンを追加
function addHeaderShareIcon() {
  // 既に追加済みなら何もしない
  if (document.querySelector('.header-share-icon')) return

  // ダークモード切り替えボタンの親要素を取得
  const headerOptions = document.querySelector('.md-header__option')
  if (!headerOptions) return

  // シェアリンクを作成
  const shareUrl = encodeURIComponent(window.siteConfig?.siteUrl || window.location.origin)
  const shareText = encodeURIComponent(window.siteConfig?.siteName || document.title)
  const tweetUrl = `https://x.com/intent/tweet?url=${shareUrl}&text=${shareText}`

  // アイコンリンク要素を作成
  const shareLink = document.createElement('a')
  shareLink.href = tweetUrl
  shareLink.target = '_blank'
  shareLink.rel = 'noopener noreferrer'
  shareLink.className = 'header-share-icon'
  shareLink.title = 'Xでシェア'
  shareLink.innerHTML = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="20" height="20">
      <path d="M389.2 48h70.6L305.6 224.2 487 464H345L233.7 318.6 106.5 464H35.8L200.7 275.5 26.8 48H172.4L272.9 180.9 389.2 48zM364.4 421.8h39.1L151.1 88h-42L364.4 421.8z" fill="currentColor"/>
    </svg>
  `

  // ダークモード切り替えの前に挿入
  headerOptions.insertBefore(shareLink, headerOptions.firstChild)
}

// 初回ロード時
document.addEventListener('DOMContentLoaded', addHeaderShareIcon)

// instant loading対応（Material for MkDocs）
if (typeof document$ !== 'undefined') {
  document$.subscribe(addHeaderShareIcon)
}
