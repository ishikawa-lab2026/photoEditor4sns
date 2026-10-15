# photoEditor4sns 改善調査レポート & 改善案

> **ステータス**: 全項目（#1〜#12）実装・テスト検証完了（46項目合格）
> 対象: [app.py](file:///c:/projects/ag/photoEditor4sns/src/app.py) / [image_processor.py](file:///c:/projects/ag/photoEditor4sns/src/image_processor.py) / [presets.py](file:///c:/projects/ag/photoEditor4sns/src/presets.py)

---

## 🔴 優先度 高（不具合・仕様とのズレ）

### 1. プレビューと保存結果が一致しない
- **症状**
  - 「適用」でプレビューに補正を反映しても、ウィンドウをリサイズしたりリセット以外で再描画したりすると補正なしのプレビューに戻る（[_on_canvas_resize](file:///c:/projects/ag/photoEditor4sns/src/app.py#L321-L325) が `apply_adjustments=False` 固定のため）。
  - スライダーを動かしただけで「適用」を押していなくても、保存時にはスライダーの値がそのまま使われる（[_on_save_image](file:///c:/projects/ag/photoEditor4sns/src/app.py#L551-L553)）。
- **改善案**
  - 「適用済みの補正値」(`self.applied_adj = (b, c, s)`) を状態として持つ。
  - 再描画と保存では、常にこの適用済みの値を使う。
  - スライダーの値と適用済みの値が違うときは、ステータスバーに「未適用の変更あり」と表示する。

### 2. 保存時に ICC プロファイルが失われ、色がくすむ
- **症状**: [save_cropped_image](file:///c:/projects/ag/photoEditor4sns/src/image_processor.py#L292-L297) で `Image.new()` から新しく画像を作るため、iPhone の Display P3 などの色空間情報も一緒に消える。SNS 上で色が薄く見える原因になる。
- **改善案**
  - 読み込み時に `img.info.get("icc_profile")` を保持しておく。
  - 保存時に `icc_profile=...` を渡す。
  - ICC プロファイルには個人情報が含まれないので、Exif を削除する方針とは矛盾しない。

### 3. 仕様にある「数値入力」が未実装
- GEMINI.md 2.1 には「スライダー**または数値入力**後、適用ボタン」とあるが、現状はスライダーのみ。
- **改善案**: 各スライダー横の値ラベルを `ttk.Spinbox`（0.01刻み）に置き換え、スライダーと値を双方向に連動させる。

---

## 🟡 優先度 中（軽量性・堅牢性）

### 4. リサイズのたびにフル解像度の画像から縮小し直している
- **症状**
  - `<Configure>` イベントはドラッグでリサイズしている間に連続して発生する。
  - そのたびに [get_preview_image](file:///c:/projects/ag/photoEditor4sns/src/image_processor.py#L177-L210) がフル解像度の元画像（例: 24MP）を縮小し直すため重い。「軽さ最優先」の方針に反する。
- **改善案**
  - 読み込み時に、プレビュー用の縮小画像（長辺 2000px 程度）を一度だけ作ってキャッシュし、以降はそこから縮小する。
  - リサイズイベントは `root.after(150, ...)` でまとめて処理する（デバウンス）。

### 5. 読み込んだ画像ファイルを閉じていない
- [load_image](file:///c:/projects/ag/photoEditor4sns/src/image_processor.py#L26) は `Image.open()` のハンドルを明示的に閉じていない。
- 複数フレームの JPEG（MPO 形式。一部のカメラが出力する）ではファイルが開いたままになり、Windows では元ファイルのロックにつながる可能性がある。
- **改善案**: `with Image.open(filepath) as img:` で読み込み、`load()` / `copy()` した画像を保持する。

### 6. 縮小計算のロジックが二重に実装されている
- [calc_output_size](file:///c:/projects/ag/photoEditor4sns/src/image_processor.py#L148-L174) と [save_cropped_image](file:///c:/projects/ag/photoEditor4sns/src/image_processor.py#L279-L288) に同じ計算がある。
- 片方だけ修正すると、バッジに表示される保存サイズと実際に保存されるサイズがずれる恐れがある。
- **改善案**: 保存処理でも `calc_output_size()` を使う。

---

## 🟢 優先度 低（UX・保守性）

| # | 内容 | 改善案 |
| :-- | :-- | :-- |
| 7 | 枠の外をクリックしても何も起きない | クリック位置へ枠の中心を移動する。矢印キーで1px単位の微調整もできるようにする |
| 8 | フォント `Helvetica` は Windows では代替フォントで表示され、日本語の表示が不揃い | `Yu Gothic UI` / `Meiryo UI` を優先して指定する |
| 9 | バッジの幅を `len(text)*7.5` で推定しているため、全角文字が枠からはみ出す | `canvas.bbox()` で実際のテキスト幅から背景矩形を描く |
| 10 | `PRESET_DEFAULT_OUTPUT_SIZE` に古いキー（例: `"Instagram 1:1 (正方形)"`）が残っている | 使われていないキーと `RATIO_PRESETS` エイリアスを整理する |
| 11 | RGBA の PNG を `convert("RGB")` すると透明部分が黒くなる | 白背景に合成してから RGB に変換する |
| 12 | テストがない | `image_processor.py` の枠計算・出力サイズ計算に pytest を追加する |

---

## 推奨する進め方
1. **第1弾（高優先 #1, #2, #6）**: 保存品質と表示の一貫性。変更は小さく、効果が大きい。
2. **第2弾（#3, #4, #5）**: 仕様の充足と軽量化。
3. **第3弾（低優先）**: 必要に応じて選んで実施。

> [!NOTE]
> いずれも外部依存の追加はありません（Pillow と tkinter のみ）。GEMINI.md の方針の範囲内です。
