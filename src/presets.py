"""SNS向けアスペクト比 & 推奨サイズプリセット定義モジュール
"""
from typing import Optional, Tuple, Dict, Any

# クロッププリセット定義
# キー: 表示ラベル
# 値: ("ratio", (幅比率, 高さ比率)) または None (全体)
CROP_PRESETS: Dict[str, Optional[Tuple[str, Tuple[int, int]]]] = {
    "Instagram 1:1 (正方形)": ("ratio", (1, 1)),
    "Instagram 4:5 (縦長投稿)": ("ratio", (4, 5)),
    "Instagram 9:16 (ストーリーズ / リール)": ("ratio", (9, 16)),
    "X (Twitter) 16:9 (標準横長)": ("ratio", (16, 9)),
    "X (Twitter) 4:3 (標準)": ("ratio", (4, 3)),
    "X (Twitter) 3:2 (写真標準)": ("ratio", (3, 2)),
    "X (Twitter) 3:1 (ヘッダー)": ("ratio", (3, 1)),
    "フリー / 元画像全体": None,
}

# 旧互換用エイリアス
RATIO_PRESETS = CROP_PRESETS

# 出力解像度（長辺上限）プリセット定義
# キー: 表示ラベル, 値: 長辺ピクセル数 または None (縮小なし)
OUTPUT_SIZE_PRESETS: Dict[str, Optional[int]] = {
    "長辺 1080px (Instagram 標準推奨)": 1080,
    "長辺 1350px (Instagram 縦長4:5 推奨)": 1350,
    "長辺 1200px (X / Twitter 推奨)": 1200,
    "長辺 1500px (X ヘッダー推奨)": 1500,
    "長辺 1920px (Full HD / ストーリーズ推奨)": 1920,
    "長辺 2048px (高解像度)": 2048,
    "元解像度のまま (縮小なし)": None,
}

# 各SNSアスペクト比に対応する推奨出力サイズ（自動連動用）
PRESET_DEFAULT_OUTPUT_SIZE: Dict[str, str] = {
    "Instagram 1:1 (正方形)": "長辺 1080px (Instagram 標準推奨)",
    "Instagram 4:5 (縦長投稿)": "長辺 1350px (Instagram 縦長4:5 推奨)",
    "Instagram 9:16 (ストーリーズ / リール)": "長辺 1920px (Full HD / ストーリーズ推奨)",
    "X (Twitter) 16:9 (標準横長)": "長辺 1200px (X / Twitter 推奨)",
    "X (Twitter) 4:3 (標準)": "長辺 1200px (X / Twitter 推奨)",
    "X (Twitter) 3:2 (写真標準)": "長辺 1200px (X / Twitter 推奨)",
    "X (Twitter) 3:1 (ヘッダー)": "長辺 1500px (X ヘッダー推奨)",
    "フリー / 元画像全体": "長辺 1920px (Full HD / ストーリーズ推奨)",
}

