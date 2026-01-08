// Twitter widgets.js の再読み込み処理
// - ページ遷移時（instant navigation対応）
// - 折りたたみ展開時（details要素対応）

function loadTwitterWidgets() {
  if (typeof twttr !== 'undefined' && twttr.widgets) {
    twttr.widgets.load()
  }
}

// instant navigation 対応：ページ遷移完了時に再読み込み
document.addEventListener('DOMContentLoaded', loadTwitterWidgets)

// MkDocs Material の instant navigation 対応
if (typeof document$ !== 'undefined') {
  document$.subscribe(() => {
    loadTwitterWidgets()
  })
}

// 折りたたみ展開時に再読み込み
document.addEventListener('toggle', (event) => {
  if (event.target.tagName === 'DETAILS' && event.target.open) {
    loadTwitterWidgets()
  }
}, true)
