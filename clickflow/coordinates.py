"""Desktop discovery, coordinate resolution, safety checks, and previews."""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
import platform
from typing import Protocol

import pyautogui


@dataclass(frozen=True, slots=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    def contains(self, x: int, y: int) -> bool:
        return self.width > 0 and self.height > 0 and self.x <= x < self.x + self.width and self.y <= y < self.y + self.height


@dataclass(frozen=True, slots=True)
class DisplayInfo:
    id: str
    name: str
    bounds: Rect
    is_primary: bool = False


@dataclass(frozen=True, slots=True)
class WindowInfo:
    id: str
    title: str
    owner: str
    bounds: Rect

    @property
    def label(self) -> str:
        return f"{self.owner} — {self.title}" if self.title else self.owner


class DesktopBackend(Protocol):
    def displays(self) -> tuple[DisplayInfo, ...]: ...
    def windows(self) -> tuple[WindowInfo, ...]: ...
    def pixel(self, x: int, y: int) -> tuple[int, int, int]: ...
    def screenshot(self, region: tuple[int, int, int, int]): ...


class SystemDesktopBackend:
    """Best-effort desktop inventory with a PyAutoGUI fallback.

    Quartz is optional at runtime. It is available in many macOS Python
    installations; without it the primary display remains fully usable.
    """

    def displays(self) -> tuple[DisplayInfo, ...]:
        try:
            import Quartz  # type: ignore[import-not-found]

            _error, display_ids, _count = Quartz.CGGetActiveDisplayList(32, None, None)
            main_id = Quartz.CGMainDisplayID()
            result = []
            for index, display_id in enumerate(display_ids):
                bounds = Quartz.CGDisplayBounds(display_id)
                result.append(DisplayInfo(
                    str(display_id), f"显示器 {index + 1}",
                    Rect(round(bounds.origin.x), round(bounds.origin.y), round(bounds.size.width), round(bounds.size.height)),
                    display_id == main_id,
                ))
            if result:
                return tuple(result)
        except (ImportError, AttributeError, TypeError):
            pass
        if platform.system() == "Darwin":
            try:
                class CGPoint(ctypes.Structure):
                    _fields_ = (("x", ctypes.c_double), ("y", ctypes.c_double))

                class CGSize(ctypes.Structure):
                    _fields_ = (("width", ctypes.c_double), ("height", ctypes.c_double))

                class CGRect(ctypes.Structure):
                    _fields_ = (("origin", CGPoint), ("size", CGSize))

                core_graphics = ctypes.CDLL(
                    "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
                )
                core_graphics.CGGetActiveDisplayList.argtypes = (
                    ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32)
                )
                core_graphics.CGGetActiveDisplayList.restype = ctypes.c_int32
                core_graphics.CGDisplayBounds.argtypes = (ctypes.c_uint32,)
                core_graphics.CGDisplayBounds.restype = CGRect
                core_graphics.CGMainDisplayID.restype = ctypes.c_uint32
                display_ids = (ctypes.c_uint32 * 32)()
                count = ctypes.c_uint32()
                error = core_graphics.CGGetActiveDisplayList(32, display_ids, ctypes.byref(count))
                if error == 0:
                    main_id = core_graphics.CGMainDisplayID()
                    result = []
                    for index in range(count.value):
                        display_id = display_ids[index]
                        bounds = core_graphics.CGDisplayBounds(display_id)
                        result.append(DisplayInfo(
                            str(display_id), f"显示器 {index + 1}",
                            Rect(round(bounds.origin.x), round(bounds.origin.y), round(bounds.size.width), round(bounds.size.height)),
                            display_id == main_id,
                        ))
                    if result:
                        return tuple(result)
            except (OSError, AttributeError, TypeError):
                pass
        size = pyautogui.size()
        return (DisplayInfo("primary", "主显示器", Rect(0, 0, size.width, size.height), True),)

    def windows(self) -> tuple[WindowInfo, ...]:
        try:
            import Quartz  # type: ignore[import-not-found]

            options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
            raw_windows = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
            result = []
            for raw in raw_windows:
                bounds = raw.get("kCGWindowBounds", raw.get(Quartz.kCGWindowBounds))
                owner = str(raw.get("kCGWindowOwnerName", raw.get(Quartz.kCGWindowOwnerName, "")))
                title = str(raw.get("kCGWindowName", raw.get(Quartz.kCGWindowName, "")) or "")
                window_id = raw.get("kCGWindowNumber", raw.get(Quartz.kCGWindowNumber))
                layer = raw.get("kCGWindowLayer", raw.get(Quartz.kCGWindowLayer, 0))
                if bounds and window_id is not None and layer == 0:
                    result.append(WindowInfo(
                        str(window_id), title, owner,
                        Rect(round(bounds["X"]), round(bounds["Y"]), round(bounds["Width"]), round(bounds["Height"])),
                    ))
            return tuple(result)
        except (ImportError, AttributeError, TypeError, KeyError):
            return ()

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        try:
            from PIL import ImageGrab

            image = ImageGrab.grab(bbox=(x, y, x + 1, y + 1), all_screens=True)
            return tuple(image.getpixel((0, 0)))[:3]  # type: ignore[return-value]
        except (ImportError, OSError, TypeError):
            return tuple(pyautogui.pixel(x, y))[:3]  # type: ignore[return-value]

    def screenshot(self, region: tuple[int, int, int, int]):
        try:
            from PIL import ImageGrab

            x, y, width, height = region
            return ImageGrab.grab(bbox=(x, y, x + width, y + height), all_screens=True)
        except (ImportError, OSError, TypeError):
            return pyautogui.screenshot(region=region)


def select_display(displays: tuple[DisplayInfo, ...], display_id: str | None) -> DisplayInfo:
    if not displays:
        raise RuntimeError("未识别到可用显示器。")
    if display_id:
        for display in displays:
            if display.id == display_id:
                return display
        raise RuntimeError(f"找不到显示器 {display_id}，请刷新后重新选择。")
    return next((item for item in displays if item.is_primary), displays[0])


def select_window(windows: tuple[WindowInfo, ...], target: str | None) -> WindowInfo:
    query = (target or "").strip()
    if not query:
        raise RuntimeError("窗口相对坐标缺少目标窗口。")
    for window in windows:
        if query == window.id or query == window.label or query == window.title:
            return window
    lowered = query.casefold()
    matches = [item for item in windows if lowered in item.label.casefold()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise RuntimeError(f"找不到目标窗口“{query}”。")
    raise RuntimeError(f"目标窗口“{query}”不唯一，请重新选择。")


def resolve_point(action, backend: DesktopBackend | None = None) -> tuple[int, int]:
    """Resolve a mouse action to a global desktop point at execution time."""

    backend = backend or SystemDesktopBackend()
    if action.coordinate_mode == "absolute":
        return round(action.x), round(action.y)
    if action.coordinate_mode == "display_percent":
        display = select_display(backend.displays(), action.display_id)
        return (
            display.bounds.x + round((display.bounds.width - 1) * action.x / 100),
            display.bounds.y + round((display.bounds.height - 1) * action.y / 100),
        )
    if action.coordinate_mode == "window":
        window = select_window(backend.windows(), action.target_window)
        if not (0 <= action.x < window.bounds.width and 0 <= action.y < window.bounds.height):
            raise RuntimeError(
                f"窗口相对坐标 ({action.x:g}, {action.y:g}) 超出目标窗口范围。"
            )
        return window.bounds.x + round(action.x), window.bounds.y + round(action.y)
    raise ValueError(f"未知坐标模式：{action.coordinate_mode}")


def validate_action_target(action, x: int, y: int, backend: DesktopBackend | None = None) -> None:
    backend = backend or SystemDesktopBackend()
    if action.allowed_region is not None and not action.allowed_region.contains(x, y):
        raise RuntimeError(f"目标 ({x}, {y}) 超出允许区域，已阻止鼠标操作。")
    if action.operation in {"click", "double_click"} and action.expected_color is not None:
        actual = backend.pixel(x, y)
        if any(abs(actual[index] - action.expected_color[index]) > action.color_tolerance for index in range(3)):
            raise RuntimeError(
                f"目标像素颜色不匹配：期望 {action.expected_color}，实际 {actual}。"
            )


def preview_region(action, backend: DesktopBackend | None = None, radius: int = 80):
    """Capture a target/allowed-region preview and return image plus marker point."""

    backend = backend or SystemDesktopBackend()
    x, y = resolve_point(action, backend)
    if action.allowed_region is not None and not action.allowed_region.contains(x, y):
        raise RuntimeError(f"目标 ({x}, {y}) 超出允许区域，无法预览。")
    region = action.allowed_region or Rect(x - radius, y - radius, radius * 2, radius * 2)
    image = backend.screenshot((region.x, region.y, region.width, region.height))
    return image, (x - region.x, y - region.y), region
