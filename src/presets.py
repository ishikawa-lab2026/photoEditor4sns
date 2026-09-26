"""SNS向けアスペクト比 & 推奨サイズプリセット定義モジュール
"""
from typing import Optional, Tuple, Dict

# クロッププリセット定義
# キー: 表示ラベル
# 値: ("ratio", (幅比率, 高さ比率)) または ("fixed", (幅px, 高さpx)) または None
CROP_PRESETS: Dict[str, Optional[Tuple[str, Tuple[int, int]]]] = {
    # --- アスペクト比指定（元画像内で最大枠を配置） ---
    "【比率】Instagram 1:1 (正方形 最大枠)": ("ratio", (1, 1)),
    "【比率】Instagram 4:5 (縦長 最大枠)": ("ratio", (4, 5)),
    "【比率】Instagram 9:16 (ストーリーズ 最大枠)": ("ratio", (9, 16)),
    "【比率】X 16:9 (標準横長 最大枠)": ("ratio", (16, 9)),
    "【比率】X 4:3 (標準 最大枠)": ("ratio", (4, 3)),
    "【比率】X 3:2 (写真標準 最大枠)": ("ratio", (3, 2)),
    "【比率】X 3:1 (ヘッダー 最大枠)": ("ratio", (3, 1)),
    # --- SNS推奨ピクセル固定枠（元画像から等倍ピクセル切り抜き） ---
    "【推奨枠】Instagram 1080 × 1080 px (正方形)": ("fixed", (1080, 1080)),
    "【推奨枠】Instagram 1080 × 1350 px (縦長4:5)": ("fixed", (1080, 1350)),
    "【推奨枠】Instagram 1080 × 1920 px (ストーリーズ)": ("fixed", (1080, 1920)),
    "【推奨枠】X 1200 × 675 px (標準16:9)": ("fixed", (1200, 675)),
    "【推奨枠】X 1500 × 500 px (ヘッダー3:1)": ("fixed", (1500, 500)),
    # --- 全体 ---
    "フリー / 元画像全体": None,
}

# 旧互換用エイリアス
RATIO_PRESETS = CROP_PRESETS

# 出力解像度（長辺上限）プリセット定義
# キー: 表示ラベル, 値: 長辺ピクセル数 または None (縮小なし)
OUTPUT_SIZE_PRESETS: Dict[str, Optional[int]] = {
    "長辺 1080px (Instagram / 標準推奨)": 1080,
    "長辺 1200px (X / Twitter 推奨)": 1200,
    "長辺 1920px (Full HD)": 1920,
    "長辺 2048px (高解像度)": 2048,
    "元解像度のまま (縮小なし)": None,
}
