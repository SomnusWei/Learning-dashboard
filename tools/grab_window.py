"""
窗口截图探查脚本
用途：查找指定进程/标题的窗口，截取该窗口区域并保存为 PNG
用法：python grab_window.py [--proc Androws.exe] [--title 蓝基因]
      python grab_window.py --proc Androws.exe --title 蓝基因 --json
依赖：pip install pywin32 Pillow
"""
import argparse
import json
import os
import sys

try:
    import win32gui
    import win32process
    import win32ui
    import win32con
except ImportError:
    print("请先安装依赖：pip install pywin32 Pillow")
    sys.exit(1)

from PIL import Image, ImageFilter, ImageOps
import ctypes


def _enhance_for_ocr(img: Image.Image) -> Image.Image:
    """图像预处理：仅做格式转换（RGBA→RGB），让 OCR 引擎自己做预处理。
    之前的 2 倍放大+灰度+UnsharpMask 锐化反而让细笔画文字断裂，准确率下降。
    """
    if img.mode == "RGBA":
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.paste(img, mask=img.getchannel("A"))
        img = bg
    return img.convert("RGB")


def find_windows_by_proc(proc_name: str | None = None, title_keyword: str | None = None) -> list[dict]:
    """查找符合条件的所有窗口。"""
    results = []

    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return True

        # 标题过滤
        if title_keyword and title_keyword.lower() not in title.lower():
            return True

        # 进程名过滤
        if proc_name:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                import subprocess
                # Windows: 不显示 cmd 弹窗
                kwargs = {"capture_output": True, "text": True, "errors": "ignore"}
                if sys.platform == "win32":
                    kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
                out = subprocess.check_output(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                    **kwargs
                ).strip()
                if proc_name.lower() not in out.lower():
                    return True
            except Exception:
                pass

        rect = win32gui.GetWindowRect(hwnd)
        results.append({
            "hwnd": hwnd,
            "title": title,
            "rect": rect,  # (left, top, right, bottom)
            "width": rect[2] - rect[0],
            "height": rect[3] - rect[1],
        })
        return True

    win32gui.EnumWindows(callback, None)
    return results


def grab_window(hwnd: int, output_path: str = "window_capture.png") -> str:
    """截取指定窗口（仅客户区，不含标题栏）并保存。
    针对 Android 模拟器等 GPU 渲染窗口，依次尝试：
    1. PrintWindow(PW_RENDERFULLCONTENT=3) — 能截 GPU 渲染内容
    2. BitBlt + GetDC — 普通窗口默认方式
    3. 屏幕截图 + 客户区裁剪 — 最后回退方案
    """
    # 获取客户区大小
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        raise ValueError(f"窗口客户区大小无效: {width}x{height}")

    import ctypes
    user32 = ctypes.windll.user32

    def _valid_pixel_ratio(img: Image.Image) -> float:
        """计算有效像素占比（非透明 + 非全黑）"""
        alpha_band = img.getchannel("A")
        # 统计 alpha > 0 的像素数
        hist = alpha_band.histogram()
        transparent_px = hist[0]
        total_px = img.width * img.height
        non_transparent_ratio = 1.0 - (transparent_px / total_px)
        return non_transparent_ratio

    # 方案 1：PrintWindow + PW_RENDERFULLCONTENT（3）
    # 该标志能截到 GPU 渲染内容（DirectX/OpenGL/SurfaceView）
    try:
        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        save_bitmap = win32ui.CreateBitmap()
        save_bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(save_bitmap)

        # PrintWindow 返回 1 表示成功，0 表示失败
        # PW_RENDERFULLCONTENT = 3（Win8.1+，截 GPU 内容）
        result = user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 3)

        if result == 1:
            bmp_info = save_bitmap.GetInfo()
            bmp_bits = save_bitmap.GetBitmapBits(True)
            img = Image.frombuffer(
                "RGBA",
                (bmp_info["bmWidth"], bmp_info["bmHeight"]),
                bmp_bits, "raw", "BGRA", 0, 1
            )
            # 有效像素 > 50% 才认为成功
            if _valid_pixel_ratio(img) > 0.5:
                save_dc.DeleteDC()
                win32gui.DeleteObject(save_bitmap.GetHandle())
                mfc_dc.DeleteDC()
                win32gui.ReleaseDC(hwnd, hwnd_dc)
                img = _enhance_for_ocr(img)
                img.save(output_path)
                print(f"[截图方式] PrintWindow(PW_RENDERFULLCONTENT)")
                return output_path
        # PrintWindow 失败或有效像素不足，清理后继续
        save_dc.DeleteDC()
        win32gui.DeleteObject(save_bitmap.GetHandle())
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)
    except Exception as e:
        print(f"[PrintWindow 失败] {e}")

    # 方案 2：BitBlt + GetDC（普通窗口默认方式）
    try:
        hwnd_dc = win32gui.GetDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        save_bitmap = win32ui.CreateBitmap()
        save_bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(save_bitmap)
        save_dc.BitBlt((0, 0), (width, height), mfc_dc, (0, 0), win32con.SRCCOPY)

        bmp_info = save_bitmap.GetInfo()
        bmp_bits = save_bitmap.GetBitmapBits(True)
        img = Image.frombuffer(
            "RGBA",
            (bmp_info["bmWidth"], bmp_info["bmHeight"]),
            bmp_bits, "raw", "BGRA", 0, 1
        )
        # 有效像素 > 50% 才认为成功
        if _valid_pixel_ratio(img) > 0.5:
            save_dc.DeleteDC()
            win32gui.DeleteObject(save_bitmap.GetHandle())
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)
            img = _enhance_for_ocr(img)
            img.save(output_path)
            print(f"[截图方式] BitBlt + GetDC")
            return output_path
        save_dc.DeleteDC()
        win32gui.DeleteObject(save_bitmap.GetHandle())
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)
    except Exception as e:
        print(f"[BitBlt 失败] {e}")

    # 方案 3：屏幕截图 + 客户区裁剪（回退方案，需窗口在前台可见）
    print("[截图方式] 屏幕截图 + 客户区裁剪（回退）")
    user32.SetProcessDPIAware()
    # 客户区左上角屏幕坐标
    screen_left, screen_top = win32gui.ClientToScreen(hwnd, (0, 0))
    screen_right = screen_left + width
    screen_bottom = screen_top + height

    screen_dc = user32.GetDC(0)
    gdi32 = ctypes.windll.gdi32
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bmp = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
    gdi32.SelectObject(mem_dc, bmp)
    # BitBlt 从屏幕 DC 截取客户区区域
    gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, screen_left, screen_top, 0x00CC0020)

    # 读取位图
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
            ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
            ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
            ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
            ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
            ("biClrImportant", ctypes.c_uint32),
        ]
    bmp_header = BITMAPINFOHEADER()
    bmp_header.biSize = ctypes.sizeof(bmp_header)
    bmp_header.biWidth = width
    bmp_header.biHeight = -height  # 自上而下
    bmp_header.biPlanes = 1
    bmp_header.biBitCount = 32
    bmp_header.biCompression = 0
    buf = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem_dc, bmp, 0, height, buf, ctypes.byref(bmp_header), 0)
    img = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1)

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(0, screen_dc)
    img = _enhance_for_ocr(img)
    img.save(output_path)
    return output_path


def grab_window_by_screen(hwnd: int, output_path: str = "window_capture.png") -> str:
    """用屏幕坐标截取整个窗口（含标题栏）。"""
    rect = win32gui.GetWindowRect(hwnd)
    left, top, right, bottom = rect
    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        raise ValueError(f"窗口大小无效: {width}x{height}")

    # 用 ctypes 截屏区域
    from ctypes import windll
    user32 = windll.user32
    user32.SetProcessDPIAware()

    dc = user32.GetDC(0)
    import ctypes
    gdi32 = ctypes.windll.gdi32

    bmp = gdi32.CreateCompatibleBitmap(dc, width, height)
    mem_dc = gdi32.CreateCompatibleDC(dc)
    gdi32.SelectObject(mem_dc, bmp)
    gdi32.BitBlt(mem_dc, 0, 0, width, height, dc, left, top, 0x00CC0020)  # SRCCOPY

    # 读取位图
    bmp_header = ctypes.Structure(
        "BITMAPINFOHEADER",
        [
            ("biSize", ctypes.c_uint32),
            ("biWidth", ctypes.c_int32),
            ("biHeight", ctypes.c_int32),
            ("biPlanes", ctypes.c_uint16),
            ("biBitCount", ctypes.c_uint16),
            ("biCompression", ctypes.c_uint32),
            ("biSizeImage", ctypes.c_uint32),
            ("biXPelsPerMeter", ctypes.c_int32),
            ("biYPelsPerMeter", ctypes.c_int32),
            ("biClrUsed", ctypes.c_uint32),
            ("biClrImportant", ctypes.c_uint32),
        ],
    )
    bmp_header.biSize = ctypes.sizeof(bmp_header)
    bmp_header.biWidth = width
    bmp_header.biHeight = -height  # 自上而下
    bmp_header.biPlanes = 1
    bmp_header.biBitCount = 32
    bmp_header.biCompression = 0

    buf = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(mem_dc, bmp, 0, height, buf, ctypes.byref(bmp_header), 0)

    img = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1)
    img = _enhance_for_ocr(img)
    img.save(output_path)

    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(0, dc)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="抓取指定窗口截图")
    parser.add_argument("--proc", default=None, help="进程名，如 Androws.exe")
    parser.add_argument("--title", default=None, help="窗口标题关键字，如 藝基因")
    parser.add_argument("--list", action="store_true", help="仅列出匹配窗口")
    parser.add_argument("--hwnd", type=int, default=None, help="直接指定窗口句柄")
    parser.add_argument("-o", "--output", default="window_capture.png", help="输出文件路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")
    args = parser.parse_args()

    if args.list:
        windows = find_windows_by_proc(args.proc, args.title)
        if not windows:
            if args.json:
                print(json.dumps({"success": False, "error": "未找到匹配的窗口"}))
            else:
                print("未找到匹配的窗口")
            return
        if args.json:
            print(json.dumps({
                "success": True,
                "windows": [
                    {"hwnd": w["hwnd"], "title": w["title"], "width": w["width"], "height": w["height"]}
                    for w in windows
                ],
            }))
        else:
            for w in windows:
                print(f"  hwnd={w['hwnd']}  title='{w['title']}'  rect={w['rect']}  size={w['width']}x{w['height']}")
        return

    hwnd = args.hwnd
    if not hwnd:
        windows = find_windows_by_proc(args.proc, args.title)
        if not windows:
            if args.json:
                print(json.dumps({"success": False, "error": "未找到匹配的窗口"}))
            else:
                print("未找到匹配的窗口")
            return
        # 取最大的窗口（通常是主窗口）
        hwnd = max(windows, key=lambda w: w["width"] * w["height"])["hwnd"]

    # 截图
    try:
        path = grab_window(hwnd, args.output)
    except Exception as e:
        if args.json:
            print(json.dumps({"success": False, "error": f"截图失败: {e}"}))
        else:
            print(f"截图失败: {e}")
        return

    title = win32gui.GetWindowText(hwnd)
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    width = right - left
    height = bottom - top
    size = os.path.getsize(path)

    if args.json:
        # 输出 JSON（最后一行），方便 Rust 解析
        print(json.dumps({
            "success": True,
            "hwnd": hwnd,
            "title": title,
            "width": width,
            "height": height,
            "size": size,
            "png_path": os.path.abspath(path),
        }))
    else:
        print(f"自动选择窗口: hwnd={hwnd}, title='{title}'")
        print(f"\n匹配到的窗口：")
        all_windows = find_windows_by_proc(args.proc, args.title)
        for w in all_windows:
            marker = " ← 选中" if w["hwnd"] == hwnd else ""
            print(f"  hwnd={w['hwnd']}  title='{w['title']}'  size={w['width']}x{w['height']}{marker}")
        print(f"\n✅ 窗口截图已保存: {path}")
        print(f"   文件大小: {size} bytes")


if __name__ == "__main__":
    main()
