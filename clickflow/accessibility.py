"""macOS Accessibility permission integration."""

import ctypes
import ctypes.util
import platform
import subprocess

from .models import AccessibilityPermission


ACCESSIBILITY_SETTINGS_URL = (
    "x-apple.systempreferences:com.apple.preference.security?"
    "Privacy_Accessibility"
)


def get_accessibility_permission() -> AccessibilityPermission:
    """Return the current macOS Accessibility permission state."""

    if platform.system() != "Darwin":
        return AccessibilityPermission.NOT_MACOS

    framework_path = ctypes.util.find_library("ApplicationServices") or (
        "/System/Library/Frameworks/ApplicationServices.framework/"
        "ApplicationServices"
    )
    try:
        application_services = ctypes.CDLL(framework_path)
        is_trusted = application_services.AXIsProcessTrusted
        is_trusted.argtypes = []
        is_trusted.restype = ctypes.c_bool
        if is_trusted():
            return AccessibilityPermission.GRANTED
        return AccessibilityPermission.DENIED
    except (AttributeError, OSError):
        return AccessibilityPermission.CHECK_FAILED


def open_accessibility_settings() -> bool:
    """Open macOS Accessibility settings, with broader fallbacks."""

    if platform.system() != "Darwin":
        return False

    commands = (
        ["open", ACCESSIBILITY_SETTINGS_URL],
        ["open", "/System/Library/PreferencePanes/Security.prefPane"],
        ["open", "-b", "com.apple.systempreferences"],
    )
    for command in commands:
        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except (OSError, subprocess.CalledProcessError):
            continue
    return False
