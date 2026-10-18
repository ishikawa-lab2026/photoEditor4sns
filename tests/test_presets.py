"""SNSプリセット定義（presets.py）の整合性テスト

ラベル文字列で結び付いた3つの辞書の食い違い（typo等）を検出し、
GEMINI.md に記載された仕上がりサイズと一致することを確認する。
"""
from pathlib import Path

import pytest
from PIL import Image

from src.image_processor import ImageProcessor
from src.presets import CROP_PRESETS, OUTPUT_SIZE_PRESETS, PRESET_DEFAULT_OUTPUT_SIZE


def test_every_crop_preset_has_default_output():
    assert set(PRESET_DEFAULT_OUTPUT_SIZE) == set(CROP_PRESETS)


def test_default_outputs_exist_in_output_presets():
    for crop_key, size_key in PRESET_DEFAULT_OUTPUT_SIZE.items():
        assert size_key in OUTPUT_SIZE_PRESETS, f"{crop_key} -> {size_key}"


def test_preset_modes_are_known():
    for key, info in CROP_PRESETS.items():
        assert info is None or info[0] in ("ratio", "zoom"), key


# 6000×6000 の元画像（どの3倍枠も収まる）での最終保存サイズ（GEMINI.md 2.1 の仕様値）
@pytest.mark.parametrize(
    "preset_key, expected",
    [
        ("Instagram 1:1 (3倍枠 3240×3240)", (1080, 1080)),
        ("Instagram 4:5 (3倍枠 3240×4050)", (1080, 1350)),
        ("X (Twitter) 16:9 (3倍枠 3600×2025)", (1200, 675)),
        ("X (Twitter) 4:3 (3倍枠 3600×2700)", (1200, 900)),
        ("X (Twitter) 3:2 (3倍枠 3600×2400)", (1200, 800)),
        ("X (Twitter) 3:1 (3倍枠 3600×1200)", (1500, 500)),
        ("Instagram 1:1 (正方形・全体)", (1080, 1080)),
        ("Instagram 4:5 (縦長投稿・全体)", (1080, 1350)),
        ("Instagram 9:16 (ストーリーズ / リール)", (1080, 1920)),
    ],
)
def test_spec_output_size_for_preset(tmp_path: Path, preset_key, expected):
    src = tmp_path / "src.jpg"
    Image.new("RGB", (6000, 6000), (128, 128, 128)).save(src, format="JPEG")
    p = ImageProcessor()
    p.load_image(str(src))

    l, t, r, b = p.get_initial_crop_rect(CROP_PRESETS[preset_key])
    max_edge = OUTPUT_SIZE_PRESETS[PRESET_DEFAULT_OUTPUT_SIZE[preset_key]]
    assert ImageProcessor.calc_output_size(r - l, b - t, max_edge) == expected
