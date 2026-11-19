// docs/music/songlist.md の各テーブルの行順をチェック・整列する。
//
// 並び順: 行全体の文字列を Intl.Collator('ja')（ICU の日本語照合）で比較した昇順。
// VS Code の「行の並べ替え（昇順）」と同じ照合なので、エディタで並べた結果とも一致する。
// ICU のバージョンで順序が変わらないよう、Node のバージョンは mise.toml で固定している。
//
// 使い方:
//   node scripts/sort_songlist.ts           # チェックのみ（ずれがあれば exit 1）
//   node scripts/sort_songlist.ts --fix     # ファイルを並べ替えて書き戻す
//   node scripts/sort_songlist.ts --stdin   # 標準入力の内容をチェック（pre-commit フック用）

import { readFileSync, writeFileSync } from 'node:fs'

const FILE = 'docs/music/songlist.md'
const collator = new Intl.Collator('ja')
const MAX_REPORTED_ROWS = 20

// 照合上は同順位でも結果が一意になるよう、最後はコードポイント順で決める
const compare = (a: string, b: string): number =>
  collator.compare(a, b) || (a < b ? -1 : a > b ? 1 : 0)

const isRow = (line: string): boolean => line.startsWith('|')
const isSeparator = (line: string): boolean => /^\|\s*:?-{3,}/.test(line)

type Problem = { line: number; row: string }

// テーブル本体（ヘッダー行・区切り行を除いた行）を並べ替えた結果を返す
function sortTables(text: string): { text: string; problems: Problem[] } {
  const eol = text.includes('\r\n') ? '\r\n' : '\n'
  const lines = text.split(/\r?\n/)
  const problems: Problem[] = []

  for (let i = 0; i < lines.length; i++) {
    // ヘッダー行 + 区切り行 でテーブル開始を判定する
    if (!(isRow(lines[i]) && i + 1 < lines.length && isSeparator(lines[i + 1]))) continue

    const start = i + 2
    let end = start
    while (end < lines.length && isRow(lines[end])) end++

    const body = lines.slice(start, end)
    // 直前の行より前に来るべき行を「崩れている行」として報告する
    for (let k = 1; k < body.length; k++) {
      if (compare(body[k - 1], body[k]) > 0) problems.push({ line: start + k + 1, row: body[k] })
    }
    lines.splice(start, body.length, ...[...body].sort(compare))
    i = end - 1
  }

  return { text: lines.join(eol), problems }
}

const args = new Set(process.argv.slice(2))
const fromStdin = args.has('--stdin')
const input = readFileSync(fromStdin ? 0 : FILE, 'utf8')
const { text, problems } = sortTables(input)

if (problems.length === 0) process.exit(0)

if (args.has('--fix') && !fromStdin) {
  writeFileSync(FILE, text, 'utf8')
  console.log(`${FILE}: 並び順を整列しました（崩れていた行: ${problems.length} 行）`)
  process.exit(0)
}

console.error(`${FILE}: 並び順が崩れている行があります（${problems.length} 行）`)
for (const { line, row } of problems.slice(0, MAX_REPORTED_ROWS)) console.error(`  L${line}: ${row}`)
if (problems.length > MAX_REPORTED_ROWS) console.error(`  ...ほか ${problems.length - MAX_REPORTED_ROWS} 行`)
console.error('`node scripts/sort_songlist.ts --fix` で整列できます')
process.exit(1)
