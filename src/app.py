"""Tkinter / ttk による photoEditor4sns メインGUIアプリケーション
"""
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font as tkfont
from typing import Optional, Tuple
from PIL import ImageTk

from .presets import CROP_PRESETS, OUTPUT_SIZE_PRESETS, PRESET_DEFAULT_OUTPUT_SIZE
from .image_processor import ImageProcessor

# 日本語表示に適したUIフォントの優先順位（先頭から利用可能なものを採用）
UI_FONT_CANDIDATES = ("Yu Gothic UI", "Meiryo UI", "Segoe UI")

# リサイズ完了とみなすまでの待機時間（ミリ秒）
RESIZE_DEBOUNCE_MS = 150


class PhotoEditorApp:
    """photoEditor4sns メインGUIクラス"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("photoEditor4sns - SNS向け写真簡単編集・最適化ツール")
        self.root.geometry("1400x900")
        self.root.minsize(1000, 700)

        self.processor = ImageProcessor()

        # プレビュー管理変数
        self.preview_tk_image: Optional[ImageTk.PhotoImage] = None
        self.preview_scale: float = 1.0
        self.prev_w: int = 0
        self.prev_h: int = 0
        self.img_offset_x: int = 0
        self.img_offset_y: int = 0

        # クロップ枠（プレビュー画像内の座標: px）
        # (left, top, right, bottom)
        self.crop_box: Optional[Tuple[float, float, float, float]] = None

        # ドラッグ移動管理
        self.drag_start_x: float = 0.0
        self.drag_start_y: float = 0.0
        self.drag_box_orig: Optional[Tuple[float, float, float, float]] = None
        self.is_dragging: bool = False

        # プレビューに適用済みの補正値 (明るさ, コントラスト, 彩度: -1.00〜1.00, 基準 0.00)
        # 再描画・保存は常にこの値を使い、プレビューと保存結果を一致させる
        self.applied_adj: Tuple[float, float, float] = (0.0, 0.0, 0.0)

        # リサイズ再描画のデバウンス用ジョブID
        self._resize_job: Optional[str] = None

        # 日本語表示向けUIフォントの選択
        self.ui_font = self._pick_ui_font()

        # スタイルの設定
        self._setup_style()

        # UIコンポーネントの構築
        self._create_widgets()

    @staticmethod
    def _ui_to_factor(val: float) -> float:
        """UI上の補正値 (-1.00〜1.00, 基準 0.00) を Pillow ImageEnhance の倍率 (0.00〜2.00, 基準 1.00) に変換"""
        return max(0.0, min(2.0, 1.0 + val))

    def _pick_ui_font(self) -> str:
        """利用可能な日本語向けUIフォント名を返す（見つからなければTk標準）"""
        families = set(tkfont.families(self.root))
        for name in UI_FONT_CANDIDATES:
            if name in families:
                return name
        return "TkDefaultFont"

    def _setup_style(self) -> None:
        """ttk ウィジェットの共通スタイル設定"""
        self.style = ttk.Style()
        # 利用可能なテーマから 'clam' またはシステム標準を選択
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        f = self.ui_font
        self.style.configure(".", font=(f, 9))
        self.style.configure("Header.TLabel", font=(f, 11, "bold"))
        self.style.configure("Status.TLabel", font=(f, 9))
        self.style.configure("Pending.TLabel", font=(f, 9, "bold"), foreground="#d97706")
        self.style.configure("Action.TButton", font=(f, 10, "bold"))
        self.style.configure("Primary.TButton", font=(f, 11, "bold"))

    def _create_widgets(self) -> None:
        """GUI ウィジェット全体の配置"""
        # 1. 上部ツールバー
        top_bar = ttk.Frame(self.root, padding=(10, 8))
        top_bar.pack(side=tk.TOP, fill=tk.X)

        self.btn_open = ttk.Button(top_bar, text="📁 画像を開く (JPEG)", command=self._on_open_image)
        self.btn_open.pack(side=tk.LEFT, padx=(0, 10))

        self.lbl_file_info = ttk.Label(top_bar, text="画像が選択されていません", font=(self.ui_font, 10))
        self.lbl_file_info.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_orig_size = ttk.Label(top_bar, text="", font=(self.ui_font, 9))
        self.lbl_orig_size.pack(side=tk.RIGHT, padx=5)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(side=tk.TOP, fill=tk.X)

        # 2. 下部ステータスバー
        self.status_bar = ttk.Frame(self.root, padding=(10, 4), relief=tk.SUNKEN)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.lbl_status = ttk.Label(self.status_bar, text="準備完了 - 「画像を開く」ボタンから写真を読み込んでください。", style="Status.TLabel")
        self.lbl_status.pack(side=tk.LEFT)

        # 未適用の補正値があることを示すインジケータ
        self.lbl_pending = ttk.Label(self.status_bar, text="", style="Pending.TLabel")
        self.lbl_pending.pack(side=tk.RIGHT)

        # 3. メイン作業領域（左右分割）
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 左ペイン: プレビュー Canvas 領域
        canvas_frame = ttk.Frame(main_pane, relief=tk.SUNKEN, borderwidth=1)
        main_pane.add(canvas_frame, weight=3)

        self.canvas = tk.Canvas(canvas_frame, bg="#2b2b2b", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_drag_end)
        # 矢印キーで切り抜き枠を微調整（通常: 元画像1px / Shift併用: 10px）
        for key, (dx, dy) in {"Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1)}.items():
            self.canvas.bind(f"<{key}>", lambda e, dx=dx, dy=dy: self._on_nudge_crop(dx, dy))
            self.canvas.bind(f"<Shift-{key}>", lambda e, dx=dx, dy=dy: self._on_nudge_crop(dx * 10, dy * 10))

        # 右ペイン: 操作サイドバー
        sidebar = ttk.Frame(main_pane, padding=(12, 6))
        main_pane.add(sidebar, weight=1)

        # (1) アスペクト比・クロップ選択
        lbl_ratio = ttk.Label(sidebar, text="【1】SNS アスペクト比", style="Header.TLabel")
        lbl_ratio.pack(anchor=tk.W, pady=(0, 4))

        self.combo_ratio = ttk.Combobox(sidebar, values=list(CROP_PRESETS.keys()), state="readonly", font=(self.ui_font, 9))
        self.combo_ratio.current(0)  # Instagram 1:1
        self.combo_ratio.pack(fill=tk.X, pady=(0, 12))
        self.combo_ratio.bind("<<ComboboxSelected>>", self._on_ratio_changed)

        ttk.Separator(sidebar, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # (2) 簡易画像調整 (Image Adjustments)
        lbl_adj = ttk.Label(sidebar, text="【2】画質・色調補正", style="Header.TLabel")
        lbl_adj.pack(anchor=tk.W, pady=(4, 4))

        # 明るさ / コントラスト / 彩度（スライダー＋数値入力: 範囲 -1.0 〜 1.0、初期値 0.00）
        self.scale_bright, self.spin_bright, self.var_bright = self._create_adjust_row(
            sidebar, "明るさ (Brightness):", -1.0, 1.0, pady_bottom=6
        )
        self.scale_contrast, self.spin_contrast, self.var_contrast = self._create_adjust_row(
            sidebar, "コントラスト (Contrast):", -1.0, 1.0, pady_bottom=6
        )
        self.scale_color, self.spin_color, self.var_color = self._create_adjust_row(
            sidebar, "彩度 (Color/Saturation):", -1.0, 1.0, pady_bottom=10
        )

        # ボタン群（適用 / リセット）
        btn_frame = ttk.Frame(sidebar)
        btn_frame.pack(fill=tk.X, pady=(0, 12))

        self.btn_apply = ttk.Button(btn_frame, text="✨ 適用 (Preview更新)", command=self._on_apply_adjustments, style="Action.TButton")
        self.btn_apply.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.btn_reset = ttk.Button(btn_frame, text="↺ リセット", command=self._on_reset_adjustments)
        self.btn_reset.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(4, 0))

        ttk.Separator(sidebar, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # (3) 保存セクション
        lbl_save = ttk.Label(sidebar, text="【3】保存設定 (Exif自動削除)", style="Header.TLabel")
        lbl_save.pack(anchor=tk.W, pady=(4, 4))

        # 出力解像度（長辺上限）
        ttk.Label(sidebar, text="出力サイズ (長辺上限):").pack(anchor=tk.W, pady=(2, 2))
        self.combo_size = ttk.Combobox(sidebar, values=list(OUTPUT_SIZE_PRESETS.keys()), state="readonly", font=(self.ui_font, 9))
        self.combo_size.current(0)  # 長辺 1080px (Instagram 標準推奨)
        self.combo_size.pack(fill=tk.X, pady=(0, 8))
        self.combo_size.bind("<<ComboboxSelected>>", self._on_size_changed)

        f_q = ttk.Frame(sidebar)
        f_q.pack(fill=tk.X, pady=2)
        ttk.Label(f_q, text="保存品質 (Quality):").pack(side=tk.LEFT)
        self.lbl_val_quality = ttk.Label(f_q, text="90", width=4, anchor=tk.E)
        self.lbl_val_quality.pack(side=tk.RIGHT)
        self.scale_quality = ttk.Scale(sidebar, from_=70, to=100, value=90, command=lambda v: self.lbl_val_quality.config(text=f"{int(float(v))}"))
        self.scale_quality.pack(fill=tk.X, pady=(0, 16))

        self.btn_save = ttk.Button(sidebar, text="💾 別名で保存 (Exif削除・最適化)", command=self._on_save_image, style="Primary.TButton")
        self.btn_save.pack(fill=tk.X, ipady=6)

        # 初期状態では操作系を無効化
        self._set_controls_state(tk.DISABLED)

    def _set_controls_state(self, state: str) -> None:
        """画像未読み込み時のコントロール有効/無効化"""
        self.combo_ratio.config(state="readonly" if state == tk.NORMAL else tk.DISABLED)
        self.combo_size.config(state="readonly" if state == tk.NORMAL else tk.DISABLED)
        self.scale_bright.config(state=state)
        self.scale_contrast.config(state=state)
        self.scale_color.config(state=state)
        self.spin_bright.config(state=state)
        self.spin_contrast.config(state=state)
        self.spin_color.config(state=state)
        self.scale_quality.config(state=state)
        self.btn_apply.config(state=state)
        self.btn_reset.config(state=state)
        self.btn_save.config(state=state)

    def _create_adjust_row(
        self,
        parent: ttk.Frame,
        label_text: str,
        from_: float,
        to: float,
        pady_bottom: int,
    ) -> Tuple[ttk.Scale, ttk.Spinbox, tk.StringVar]:
        """補正項目1行分（ラベル・数値入力Spinbox・スライダー）を生成し、双方向に連動させる。

        Args:
            parent: 配置先フレーム
            label_text: 項目ラベル
            from_: 最小値
            to: 最大値
            pady_bottom: スライダー下側の余白

        Returns:
            Tuple[ttk.Scale, ttk.Spinbox, tk.StringVar]: (スライダー, Spinbox, 表示値変数)
        """
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=label_text).pack(side=tk.LEFT)

        var = tk.StringVar(value="0.00")
        spin = ttk.Spinbox(
            row, from_=from_, to=to, increment=0.01, width=6,
            textvariable=var, format="%.2f", font=(self.ui_font, 9),
        )
        spin.pack(side=tk.RIGHT)

        scale = ttk.Scale(
            parent, from_=from_, to=to, value=0.0,
            command=lambda v: self._on_slider_moved(var, v),
        )
        scale.pack(fill=tk.X, pady=(0, pady_bottom))

        def commit(_event=None) -> None:
            self._on_spin_commit(var, scale, from_, to)

        spin.config(command=commit)
        spin.bind("<Return>", commit)
        spin.bind("<FocusOut>", commit)
        return scale, spin, var

    def _on_slider_moved(self, var: tk.StringVar, val_str: str) -> None:
        """スライダー操作時: 数値欄へ反映し、未適用表示を更新"""
        try:
            var.set(f"{float(val_str):.2f}")
        except ValueError:
            return
        self._update_pending_indicator()

    def _on_spin_commit(self, var: tk.StringVar, scale: ttk.Scale, from_: float, to: float) -> None:
        """数値入力確定時: 範囲内に丸めてスライダーへ反映（不正値は元に戻す）"""
        try:
            val = float(var.get())
        except ValueError:
            var.set(f"{float(scale.get()):.2f}")
            return
        val = max(from_, min(to, val))
        scale.set(val)
        var.set(f"{val:.2f}")
        self._update_pending_indicator()

    def _current_adj(self) -> Tuple[float, float, float]:
        """現在のスライダー値 (明るさ, コントラスト, 彩度) を小数2桁で返す"""
        return (
            round(float(self.scale_bright.get()), 2),
            round(float(self.scale_contrast.get()), 2),
            round(float(self.scale_color.get()), 2),
        )

    def _has_pending_adj(self) -> bool:
        """プレビュー未適用の補正値があるか"""
        return self._current_adj() != self.applied_adj

    def _update_pending_indicator(self) -> None:
        """未適用の補正値がある場合にステータスバーへ表示"""
        if self.processor.original_image is not None and self._has_pending_adj():
            self.lbl_pending.config(text="● 未適用の補正あり（「適用」で反映）")
        else:
            self.lbl_pending.config(text="")

    def _on_open_image(self) -> None:
        """ファイル選択ダイアログからJPEG画像を開く"""
        filetypes = [
            ("JPEG画像", "*.jpg *.jpeg *.JPG *.JPEG"),
            ("すべての画像", "*.jpg *.jpeg *.png *.webp *.bmp"),
        ]
        filepath = filedialog.askopenfilename(title="編集する写真を選択", filetypes=filetypes)
        if not filepath:
            return

        try:
            orig_w, orig_h = self.processor.load_image(filepath)
            filename = os.path.basename(filepath)
            self.lbl_file_info.config(text=f"📂 {filename}")
            self.lbl_orig_size.config(text=f"元解像度: {orig_w} × {orig_h} px")
            self._set_controls_state(tk.NORMAL)

            # リセットして初期中央枠配置
            self._reset_all_params()
            self.lbl_status.config(text=f"「{filename}」を読み込みました。比率選択やドラッグで位置を合わせてください。")
        except Exception as e:
            messagebox.showerror("エラー", f"画像の読み込みに失敗しました:\n{e}")

    def _reset_all_params(self) -> None:
        """補正スライダー、クロップ枠、出力サイズ設定を初期値にリセット"""
        self.applied_adj = (0.0, 0.0, 0.0)
        for scale, var in (
            (self.scale_bright, self.var_bright),
            (self.scale_contrast, self.var_contrast),
            (self.scale_color, self.var_color),
        ):
            scale.set(0.0)
            var.set("0.00")
        self._update_pending_indicator()

        # 現在選択中のSNS比率に応じた推奨出力サイズに初期化
        preset_name = self.combo_ratio.get()
        default_size_key = PRESET_DEFAULT_OUTPUT_SIZE.get(preset_name, list(OUTPUT_SIZE_PRESETS.keys())[0])
        self.combo_size.set(default_size_key)

        # クロップ枠を破棄し、描画時（新しいプレビュースケール確定後）に中央へ再配置させる
        self.crop_box = None
        self._render_canvas()
        self._update_status_size()

    def _recalc_initial_crop_box(self) -> None:
        """現在の選択プリセットに基づいてプレビュー内の中央クロップ枠を計算"""
        if self.processor.original_image is None or self.prev_w == 0 or self.prev_h == 0:
            return

        preset_key = self.combo_ratio.get()
        preset_info = CROP_PRESETS.get(preset_key, None)

        if preset_info is None:
            # フリー / 元画像全体: プレビュー画像全体
            self.crop_box = (0.0, 0.0, float(self.prev_w), float(self.prev_h))
        else:
            orig_crop_w, orig_crop_h = self.processor.get_crop_size_for_preset(preset_info)
            # 元画像のクロップサイズをプレビュー座標系にスケール変換
            # （プレビュー寸法は整数丸めされるため、枠がはみ出さないよう上限をかける）
            prev_box_w = min(orig_crop_w * self.preview_scale, float(self.prev_w))
            prev_box_h = min(orig_crop_h * self.preview_scale, float(self.prev_h))

            left = (self.prev_w - prev_box_w) / 2.0
            top = (self.prev_h - prev_box_h) / 2.0
            self.crop_box = (left, top, left + prev_box_w, top + prev_box_h)

    def _on_ratio_changed(self, event=None) -> None:
        """クロッププリセットコンボボックス変更時の処理（出力サイズを自動連動）"""
        if self.processor.original_image is None:
            return

        preset_name = self.combo_ratio.get()

        # SNS比率に対応する推奨出力サイズに自動連動
        default_size_key = PRESET_DEFAULT_OUTPUT_SIZE.get(preset_name)
        if default_size_key and default_size_key in OUTPUT_SIZE_PRESETS:
            self.combo_size.set(default_size_key)

        self._recalc_initial_crop_box()
        self._draw_overlay()
        self._update_status_size()

    def _on_size_changed(self, event=None) -> None:
        """出力サイズコンボボックス手動変更時の処理"""
        if self.processor.original_image is not None:
            self._draw_overlay()
            self._update_status_size()

    def _update_status_size(self) -> None:
        """現在の切り抜きサイズと最終保存サイズをステータスバーに反映"""
        if self.processor.original_image is None or self.crop_box is None or self.preview_scale <= 0:
            return
        cl, ct, cr, cb = self.crop_box
        orig_w = int(round((cr - cl) / self.preview_scale))
        orig_h = int(round((cb - ct) / self.preview_scale))

        preset_name = self.combo_ratio.get()
        preset_info = CROP_PRESETS.get(preset_name)
        l, t, r, b = self.processor.adjust_crop_rect_to_aspect((0, 0, orig_w, orig_h), preset_info)
        cw, ch = r - l, b - t

        size_key = self.combo_size.get()
        max_edge = OUTPUT_SIZE_PRESETS.get(size_key)
        out_w, out_h = self.processor.calc_output_size(cw, ch, max_edge)

        self.lbl_status.config(
            text=f"【{preset_name}】 構図: {cw}×{ch} px ➡ 最終保存サイズ: {out_w}×{out_h} px ({size_key})"
        )

    def _on_apply_adjustments(self) -> None:
        """「適用」ボタン押下時: 現在の補正値を確定してプレビューに反映"""
        if self.processor.original_image is None:
            return
        self.applied_adj = self._current_adj()
        self._render_canvas()
        self._update_pending_indicator()
        self.lbl_status.config(text="色調補正をプレビューに反映しました。")

    def _on_reset_adjustments(self) -> None:
        """「リセット」ボタン押下時: 補正値とクロップ位置を初期化"""
        if self.processor.original_image is None:
            return
        self._reset_all_params()
        self.lbl_status.config(text="補正値とクロップ枠を初期状態に戻しました。")

    def _on_canvas_resize(self, event) -> None:
        """ウィンドウ・Canvasリサイズ時: 連続イベントをまとめ、落ち着いてから再描画（デバウンス）"""
        if self.processor.original_image is None:
            return
        if self._resize_job is not None:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(RESIZE_DEBOUNCE_MS, self._on_resize_settled)

    def _on_resize_settled(self) -> None:
        """リサイズ完了後の再描画"""
        self._resize_job = None
        self._render_canvas()

    def _render_canvas(self) -> None:
        """プレビュー画像（適用済み補正値を反映）とオーバーレイをCanvasに描画"""
        if self.processor.original_image is None:
            return

        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w <= 10 or canvas_h <= 10:
            return

        # プレビュー領域マージン
        max_pw = max(50, canvas_w - 20)
        max_ph = max(50, canvas_h - 20)

        # 既存クロップ枠の正規化比率を保存（リサイズ追従用）
        norm_box = None
        if self.crop_box is not None and self.prev_w > 0 and self.prev_h > 0:
            l, t, r, b = self.crop_box
            norm_box = (l / self.prev_w, t / self.prev_h, r / self.prev_w, b / self.prev_h)

        bright_ui, contrast_ui, color_ui = self.applied_adj

        prev_img, scale, pw, ph = self.processor.get_preview_image(
            max_size=(max_pw, max_ph),
            brightness=self._ui_to_factor(bright_ui),
            contrast=self._ui_to_factor(contrast_ui),
            color=self._ui_to_factor(color_ui),
            apply_adjustments=True,
        )
        if prev_img is None:
            return

        self.preview_scale = scale
        self.prev_w = pw
        self.prev_h = ph
        self.img_offset_x = (canvas_w - pw) // 2
        self.img_offset_y = (canvas_h - ph) // 2

        self.preview_tk_image = ImageTk.PhotoImage(prev_img)

        # クロップ枠のスケール再設定
        if norm_box is not None:
            nl, nt, nr, nb = norm_box
            self.crop_box = (nl * pw, nt * ph, nr * pw, nb * ph)
        else:
            self._recalc_initial_crop_box()

        # Canvas要素の描画
        self.canvas.delete("all")
        self.canvas.create_image(
            self.img_offset_x, self.img_offset_y,
            image=self.preview_tk_image,
            anchor=tk.NW,
            tags="preview_img",
        )
        self._draw_overlay()

    def _draw_overlay(self) -> None:
        """クロップ枠、3分割構図線、枠外シャドウのCanvas描画"""
        self.canvas.delete("crop_overlay")
        if self.crop_box is None or self.prev_w == 0 or self.prev_h == 0:
            return

        cl, ct, cr, cb = self.crop_box
        ox = self.img_offset_x
        oy = self.img_offset_y

        # 枠のCanvas上座標
        x1 = ox + cl
        y1 = oy + ct
        x2 = ox + cr
        y2 = oy + cb

        # 1. 枠外の視覚的強調（枠外4方向の暗転矩形）
        img_x1 = ox
        img_y1 = oy
        img_x2 = ox + self.prev_w
        img_y2 = oy + self.prev_h

        # 上
        if y1 > img_y1:
            self.canvas.create_rectangle(img_x1, img_y1, img_x2, y1, fill="#000000", stipple="gray50", outline="", tags="crop_overlay")
        # 下
        if y2 < img_y2:
            self.canvas.create_rectangle(img_x1, y2, img_x2, img_y2, fill="#000000", stipple="gray50", outline="", tags="crop_overlay")
        # 左
        if x1 > img_x1:
            self.canvas.create_rectangle(img_x1, max(img_y1, y1), x1, min(img_y2, y2), fill="#000000", stipple="gray50", outline="", tags="crop_overlay")
        # 右
        if x2 < img_x2:
            self.canvas.create_rectangle(x2, max(img_y1, y1), img_x2, min(img_y2, y2), fill="#000000", stipple="gray50", outline="", tags="crop_overlay")

        # 2. 3分割グリッド構図線（三分割法）
        w = x2 - x1
        h = y2 - y1
        if w > 20 and h > 20:
            # 縦2本
            self.canvas.create_line(x1 + w / 3.0, y1, x1 + w / 3.0, y2, fill="#ffffff", dash=(2, 2), tags="crop_overlay")
            self.canvas.create_line(x1 + 2.0 * w / 3.0, y1, x1 + 2.0 * w / 3.0, y2, fill="#ffffff", dash=(2, 2), tags="crop_overlay")
            # 横2本
            self.canvas.create_line(x1, y1 + h / 3.0, x2, y1 + h / 3.0, fill="#ffffff", dash=(2, 2), tags="crop_overlay")
            self.canvas.create_line(x1, y1 + 2.0 * h / 3.0, x2, y1 + 2.0 * h / 3.0, fill="#ffffff", dash=(2, 2), tags="crop_overlay")

        # 3. クロップ外枠線
        self.canvas.create_rectangle(x1, y1, x2, y2, outline="#00ffcc", width=2, tags="crop_overlay")

        # 4. クロップ枠の元画像実サイズと最終保存サイズバッジ表示
        if self.preview_scale > 0:
            actual_w = int(round((cr - cl) / self.preview_scale))
            actual_h = int(round((cb - ct) / self.preview_scale))

            # アスペクト比厳密補正
            preset_name = self.combo_ratio.get()
            preset_info = CROP_PRESETS.get(preset_name)
            _, _, adj_w, adj_h = self.processor.adjust_crop_rect_to_aspect((0, 0, actual_w, actual_h), preset_info)

            # 最終出力サイズの算出
            size_key = self.combo_size.get()
            max_edge = OUTPUT_SIZE_PRESETS.get(size_key)
            out_w, out_h = self.processor.calc_output_size(adj_w, adj_h, max_edge)

            if adj_w == out_w and adj_h == out_h:
                size_text = f"{out_w} × {out_h} px"
            else:
                size_text = f"構図: {adj_w}×{adj_h} px ➡ 保存: {out_w}×{out_h} px"

            # 枠上部または枠内にバッジ表示（テキストの実寸から背景矩形を描画）
            tag_y = y1 - 12 if y1 >= 24 else y1 + 14
            text_id = self.canvas.create_text(
                x1 + 8, tag_y, text=size_text, fill="#00ffcc",
                anchor=tk.W, font=(self.ui_font, 9, "bold"), tags="crop_overlay"
            )
            bbox = self.canvas.bbox(text_id)
            if bbox is not None:
                bx1, by1, bx2, by2 = bbox
                rect_id = self.canvas.create_rectangle(
                    bx1 - 6, by1 - 2, bx2 + 6, by2 + 2,
                    fill="#1e1e1e", outline="#00ffcc", width=1, tags="crop_overlay"
                )
                self.canvas.tag_lower(rect_id, text_id)

    # --- ドラッグによるクロップ枠移動イベント ---

    def _on_drag_start(self, event) -> None:
        """マウスクリック時: ドラッグ開始（枠外クリック時はその位置へ枠の中心を移動）"""
        # 矢印キーによる微調整を受け付けるためCanvasにフォーカスを移す
        self.canvas.focus_set()
        if self.crop_box is None:
            return

        cx = event.x - self.img_offset_x
        cy = event.y - self.img_offset_y
        cl, ct, cr, cb = self.crop_box

        if not (cl <= cx <= cr and ct <= cy <= cb):
            # 画像範囲外のクリックは無視
            if not (0 <= cx <= self.prev_w and 0 <= cy <= self.prev_h):
                return
            box_w = cr - cl
            box_h = cb - ct
            self._move_crop_to(cx - box_w / 2.0, cy - box_h / 2.0)
            self._draw_overlay()

        self.is_dragging = True
        self.drag_start_x = cx
        self.drag_start_y = cy
        self.drag_box_orig = self.crop_box

    def _on_drag_motion(self, event) -> None:
        """ドラッグ中: クロップ枠を画像表示範囲内に制限しながら移動"""
        if not self.is_dragging or self.drag_box_orig is None:
            return

        cx = event.x - self.img_offset_x
        cy = event.y - self.img_offset_y

        dx = cx - self.drag_start_x
        dy = cy - self.drag_start_y

        orig_l, orig_t, _, _ = self.drag_box_orig
        self._move_crop_to(orig_l + dx, orig_t + dy)
        self._draw_overlay()

    def _move_crop_to(self, new_l: float, new_t: float) -> None:
        """クロップ枠を指定位置へ移動（プレビュー画像範囲内にクランプ）"""
        if self.crop_box is None:
            return
        cl, ct, cr, cb = self.crop_box
        box_w = cr - cl
        box_h = cb - ct
        new_l = max(0.0, min(float(self.prev_w - box_w), new_l))
        new_t = max(0.0, min(float(self.prev_h - box_h), new_t))
        self.crop_box = (new_l, new_t, new_l + box_w, new_t + box_h)

    def _on_nudge_crop(self, dx_orig: int, dy_orig: int) -> str:
        """矢印キー押下時: 元画像のピクセル単位でクロップ枠を微調整"""
        if self.crop_box is None or self.preview_scale <= 0:
            return "break"
        cl, ct, _, _ = self.crop_box
        self._move_crop_to(cl + dx_orig * self.preview_scale, ct + dy_orig * self.preview_scale)
        self._draw_overlay()
        return "break"

    def _on_drag_end(self, event) -> None:
        """ドラッグ終了"""
        self.is_dragging = False
        self.drag_box_orig = None

    # --- 保存処理 ---

    def _on_save_image(self) -> None:
        """「別名で保存」ボタン押下時: Exif除去・元解像度クロップ別名保存"""
        if self.processor.original_image is None or self.crop_box is None:
            messagebox.showwarning("警告", "保存対象の写真がありません。")
            return

        # 未適用の補正値がある場合は、プレビューと保存結果の食い違いを防ぐため確認する
        if self._has_pending_adj():
            answer = messagebox.askyesnocancel(
                "未適用の補正があります",
                "変更した補正値がプレビューに未適用です。\n\n"
                "・はい: 適用してから保存\n"
                "・いいえ: 現在のプレビュー（適用済みの補正）のまま保存\n"
                "・キャンセル: 保存を中止",
            )
            if answer is None:
                return
            if answer:
                self._on_apply_adjustments()

        orig_dir = os.path.dirname(self.processor.filepath) if self.processor.filepath else os.getcwd()
        orig_base = os.path.splitext(os.path.basename(self.processor.filepath))[0] if self.processor.filepath else "photo"
        default_filename = f"{orig_base}_sns.jpg"

        filetypes = [("JPEG画像", "*.jpg *.jpeg"), ("すべてのファイル", "*.*")]
        save_path = filedialog.asksaveasfilename(
            title="SNS向けに最適化して別名保存",
            initialdir=orig_dir,
            initialfile=default_filename,
            defaultextension=".jpg",
            filetypes=filetypes,
        )
        if not save_path:
            return

        try:
            # プレビュー上の crop_box を元画像座標系に変換
            cl, ct, cr, cb = self.crop_box
            orig_left = int(round(cl / self.preview_scale))
            orig_top = int(round(ct / self.preview_scale))
            orig_right = int(round(cr / self.preview_scale))
            orig_bottom = int(round(cb / self.preview_scale))

            raw_rect = (orig_left, orig_top, orig_right, orig_bottom)
            # アスペクト比の厳密補正（微小な丸め誤差を除去）
            preset_name = self.combo_ratio.get()
            preset_info = CROP_PRESETS.get(preset_name)
            crop_rect = self.processor.adjust_crop_rect_to_aspect(raw_rect, preset_info)
            # 保存はプレビューと同じ「適用済み」の補正値で行う（UI値 -> Pillow倍率に変換）
            bright_ui, contrast_ui, color_ui = self.applied_adj
            quality = int(float(self.scale_quality.get()))

            # 出力サイズ（長辺上限）の取得
            size_key = self.combo_size.get()
            max_long_edge = OUTPUT_SIZE_PRESETS.get(size_key, 1080)

            final_w, final_h = self.processor.save_cropped_image(
                output_path=save_path,
                crop_rect=crop_rect,
                brightness=self._ui_to_factor(bright_ui),
                contrast=self._ui_to_factor(contrast_ui),
                color=self._ui_to_factor(color_ui),
                quality=quality,
                max_long_edge=max_long_edge,
            )

            saved_name = os.path.basename(save_path)
            self.lbl_status.config(text=f"保存完了: {saved_name} ({final_w}×{final_h} px, Exif除去済)")
            messagebox.showinfo(
                "保存完了",
                f"以下の内容で保存しました:\n\n"
                f"・保存先: {save_path}\n"
                f"・出力解像度: {final_w} × {final_h} px\n"
                f"・サイズ設定: {size_key}\n"
                f"・Exifメタデータ: 完全削除済 (プライバシー保護)\n"
                f"・品質: {quality}",
            )
        except Exception as e:
            messagebox.showerror("エラー", f"画像の保存に失敗しました:\n{e}")
