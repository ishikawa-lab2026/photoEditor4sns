"""Tkinter / ttk による photoEditor4sns メインGUIアプリケーション
"""
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, Tuple
from PIL import ImageTk

from .presets import RATIO_PRESETS, OUTPUT_SIZE_PRESETS
from .image_processor import ImageProcessor


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

        # スタイルの設定
        self._setup_style()

        # UIコンポーネントの構築
        self._create_widgets()

    def _setup_style(self) -> None:
        """ttk ウィジェットの共通スタイル設定"""
        self.style = ttk.Style()
        # 利用可能なテーマから 'clam' またはシステム標準を選択
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")

        self.style.configure("Header.TLabel", font=("Helvetica", 11, "bold"))
        self.style.configure("Status.TLabel", font=("Helvetica", 9))
        self.style.configure("Action.TButton", font=("Helvetica", 10, "bold"))
        self.style.configure("Primary.TButton", font=("Helvetica", 11, "bold"))

    def _create_widgets(self) -> None:
        """GUI ウィジェット全体の配置"""
        # 1. 上部ツールバー
        top_bar = ttk.Frame(self.root, padding=(10, 8))
        top_bar.pack(side=tk.TOP, fill=tk.X)

        self.btn_open = ttk.Button(top_bar, text="📁 画像を開く (JPEG)", command=self._on_open_image)
        self.btn_open.pack(side=tk.LEFT, padx=(0, 10))

        self.lbl_file_info = ttk.Label(top_bar, text="画像が選択されていません", font=("Helvetica", 10))
        self.lbl_file_info.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.lbl_orig_size = ttk.Label(top_bar, text="", font=("Helvetica", 9))
        self.lbl_orig_size.pack(side=tk.RIGHT, padx=5)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(side=tk.TOP, fill=tk.X)

        # 2. 下部ステータスバー
        self.status_bar = ttk.Frame(self.root, padding=(10, 4), relief=tk.SUNKEN)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.lbl_status = ttk.Label(self.status_bar, text="準備完了 - 「画像を開く」ボタンから写真を読み込んでください。", style="Status.TLabel")
        self.lbl_status.pack(side=tk.LEFT)

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

        # 右ペイン: 操作サイドバー
        sidebar = ttk.Frame(main_pane, padding=(12, 6))
        main_pane.add(sidebar, weight=1)

        # (1) アスペクト比・クロップ選択
        lbl_ratio = ttk.Label(sidebar, text="【1】SNS アスペクト比", style="Header.TLabel")
        lbl_ratio.pack(anchor=tk.W, pady=(0, 4))

        self.combo_ratio = ttk.Combobox(sidebar, values=list(RATIO_PRESETS.keys()), state="readonly", font=("Helvetica", 9))
        self.combo_ratio.current(0)  # Instagram 1:1
        self.combo_ratio.pack(fill=tk.X, pady=(0, 12))
        self.combo_ratio.bind("<<ComboboxSelected>>", self._on_ratio_changed)

        ttk.Separator(sidebar, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=6)

        # (2) 簡易画像調整 (Image Adjustments)
        lbl_adj = ttk.Label(sidebar, text="【2】画質・色調補正", style="Header.TLabel")
        lbl_adj.pack(anchor=tk.W, pady=(4, 4))

        # 明るさ
        f_b = ttk.Frame(sidebar)
        f_b.pack(fill=tk.X, pady=2)
        ttk.Label(f_b, text="明るさ (Brightness):").pack(side=tk.LEFT)
        self.lbl_val_bright = ttk.Label(f_b, text="1.00", width=5, anchor=tk.E)
        self.lbl_val_bright.pack(side=tk.RIGHT)
        self.scale_bright = ttk.Scale(sidebar, from_=0.2, to=2.0, value=1.0, command=lambda v: self._update_slider_label(self.lbl_val_bright, v))
        self.scale_bright.pack(fill=tk.X, pady=(0, 6))

        # コントラスト
        f_c = ttk.Frame(sidebar)
        f_c.pack(fill=tk.X, pady=2)
        ttk.Label(f_c, text="コントラスト (Contrast):").pack(side=tk.LEFT)
        self.lbl_val_contrast = ttk.Label(f_c, text="1.00", width=5, anchor=tk.E)
        self.lbl_val_contrast.pack(side=tk.RIGHT)
        self.scale_contrast = ttk.Scale(sidebar, from_=0.2, to=2.0, value=1.0, command=lambda v: self._update_slider_label(self.lbl_val_contrast, v))
        self.scale_contrast.pack(fill=tk.X, pady=(0, 6))

        # 彩度
        f_s = ttk.Frame(sidebar)
        f_s.pack(fill=tk.X, pady=2)
        ttk.Label(f_s, text="彩度 (Color/Saturation):").pack(side=tk.LEFT)
        self.lbl_val_color = ttk.Label(f_s, text="1.00", width=5, anchor=tk.E)
        self.lbl_val_color.pack(side=tk.RIGHT)
        self.scale_color = ttk.Scale(sidebar, from_=0.0, to=2.0, value=1.0, command=lambda v: self._update_slider_label(self.lbl_val_color, v))
        self.scale_color.pack(fill=tk.X, pady=(0, 10))

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
        self.combo_size = ttk.Combobox(sidebar, values=list(OUTPUT_SIZE_PRESETS.keys()), state="readonly", font=("Helvetica", 9))
        self.combo_size.current(0)  # 長辺 1080px (Instagram / 標準推奨)
        self.combo_size.pack(fill=tk.X, pady=(0, 8))

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
        self.scale_quality.config(state=state)
        self.btn_apply.config(state=state)
        self.btn_reset.config(state=state)
        self.btn_save.config(state=state)

    def _update_slider_label(self, label: ttk.Label, val_str: str) -> None:
        """スライダー数値をラベルに反映"""
        try:
            val = float(val_str)
            label.config(text=f"{val:.2f}")
        except ValueError:
            pass

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
        """補正スライダーおよびクロップ枠を初期値にリセット"""
        self.scale_bright.set(1.0)
        self.scale_contrast.set(1.0)
        self.scale_color.set(1.0)
        self.lbl_val_bright.config(text="1.00")
        self.lbl_val_contrast.config(text="1.00")
        self.lbl_val_color.config(text="1.00")

        self._recalc_initial_crop_box()
        self._render_canvas(apply_adjustments=False)

    def _recalc_initial_crop_box(self) -> None:
        """現在の選択プリセットに基づいてプレビュー内の中央クロップ枠を計算"""
        if self.processor.original_image is None or self.prev_w == 0 or self.prev_h == 0:
            return

        preset_key = self.combo_ratio.get()
        preset_info = RATIO_PRESETS.get(preset_key, None)

        if preset_info is None:
            # フリー / 元画像全体: プレビュー画像全体
            self.crop_box = (0.0, 0.0, float(self.prev_w), float(self.prev_h))
        else:
            orig_crop_w, orig_crop_h = self.processor.get_crop_size_for_preset(preset_info)
            # 元画像のクロップサイズをプレビュー座標系にスケール変換
            prev_box_w = orig_crop_w * self.preview_scale
            prev_box_h = orig_crop_h * self.preview_scale

            left = (self.prev_w - prev_box_w) / 2.0
            top = (self.prev_h - prev_box_h) / 2.0
            self.crop_box = (left, top, left + prev_box_w, top + prev_box_h)

    def _on_ratio_changed(self, event=None) -> None:
        """クロッププリセットコンボボックス変更時の処理"""
        if self.processor.original_image is None:
            return
        self._recalc_initial_crop_box()
        self._draw_overlay()
        preset_name = self.combo_ratio.get()
        preset_info = RATIO_PRESETS.get(preset_name, None)

        # 固定枠の場合は出力サイズ設定を「元解像度のまま」に自動で合わせる案内
        if preset_info and preset_info[0] == "fixed":
            target_w, target_h = preset_info[1]
            self.combo_size.set("元解像度のまま (縮小なし)")
            self.lbl_status.config(text=f"推奨固定枠「{target_w}×{target_h} px」を配置しました。ドラッグで位置を合わせて「元解像度のまま」保存できます。")
        else:
            self.lbl_status.config(text=f"切り抜き枠を「{preset_name}」に変更しました。枠内をドラッグして位置を調整できます。")

    def _on_apply_adjustments(self) -> None:
        """「適用」ボタン押下時: 色調補正をプレビューに反映"""
        if self.processor.original_image is None:
            return
        self._render_canvas(apply_adjustments=True)
        self.lbl_status.config(text="色調補正をプレビューに反映しました。")

    def _on_reset_adjustments(self) -> None:
        """「リセット」ボタン押下時: 補正値とクロップ位置を初期化"""
        if self.processor.original_image is None:
            return
        self._reset_all_params()
        self.lbl_status.config(text="補正値とクロップ枠を初期状態に戻しました。")

    def _on_canvas_resize(self, event) -> None:
        """ウィンドウ・Canvasリサイズ時の再描画"""
        if self.processor.original_image is not None:
            # プレビューサイズをCanvasに合わせて再計算
            self._render_canvas(apply_adjustments=False)

    def _render_canvas(self, apply_adjustments: bool = False) -> None:
        """プレビュー画像とオーバーレイをCanvasに描画"""
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

        bright = float(self.scale_bright.get())
        contrast = float(self.scale_contrast.get())
        color = float(self.scale_color.get())

        prev_img, scale, pw, ph = self.processor.get_preview_image(
            max_size=(max_pw, max_ph),
            brightness=bright,
            contrast=contrast,
            color=color,
            apply_adjustments=apply_adjustments,
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

        # 4. クロップ枠の元画像実サイズ (px) のラベル表示
        if self.preview_scale > 0:
            actual_w = int(round((cr - cl) / self.preview_scale))
            actual_h = int(round((cb - ct) / self.preview_scale))
            size_text = f" {actual_w} × {actual_h} px "
            
            # 枠上部または枠内にバッジ表示
            tag_y = y1 - 10 if y1 >= 20 else y1 + 12
            self.canvas.create_rectangle(
                x1, tag_y - 9, x1 + len(size_text) * 7.5, tag_y + 9,
                fill="#1e1e1e", outline="#00ffcc", width=1, tags="crop_overlay"
            )
            self.canvas.create_text(
                x1 + 4, tag_y, text=size_text, fill="#00ffcc",
                anchor=tk.W, font=("Helvetica", 9, "bold"), tags="crop_overlay"
            )

    # --- ドラッグによるクロップ枠移動イベント ---

    def _on_drag_start(self, event) -> None:
        """マウスクリック時: ドラッグ開始座標を記録"""
        if self.crop_box is None:
            return

        cx = event.x - self.img_offset_x
        cy = event.y - self.img_offset_y
        cl, ct, cr, cb = self.crop_box

        # 枠内または枠近傍をクリックした場合にドラッグ開始
        if cl <= cx <= cr and ct <= cy <= cb:
            self.is_dragging = True
            self.drag_start_x = cx
            self.drag_start_y = cy
            self.drag_box_orig = (cl, ct, cr, cb)

    def _on_drag_motion(self, event) -> None:
        """ドラッグ中: クロップ枠を画像表示範囲内に制限しながら移動"""
        if not self.is_dragging or self.drag_box_orig is None:
            return

        cx = event.x - self.img_offset_x
        cy = event.y - self.img_offset_y

        dx = cx - self.drag_start_x
        dy = cy - self.drag_start_y

        orig_l, orig_t, orig_r, orig_b = self.drag_box_orig
        box_w = orig_r - orig_l
        box_h = orig_b - orig_t

        new_l = orig_l + dx
        new_t = orig_t + dy

        # プレビュー画像範囲内 (0, 0, prev_w, prev_h) にクランプ
        new_l = max(0.0, min(float(self.prev_w - box_w), new_l))
        new_t = max(0.0, min(float(self.prev_h - box_h), new_t))

        self.crop_box = (new_l, new_t, new_l + box_w, new_t + box_h)
        self._draw_overlay()

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

            crop_rect = (orig_left, orig_top, orig_right, orig_bottom)
            bright = float(self.scale_bright.get())
            contrast = float(self.scale_contrast.get())
            color = float(self.scale_color.get())
            quality = int(float(self.scale_quality.get()))

            # 出力サイズ（長辺上限）の取得
            size_key = self.combo_size.get()
            max_long_edge = OUTPUT_SIZE_PRESETS.get(size_key, 1080)

            final_w, final_h = self.processor.save_cropped_image(
                output_path=save_path,
                crop_rect=crop_rect,
                brightness=bright,
                contrast=contrast,
                color=color,
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
