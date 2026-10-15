"""Pillow による画像読み込み・補正・クロップ・Exif除去保存モジュール
"""
from typing import Any, Dict, Optional, Tuple
from PIL import Image, ImageOps, ImageEnhance

# プレビュー用キャッシュ画像の長辺上限px（4Kモニタでも十分な解像度）
PREVIEW_CACHE_LONG_EDGE = 2560


class ImageProcessor:
    """画像の読込・色調補正・クロップ・保存を担うクラス"""

    def __init__(self) -> None:
        self.original_image: Optional[Image.Image] = None
        # プレビュー生成用の縮小キャッシュ（毎回フル解像度から縮小しないため）
        self.preview_base: Optional[Image.Image] = None
        # 色空間情報（ICCプロファイル）。個人情報を含まないため保存時に引き継ぐ
        self.icc_profile: Optional[bytes] = None
        self.filepath: Optional[str] = None
        self.orig_w: int = 0
        self.orig_h: int = 0

    def load_image(self, filepath: str) -> Tuple[int, int]:
        """画像ファイルを読み込み、Exif向き補正を行って保持する。

        Args:
            filepath: 読み込む画像のファイルパス

        Returns:
            Tuple[int, int]: 元画像の (幅, 高さ)
        """
        # with 文でファイルハンドルを確実に解放する（MPO等でのファイルロック防止）
        with Image.open(filepath) as img:
            img.load()
            src_mode = img.mode
            # RGB系の画像のみICCプロファイルを引き継ぐ（CMYK/グレー用プロファイルはRGB出力に不適合）
            icc = img.info.get("icc_profile") if src_mode in ("RGB", "RGBA") else None
            # スマホ撮影等のExif回転情報を反映して正しい向きに補正
            transposed = ImageOps.exif_transpose(img)
            image = self._to_rgb(transposed if transposed is not None else img)

        self.filepath = filepath
        self.icc_profile = icc or None
        self.original_image = image
        self.orig_w, self.orig_h = image.size

        # プレビュー用の縮小キャッシュを一度だけ生成
        base = image.copy()
        base.thumbnail((PREVIEW_CACHE_LONG_EDGE, PREVIEW_CACHE_LONG_EDGE), Image.Resampling.LANCZOS)
        self.preview_base = base
        return self.orig_w, self.orig_h

    @staticmethod
    def _to_rgb(img: Image.Image) -> Image.Image:
        """任意モードの画像をRGBへ変換する。透過部分は白背景に合成する。

        Args:
            img: 変換対象画像

        Returns:
            Image.Image: RGB画像
        """
        has_alpha = img.mode in ("RGBA", "LA", "PA") or (
            img.mode == "P" and "transparency" in img.info
        )
        if has_alpha:
            rgba = img.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.getchannel("A"))
            return background
        if img.mode != "RGB":
            return img.convert("RGB")
        return img.copy()

    def get_crop_size_for_preset(
        self,
        preset_info: Optional[Tuple[str, Tuple[int, int]]],
    ) -> Tuple[int, int]:
        """プリセット設定（比率または推奨固定ピクセルサイズ）に基づいて、元画像内の切り抜き枠サイズを計算する。

        Args:
            preset_info: ("ratio", (幅比率, 高さ比率)) または ("fixed", (幅px, 高さpx)) または None

        Returns:
            Tuple[int, int]: (クロップ幅, クロップ高さ)
        """
        if self.original_image is None or self.orig_w == 0 or self.orig_h == 0:
            return 0, 0

        if preset_info is None:
            # フリー / 元画像全体
            return self.orig_w, self.orig_h

        mode, values = preset_info

        if mode == "zoom":
            # 3倍ズーム枠（指定ピクセルサイズ）
            target_w, target_h = values
            # 元画像の幅または高さが指定ピクセルより小さい場合は、比率を維持して元画像内に収まる最大枠へ安全クランプ
            if target_w > self.orig_w or target_h > self.orig_h:
                target_aspect = target_w / target_h
                current_aspect = self.orig_w / self.orig_h
                if current_aspect > target_aspect:
                    crop_h = self.orig_h
                    crop_w = int(round(crop_h * target_aspect))
                else:
                    crop_w = self.orig_w
                    crop_h = int(round(crop_w / target_aspect))
                crop_w = min(self.orig_w, max(1, crop_w))
                crop_h = min(self.orig_h, max(1, crop_h))
                return crop_w, crop_h
            return target_w, target_h

        elif mode == "fixed":
            # SNS推奨固定ピクセルサイズ（元画像サイズを上限にクランプ）
            target_w, target_h = values
            crop_w = min(self.orig_w, target_w)
            crop_h = min(self.orig_h, target_h)
            return crop_w, crop_h

        elif mode == "ratio":
            # アスペクト比に基づく元画像内最大サイズ
            target_w_ratio, target_h_ratio = values
            target_aspect = target_w_ratio / target_h_ratio
            current_aspect = self.orig_w / self.orig_h

            if current_aspect > target_aspect:
                crop_h = self.orig_h
                crop_w = int(round(crop_h * target_aspect))
            else:
                crop_w = self.orig_w
                crop_h = int(round(crop_w / target_aspect))

            crop_w = min(self.orig_w, max(1, crop_w))
            crop_h = min(self.orig_h, max(1, crop_h))
            return crop_w, crop_h

        return self.orig_w, self.orig_h

    def get_initial_crop_rect(
        self,
        preset_info: Optional[Tuple[str, Tuple[int, int]]],
    ) -> Tuple[int, int, int, int]:
        """指定されたプリセットで、元画像の中央に配置された初期クロップ矩形を返す。

        Args:
            preset_info: プリセット定義

        Returns:
            Tuple[int, int, int, int]: (left, top, right, bottom)
        """
        crop_w, crop_h = self.get_crop_size_for_preset(preset_info)
        left = (self.orig_w - crop_w) // 2
        top = (self.orig_h - crop_h) // 2
        right = left + crop_w
        bottom = top + crop_h
        return left, top, right, bottom

    def adjust_crop_rect_to_aspect(
        self,
        crop_rect: Tuple[int, int, int, int],
        preset_info: Optional[Tuple[str, Tuple[int, int]]],
    ) -> Tuple[int, int, int, int]:
        """指定プリセットの枠サイズ (target_w, target_h) を維持し、画面内にクランプして厳密な矩形を返す。

        Args:
            crop_rect: 元画像座標系での切り抜き矩形 (l, t, r, b)
            preset_info: プリセット情報

        Returns:
            Tuple[int, int, int, int]: 補正後の切り抜き矩形 (l, t, r, b)
        """
        if preset_info is None or self.orig_w == 0 or self.orig_h == 0:
            return crop_rect

        mode, _ = preset_info
        if mode not in ("ratio", "zoom"):
            return crop_rect

        # ターゲット比率での元画像内切り抜きサイズを取得
        target_w, target_h = self.get_crop_size_for_preset(preset_info)

        l, t, _, _ = crop_rect
        l = max(0, min(self.orig_w - target_w, l))
        t = max(0, min(self.orig_h - target_h, t))
        return l, t, l + target_w, t + target_h

    @staticmethod
    def calc_output_size(
        crop_w: int,
        crop_h: int,
        max_long_edge: Optional[int],
    ) -> Tuple[int, int]:
        """切り抜き枠サイズと長辺上限設定から、最終保存サイズ (幅, 高さ) を算出する。

        Args:
            crop_w: クロップ幅px
            crop_h: クロップ高さpx
            max_long_edge: 出力画像の長辺上限px (Noneの場合は縮小なし)

        Returns:
            Tuple[int, int]: 最終保存画像の (幅, 高さ)
        """
        if crop_w <= 0 or crop_h <= 0:
            return 0, 0
        if max_long_edge is not None and max(crop_w, crop_h) > max_long_edge:
            if crop_w >= crop_h:
                new_w = max_long_edge
                new_h = int(round(crop_h * (max_long_edge / crop_w)))
            else:
                new_h = max_long_edge
                new_w = int(round(crop_w * (max_long_edge / crop_h)))
            return new_w, new_h
        return crop_w, crop_h


    def get_preview_image(
        self,
        max_size: Tuple[int, int] = (620, 560),
        brightness: float = 1.0,
        contrast: float = 1.0,
        color: float = 1.0,
        apply_adjustments: bool = False,
    ) -> Tuple[Optional[Image.Image], float, int, int]:
        """Canvasプレビュー用の縮小画像とスケール比率を生成する。

        Args:
            max_size: プレビュー枠の最大サイズ (幅, 高さ)
            brightness: 明るさ倍率
            contrast: コントラスト倍率
            color: 彩度倍率
            apply_adjustments: 色調補正を適用するかどうか

        Returns:
            Tuple[Image, float, int, int]: (プレビュー画像, 元画像からのスケール係数, プレビュー幅, プレビュー高さ)
        """
        if self.original_image is None:
            return None, 1.0, 0, 0

        max_w, max_h = max_size
        scale = min(max_w / self.orig_w, max_h / self.orig_h, 1.0)
        prev_w = max(1, int(round(self.orig_w * scale)))
        prev_h = max(1, int(round(self.orig_h * scale)))

        # 縮小キャッシュで足りる場合はキャッシュから、足りない場合のみ元画像から縮小
        source = self.preview_base
        if source is None or prev_w > source.width or prev_h > source.height:
            source = self.original_image
        preview_img = source.resize((prev_w, prev_h), Image.Resampling.BILINEAR)

        if apply_adjustments:
            preview_img = self.apply_adjustments(preview_img, brightness, contrast, color)

        return preview_img, scale, prev_w, prev_h

    @staticmethod
    def apply_adjustments(
        img: Image.Image,
        brightness: float = 1.0,
        contrast: float = 1.0,
        color: float = 1.0,
    ) -> Image.Image:
        """Pillow の ImageEnhance を使用して明るさ・コントラスト・彩度を補正する。

        Args:
            img: 対象画像
            brightness: 明るさ倍率 (0.0〜2.0, デフォルト1.0)
            contrast: コントラスト倍率 (0.0〜2.0, デフォルト1.0)
            color: 彩度倍率 (0.0〜2.0, デフォルト1.0)

        Returns:
            Image.Image: 補正後画像
        """
        result = img
        if brightness != 1.0:
            result = ImageEnhance.Brightness(result).enhance(brightness)
        if contrast != 1.0:
            result = ImageEnhance.Contrast(result).enhance(contrast)
        if color != 1.0:
            result = ImageEnhance.Color(result).enhance(color)
        return result

    def save_cropped_image(
        self,
        output_path: str,
        crop_rect: Tuple[int, int, int, int],
        brightness: float = 1.0,
        contrast: float = 1.0,
        color: float = 1.0,
        quality: int = 90,
        max_long_edge: Optional[int] = 1080,
    ) -> Tuple[int, int]:
        """元解像度の切り抜き・色調補正・SNS向け縮小を行い、Exifを完全除去して別名保存する。

        Args:
            output_path: 出力先ファイルパス
            crop_rect: 切り抜き矩形 (left, top, right, bottom)
            brightness: 明るさ倍率
            contrast: コントラスト倍率
            color: 彩度倍率
            quality: 保存JPEG品質 (1〜100)
            max_long_edge: 出力画像の長辺上限px (Noneの場合は縮小なし)

        Returns:
            Tuple[int, int]: 最終保存画像の (幅, 高さ)
        """
        if self.original_image is None:
            raise ValueError("画像が読み込まれていません。")

        # 元画像の座標範囲に収まるようクランプ
        l, t, r, b = crop_rect
        l = max(0, min(self.orig_w - 1, l))
        t = max(0, min(self.orig_h - 1, t))
        r = max(l + 1, min(self.orig_w, r))
        b = max(t + 1, min(self.orig_h, b))

        # 1. 元解像度のまま切り抜き
        cropped = self.original_image.crop((l, t, r, b))

        # 2. 色調補正の適用
        adjusted = self.apply_adjustments(cropped, brightness, contrast, color)

        # 3. SNS向け長辺リサイズ（元サイズが上限より大きい場合のみ高品質縮小）
        #    サイズ計算はバッジ表示と共通の calc_output_size を使い、表示と結果のズレを防ぐ
        cur_w, cur_h = adjusted.size
        new_w, new_h = self.calc_output_size(cur_w, cur_h, max_long_edge)
        if (new_w, new_h) != (cur_w, cur_h):
            adjusted = adjusted.resize((new_w, new_h), Image.Resampling.LANCZOS)

        final_w, final_h = adjusted.size

        # 4. Exifメタデータを完全除去するため、新規RGBプレーン画像を作成して転送
        clean_img = Image.new("RGB", (final_w, final_h))
        clean_img.paste(adjusted)

        # 5. JPEG保存（Exifは含めず、色再現のためICCプロファイルのみ引き継ぐ）
        save_kwargs: Dict[str, Any] = {"quality": quality, "optimize": True}
        if self.icc_profile:
            save_kwargs["icc_profile"] = self.icc_profile
        clean_img.save(output_path, format="JPEG", **save_kwargs)
        return final_w, final_h
