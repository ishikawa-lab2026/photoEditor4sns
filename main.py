"""photoEditor4sns アプリケーション エントリポイント
"""
import sys
import tkinter as tk

from src.app import PhotoEditorApp


def _enable_high_dpi_awareness() -> None:
    """Windows環境での高DPI（4Kディスプレイ等）ボケ防止設定"""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def main() -> None:
    """メイン実行関数"""
    _enable_high_dpi_awareness()
    root = tk.Tk()
    PhotoEditorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
