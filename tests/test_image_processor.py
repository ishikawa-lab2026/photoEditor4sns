"""ImageProcessor（画像読込・枠計算・出力サイズ計算・保存）のテスト

GUI（tkinter）に依存しない画像処理ロジックのみを対象とする。
テスト画像は tmp_path 上にその場で生成するため、外部ファイルは不要。
"""
import os
from pathlib import Path

import pytest
from PIL import Image, ImageCms

from src.image_processor import PREVIEW_CACHE_LONG_EDGE, ImageProcessor

# Exif の Orientation タグID
EXIF_ORIENTATION = 0x0112


# ---------------------------------------------------------------------------
# ヘルパー / フィクスチャ
# ---------------------------------------------------------------------------

def _make_jpeg(path: Path, size=(400, 300), color=(120, 160, 200), **save_kwargs) -> Path:
    """指定サイズ・単色のJPEGを生成して保存する"""
    Image.new("RGB", size, color).save(path, format="JPEG", quality=95, **save_kwargs)
    return path


def _srgb_icc_bytes() -> bytes:
    """テスト用の sRGB ICC プロファイルのバイト列を生成する"""
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


@pytest.fixture
def processor() -> ImageProcessor:
    """未読込状態の ImageProcessor"""
    return ImageProcessor()


@pytest.fixture
def loaded(processor: ImageProcessor, tmp_path: Path):
    """任意サイズの画像を読み込んだ ImageProcessor を返すファクトリ"""
    def _factory(size=(4000, 3000)) -> ImageProcessor:
        _make_jpeg(tmp_path / f"src_{size[0]}x{size[1]}.jpg", size=size)
        processor.load_image(str(tmp_path / f"src_{size[0]}x{size[1]}.jpg"))
        return processor
    return _factory


# ---------------------------------------------------------------------------
# 読み込み
# ---------------------------------------------------------------------------

class TestLoadImage:
    def test_returns_size_and_rgb(self, processor, tmp_path):
        path = _make_jpeg(tmp_path / "a.jpg", size=(640, 480))
        assert processor.load_image(str(path)) == (640, 480)
        assert processor.original_image is not None
        assert processor.original_image.mode == "RGB"
        assert processor.filepath == str(path)

    def test_exif_orientation_is_applied(self, processor, tmp_path):
        """Orientation=6（90度回転）の画像は幅と高さが入れ替わって読み込まれる"""
        exif = Image.Exif()
        exif[EXIF_ORIENTATION] = 6
        path = _make_jpeg(tmp_path / "rot.jpg", size=(400, 200), exif=exif.tobytes())
        assert processor.load_image(str(path)) == (200, 400)

    def test_file_handle_is_released(self, processor, tmp_path):
        """読込後に元ファイルを削除できる（ファイルロックが残らない）"""
        path = _make_jpeg(tmp_path / "lock.jpg")
        processor.load_image(str(path))
        os.remove(path)
        assert not path.exists()

    def test_transparent_png_is_composited_on_white(self, processor, tmp_path):
        """透過PNGは黒ではなく白背景に合成される"""
        path = tmp_path / "alpha.png"
        Image.new("RGBA", (50, 50), (255, 0, 0, 0)).save(path)
        processor.load_image(str(path))
        assert processor.original_image.getpixel((10, 10)) == (255, 255, 255)

    def test_cmyk_is_converted_to_rgb(self, processor, tmp_path):
        path = tmp_path / "cmyk.jpg"
        Image.new("CMYK", (60, 40), (0, 0, 0, 0)).save(path, format="JPEG")
        assert processor.load_image(str(path)) == (60, 40)
        assert processor.original_image.mode == "RGB"
        # CMYK用のICCはRGB出力に不適合のため引き継がない
        assert processor.icc_profile is None

    def test_icc_profile_is_kept_for_rgb(self, processor, tmp_path):
        icc = _srgb_icc_bytes()
        path = _make_jpeg(tmp_path / "icc.jpg", icc_profile=icc)
        processor.load_image(str(path))
        assert processor.icc_profile == icc

    def test_preview_cache_is_downscaled(self, processor, tmp_path):
        path = _make_jpeg(tmp_path / "big.jpg", size=(4000, 1000))
        processor.load_image(str(path))
        assert processor.preview_base is not None
        assert max(processor.preview_base.size) == PREVIEW_CACHE_LONG_EDGE

    def test_invalid_file_raises(self, processor, tmp_path):
        path = tmp_path / "broken.jpg"
        path.write_bytes(b"not an image")
        with pytest.raises(Exception):
            processor.load_image(str(path))


# ---------------------------------------------------------------------------
# 切り抜き枠の計算
# ---------------------------------------------------------------------------

class TestCropSize:
    def test_not_loaded_returns_zero(self, processor):
        assert processor.get_crop_size_for_preset(("ratio", (1, 1))) == (0, 0)

    def test_none_preset_is_full_image(self, loaded):
        assert loaded((4000, 3000)).get_crop_size_for_preset(None) == (4000, 3000)

    @pytest.mark.parametrize(
        "size, ratio, expected",
        [
            ((4000, 3000), (1, 1), (3000, 3000)),
            ((4000, 3000), (16, 9), (4000, 2250)),
            ((4000, 3000), (4, 5), (2400, 3000)),
            ((3000, 4000), (9, 16), (2250, 4000)),
            ((4000, 3000), (3, 1), (4000, 1333)),
        ],
    )
    def test_ratio_preset_fits_max(self, loaded, size, ratio, expected):
        assert loaded(size).get_crop_size_for_preset(("ratio", ratio)) == expected

    def test_zoom_preset_uses_exact_pixels(self, loaded):
        assert loaded((6000, 4000)).get_crop_size_for_preset(("zoom", (3600, 2400))) == (3600, 2400)

    def test_zoom_preset_is_clamped_keeping_aspect(self, loaded):
        """元画像が3倍枠より小さい場合は比率を維持して収まる最大枠になる"""
        assert loaded((2000, 1500)).get_crop_size_for_preset(("zoom", (3240, 3240))) == (1500, 1500)

    def test_initial_rect_is_centered(self, loaded):
        p = loaded((4000, 3000))
        assert p.get_initial_crop_rect(("ratio", (1, 1))) == (500, 0, 3500, 3000)


class TestAdjustCropRect:
    def test_keeps_size_and_clamps_inside(self, loaded):
        p = loaded((4000, 3000))
        # はみ出した位置・丸め誤差のあるサイズを渡しても、規定サイズで画像内に収まる
        l, t, r, b = p.adjust_crop_rect_to_aspect((3500, -10, 6501, 2999), ("ratio", (1, 1)))
        assert (r - l, b - t) == (3000, 3000)
        assert (l, t) == (1000, 0)

    def test_none_preset_returns_as_is(self, loaded):
        rect = (10, 20, 110, 220)
        assert loaded().adjust_crop_rect_to_aspect(rect, None) == rect


class TestMoveCropRect:
    def test_moves_keeping_size(self, loaded):
        p = loaded((4000, 3000))
        assert p.move_crop_rect_to((500, 0, 3500, 3000), 501, 0) == (501, 0, 3501, 3000)

    @pytest.mark.parametrize(
        "left, top, expected",
        [
            (-100, -100, (0, 0, 1000, 1000)),
            (9999, 9999, (3000, 2000, 4000, 3000)),
        ],
    )
    def test_clamped_inside_image(self, loaded, left, top, expected):
        p = loaded((4000, 3000))
        assert p.move_crop_rect_to((100, 100, 1100, 1100), left, top) == expected

    def test_full_image_cannot_move(self, loaded):
        """フリー（元画像全体）の枠は移動しても元解像度のまま変わらない"""
        p = loaded((4032, 3024))
        full = p.get_initial_crop_rect(None)
        assert full == (0, 0, 4032, 3024)
        assert p.move_crop_rect_to(full, 7, 7) == full

    def test_repeated_nudge_is_exact(self, loaded):
        """1px移動を繰り返しても丸め誤差が蓄積しない"""
        p = loaded((4032, 3024))
        rect = p.get_initial_crop_rect(("ratio", (1, 1)))
        for _ in range(100):
            l, t, _, _ = rect
            rect = p.move_crop_rect_to(rect, l + 1, t)
        assert rect == (504 + 100, 0, 504 + 100 + 3024, 3024)


# ---------------------------------------------------------------------------
# 出力サイズ計算（仕様書の仕上がりサイズと一致すること）
# ---------------------------------------------------------------------------

class TestCalcOutputSize:
    @pytest.mark.parametrize(
        "crop, max_edge, expected",
        [
            ((3240, 3240), 1080, (1080, 1080)),   # Instagram 1:1
            ((3240, 4050), 1350, (1080, 1350)),   # Instagram 4:5
            ((2250, 4000), 1920, (1080, 1920)),   # Instagram 9:16
            ((3600, 2025), 1200, (1200, 675)),    # X 16:9
            ((3600, 2700), 1200, (1200, 900)),    # X 4:3
            ((3600, 2400), 1200, (1200, 800)),    # X 3:2
            ((3600, 1200), 1500, (1500, 500)),    # X 3:1
        ],
    )
    def test_spec_presets(self, crop, max_edge, expected):
        assert ImageProcessor.calc_output_size(*crop, max_edge) == expected

    def test_no_upscale_when_smaller(self):
        assert ImageProcessor.calc_output_size(800, 600, 1080) == (800, 600)

    def test_none_keeps_original(self):
        assert ImageProcessor.calc_output_size(4000, 3000, None) == (4000, 3000)

    @pytest.mark.parametrize("w, h", [(0, 100), (100, 0), (-1, 10)])
    def test_invalid_size_returns_zero(self, w, h):
        assert ImageProcessor.calc_output_size(w, h, 1080) == (0, 0)


# ---------------------------------------------------------------------------
# 色調補正
# ---------------------------------------------------------------------------

class TestAdjustments:
    def test_identity_returns_same_object(self):
        img = Image.new("RGB", (10, 10), (100, 100, 100))
        assert ImageProcessor.apply_adjustments(img) is img

    def test_zero_brightness_is_black(self):
        img = Image.new("RGB", (10, 10), (100, 150, 200))
        out = ImageProcessor.apply_adjustments(img, brightness=0.0)
        assert out.getpixel((0, 0)) == (0, 0, 0)

    def test_zero_color_is_grayscale(self):
        img = Image.new("RGB", (10, 10), (200, 50, 50))
        r, g, b = ImageProcessor.apply_adjustments(img, color=0.0).getpixel((0, 0))
        assert r == g == b


# ---------------------------------------------------------------------------
# プレビュー
# ---------------------------------------------------------------------------

class TestPreview:
    def test_not_loaded(self, processor):
        assert processor.get_preview_image() == (None, 1.0, 0, 0)

    def test_fits_into_max_size(self, loaded):
        img, scale, w, h = loaded((4000, 3000)).get_preview_image(max_size=(800, 800))
        assert (w, h) == (800, 600)
        assert img.size == (800, 600)
        assert scale == pytest.approx(0.2)

    def test_no_upscale_for_small_image(self, loaded):
        _, scale, w, h = loaded((300, 200)).get_preview_image(max_size=(800, 800))
        assert (w, h, scale) == (300, 200, 1.0)


# ---------------------------------------------------------------------------
# 保存
# ---------------------------------------------------------------------------

class TestSave:
    def test_not_loaded_raises(self, processor, tmp_path):
        with pytest.raises(ValueError):
            processor.save_cropped_image(str(tmp_path / "out.jpg"), (0, 0, 10, 10))

    def test_crop_and_resize(self, loaded, tmp_path):
        p = loaded((4000, 3000))
        out = tmp_path / "out.jpg"
        rect = p.get_initial_crop_rect(("ratio", (1, 1)))
        assert p.save_cropped_image(str(out), rect, max_long_edge=1080) == (1080, 1080)
        with Image.open(out) as saved:
            assert saved.format == "JPEG"
            assert saved.size == (1080, 1080)

    def test_original_resolution_kept_when_none(self, loaded, tmp_path):
        p = loaded((1200, 900))
        out = tmp_path / "out.jpg"
        assert p.save_cropped_image(str(out), (100, 100, 700, 500), max_long_edge=None) == (600, 400)

    def test_out_of_range_rect_is_clamped(self, loaded, tmp_path):
        p = loaded((800, 600))
        out = tmp_path / "out.jpg"
        assert p.save_cropped_image(str(out), (-50, -50, 2000, 2000), max_long_edge=None) == (800, 600)

    def test_exif_is_removed(self, processor, tmp_path):
        """GPS等を含むExifは保存結果に一切残らない"""
        exif = Image.Exif()
        exif[0x010F] = "TestCamera"  # Make
        exif[0x0132] = "2026:01:01 00:00:00"  # DateTime
        src = _make_jpeg(tmp_path / "exif.jpg", size=(400, 300), exif=exif.tobytes())
        processor.load_image(str(src))
        out = tmp_path / "out.jpg"
        processor.save_cropped_image(str(out), (0, 0, 400, 300), max_long_edge=None)
        with Image.open(out) as saved:
            assert "exif" not in saved.info
            assert len(saved.getexif()) == 0

    def test_icc_profile_is_preserved(self, processor, tmp_path):
        icc = _srgb_icc_bytes()
        src = _make_jpeg(tmp_path / "icc.jpg", icc_profile=icc)
        processor.load_image(str(src))
        out = tmp_path / "out.jpg"
        processor.save_cropped_image(str(out), (0, 0, 100, 100), max_long_edge=None)
        with Image.open(out) as saved:
            assert saved.info.get("icc_profile") == icc

    def test_no_icc_when_source_has_none(self, loaded, tmp_path):
        p = loaded((200, 200))
        out = tmp_path / "out.jpg"
        p.save_cropped_image(str(out), (0, 0, 200, 200), max_long_edge=None)
        with Image.open(out) as saved:
            assert "icc_profile" not in saved.info

    def test_lower_quality_makes_smaller_file(self, tmp_path):
        """品質設定が保存結果に反映される（ノイズ画像で比較）"""
        noise = Image.effect_noise((400, 400), 64).convert("RGB")
        src = tmp_path / "noise.png"
        noise.save(src)
        p = ImageProcessor()
        p.load_image(str(src))
        hi, lo = tmp_path / "hi.jpg", tmp_path / "lo.jpg"
        p.save_cropped_image(str(hi), (0, 0, 400, 400), quality=100, max_long_edge=None)
        p.save_cropped_image(str(lo), (0, 0, 400, 400), quality=70, max_long_edge=None)
        assert lo.stat().st_size < hi.stat().st_size
