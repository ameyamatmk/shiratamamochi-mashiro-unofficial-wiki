// 外部リンクを別タブで開く（instant loading対応）
function openExternalLinksInNewTab() {
  const links = document.querySelectorAll('a[href^="http"]')
  links.forEach(function(link) {
    // 同一ドメインでなければ別タブで開く
    if (link.hostname !== window.location.hostname) {
      link.setAttribute('target', '_blank')
      link.setAttribute('rel', 'noopener noreferrer')
    }
  })
}

// 初回ロード時
document.addEventListener('DOMContentLoaded', openExternalLinksInNewTab)

// instant loading対応（Material for MkDocs）
if (typeof document$ !== 'undefined') {
  document$.subscribe(openExternalLinksInNewTab)
}
