"""MacClickPath desktop application."""

from __future__ import annotations

import platform
import queue
import threading
import time
import tkinter as tk
from dataclasses import replace
from tkinter import filedialog, messagebox, ttk

import pyautogui
from PIL import ImageDraw, ImageTk

from clickflow import (
    ACTION_LABELS,
    CONDITION_LABELS,
    LABEL_CONDITIONS,
    AccessibilityPermission,
    ExecutionState,
    DirectActionExecutor,
    RunnerEvent,
    Step,
    Workflow,
    WorkflowRunner,
    format_elapsed,
    get_accessibility_permission,
    open_accessibility_settings,
    perform_action,
    load_workflow,
    save_workflow,
    validate_step_input,
    validate_workflow,
)
from clickflow.coordinates import SystemDesktopBackend, preview_region, select_display, select_window

POLL_INTERVAL_MS = 100
CAPTURE_COUNTDOWN_SECONDS = 3
START_COUNTDOWN_SECONDS = 3
COORDINATE_MODES = {
    "absolute": "屏幕绝对坐标",
    "display_percent": "显示器百分比",
    "window": "目标窗口相对坐标",
}
LABEL_COORDINATE_MODES = {label: mode for mode, label in COORDINATE_MODES.items()}


class ClickFlowApp(tk.Tk):
    """Main desktop window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("MacClickPath")
        self.geometry("1040x840")
        self.minsize(920, 720)
        self._configure_styles()

        self.live_position = tk.StringVar(value="X: --    Y: --")
        self.capture_status = tk.StringVar(value="移动鼠标可实时查看坐标")
        self.action_value = tk.StringVar(value=ACTION_LABELS["move"])
        self.x_value = tk.StringVar()
        self.y_value = tk.StringVar()
        self.coordinate_mode_value = tk.StringVar(value=COORDINATE_MODES["absolute"])
        self.display_value = tk.StringVar()
        self.window_value = tk.StringVar()
        self.expected_color_value = tk.StringVar()
        self.color_tolerance_value = tk.StringVar(value="0")
        self.allowed_region_value = tk.StringVar()
        self.wait_value = tk.StringVar(value="0.5")
        self.wait_max_value = tk.StringVar()
        self.step_repeat_value = tk.StringVar(value="1")
        self.condition_value = tk.StringVar(value=CONDITION_LABELS["always"])
        self.condition_parameter_value = tk.StringVar()
        self.condition_timeout_value = tk.StringVar(value="0")
        self.retry_value = tk.StringVar(value="0")
        self.timeout_value = tk.StringVar()
        self.success_target_value = tk.StringVar()
        self.failure_target_value = tk.StringVar()
        self.workflow_repeat_value = tk.StringVar(value="1")
        self.infinite_loop_value = tk.BooleanVar(value=False)
        self.permission_status = tk.StringVar()
        self.execution_status = tk.StringVar(value="执行状态：待机")
        self.step_progress = tk.StringVar(value="当前步骤：0 / 0")
        self.elapsed_display = tk.StringVar(value="运行时间：00:00:00")
        self.completed_display = tk.StringVar(value="已完成操作：0 次")
        self.steps: list[Step] = []
        self._editor_locked = False
        self._editing_index: int | None = None
        self._capture_job: str | None = None
        self._position_job: str | None = None
        self._countdown_job: str | None = None
        self._execution_poll_job: str | None = None
        self._execution_state = ExecutionState.IDLE
        self._total_steps = 0
        self._current_step_number = 0
        self._completed_operations = 0
        self._elapsed_accumulated = 0.0
        self._running_started_at: float | None = None
        self._execution_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._execution_queue: queue.Queue[RunnerEvent] = queue.Queue()
        self._workflow_repeat_count: int | None = 1
        self._runner: WorkflowRunner | None = None
        self._desktop = SystemDesktopBackend()
        self._display_by_label = {}
        self._window_by_label = {}
        self._build_window()
        self._refresh_desktop_targets()
        self._refresh_permission_status(show_warning=True)
        self._poll_mouse_position()
        self._poll_execution_messages()
        self.bind("<FocusIn>", self._on_focus_in)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_styles(self) -> None:
        """Apply a deliberate cross-platform dark theme instead of raw Tk defaults."""

        self.configure(background="#0b1120")
        self.option_add("*Font", ("Helvetica Neue", 12))
        self.option_add("*TCombobox*Listbox.Font", ("Helvetica Neue", 12))
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background="#0b1120", foreground="#e5e7eb")
        style.configure("TFrame", background="#0b1120")
        style.configure("TLabel", background="#0b1120", foreground="#cbd5e1")
        style.configure("Title.TLabel", foreground="#f8fafc", font=("Helvetica Neue", 24, "bold"))
        style.configure("Subtitle.TLabel", foreground="#7dd3fc", font=("Helvetica Neue", 11))
        style.configure("Metric.TLabel", background="#111827", foreground="#f8fafc", font=("SF Mono", 19, "bold"))
        style.configure("Muted.TLabel", background="#111827", foreground="#94a3b8", font=("Helvetica Neue", 10))
        style.configure(
            "TLabelframe", background="#111827", bordercolor="#263349",
            relief="solid", borderwidth=1,
        )
        style.configure(
            "TLabelframe.Label", background="#0b1120", foreground="#f8fafc",
            font=("Helvetica Neue", 12, "bold"),
        )
        style.configure("Card.TFrame", background="#111827")
        style.configure("Card.TLabel", background="#111827", foreground="#cbd5e1")
        style.configure("CardMuted.TLabel", background="#111827", foreground="#94a3b8", font=("Helvetica Neue", 10))
        style.configure(
            "TEntry", fieldbackground="#182235", foreground="#f8fafc",
            insertcolor="#f8fafc", bordercolor="#334155", lightcolor="#334155",
            darkcolor="#334155", padding=(9, 7),
        )
        style.configure(
            "TCombobox", fieldbackground="#182235", background="#182235",
            foreground="#f8fafc", arrowcolor="#94a3b8", bordercolor="#334155",
            lightcolor="#334155", darkcolor="#334155", padding=(9, 6),
        )
        style.map("TCombobox", fieldbackground=[("readonly", "#182235")], foreground=[("readonly", "#f8fafc")])
        style.configure(
            "TButton", background="#1e293b", foreground="#e2e8f0",
            bordercolor="#334155", padding=(12, 8), font=("Helvetica Neue", 11, "bold"),
        )
        style.map("TButton", background=[("active", "#334155"), ("disabled", "#111827")], foreground=[("disabled", "#64748b")])
        style.configure("Accent.TButton", background="#0ea5e9", foreground="#06111d", bordercolor="#38bdf8")
        style.map("Accent.TButton", background=[("active", "#38bdf8"), ("disabled", "#164e63")])
        style.configure("Danger.TButton", background="#3f1d2a", foreground="#fda4af", bordercolor="#7f1d1d")
        style.configure("TCheckbutton", background="#111827", foreground="#cbd5e1")
        style.configure("TNotebook", background="#111827", borderwidth=0)
        style.configure("TNotebook.Tab", background="#111827", foreground="#94a3b8", padding=(18, 9), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", "#1e293b")], foreground=[("selected", "#f8fafc")])
        style.configure(
            "Treeview", background="#111827", fieldbackground="#111827",
            foreground="#cbd5e1", rowheight=30, bordercolor="#263349",
        )
        style.configure("Treeview.Heading", background="#182235", foreground="#94a3b8", relief="flat", padding=(6, 8), font=("Helvetica Neue", 10, "bold"))
        style.map("Treeview", background=[("selected", "#075985")], foreground=[("selected", "#f8fafc")])

    def _build_window(self) -> None:
        container = ttk.Frame(self, padding=(20, 16))
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(3, weight=1)

        header = ttk.Frame(container)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="MacClickPath", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="精准、安全地编排桌面鼠标操作", style="Subtitle.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))

        position_frame = ttk.LabelFrame(container, text="实时坐标", padding=(14, 10))
        position_frame.grid(row=1, column=0, sticky="ew")
        position_frame.columnconfigure(0, weight=1)

        ttk.Label(
            position_frame,
            textvariable=self.live_position,
            style="Metric.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(position_frame, textvariable=self.capture_status, style="Muted.TLabel").grid(
            row=0, column=1, sticky="e", padx=(20, 0)
        )

        form_frame = ttk.LabelFrame(container, text="步骤编辑器", padding=12)
        self.form_frame = form_frame
        form_frame.grid(row=2, column=0, sticky="ew", pady=12)
        form_frame.columnconfigure(0, weight=1)

        editor_tabs = ttk.Notebook(form_frame)
        editor_tabs.grid(row=0, column=0, sticky="ew")
        basic_tab = ttk.Frame(editor_tabs, style="Card.TFrame", padding=(14, 12))
        position_tab = ttk.Frame(editor_tabs, style="Card.TFrame", padding=(14, 12))
        safety_tab = ttk.Frame(editor_tabs, style="Card.TFrame", padding=(14, 12))
        editor_tabs.add(basic_tab, text="  基础操作  ")
        editor_tabs.add(position_tab, text="  坐标定位  ")
        editor_tabs.add(safety_tab, text="  安全与流程  ")
        for tab in (basic_tab, position_tab, safety_tab):
            for column in (1, 3, 5, 7):
                tab.columnconfigure(column, weight=1)

        ttk.Label(basic_tab, text="操作", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.action_input = ttk.Combobox(basic_tab, textvariable=self.action_value, values=tuple(ACTION_LABELS.values()), state="readonly", width=10)
        self.action_input.grid(row=0, column=1, sticky="ew", padx=(0, 18))
        ttk.Label(basic_tab, text="X", style="Card.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.x_input = ttk.Entry(basic_tab, textvariable=self.x_value, width=12)
        self.x_input.grid(row=0, column=3, sticky="ew", padx=(0, 18))
        ttk.Label(basic_tab, text="Y", style="Card.TLabel").grid(row=0, column=4, sticky="w", padx=(0, 8))
        self.y_input = ttk.Entry(basic_tab, textvariable=self.y_value, width=12)
        self.y_input.grid(row=0, column=5, sticky="ew", padx=(0, 18))
        ttk.Label(basic_tab, text="等待下限", style="Card.TLabel").grid(row=0, column=6, sticky="w", padx=(0, 8))
        self.wait_input = ttk.Entry(basic_tab, textvariable=self.wait_value, width=10)
        self.wait_input.grid(row=0, column=7, sticky="ew")

        ttk.Label(basic_tab, text="随机上限", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(12, 0))
        self.wait_max_input = ttk.Entry(basic_tab, textvariable=self.wait_max_value, width=10)
        self.wait_max_input.grid(row=1, column=1, sticky="ew", padx=(0, 18), pady=(12, 0))
        ttk.Label(basic_tab, text="重复次数", style="Card.TLabel").grid(row=1, column=2, sticky="w", padx=(0, 8), pady=(12, 0))
        self.step_repeat_input = ttk.Entry(basic_tab, textvariable=self.step_repeat_value, width=10)
        self.step_repeat_input.grid(row=1, column=3, sticky="ew", padx=(0, 18), pady=(12, 0))
        ttk.Label(basic_tab, text="失败重试", style="Card.TLabel").grid(row=1, column=4, sticky="w", padx=(0, 8), pady=(12, 0))
        self.retry_input = ttk.Entry(basic_tab, textvariable=self.retry_value, width=10)
        self.retry_input.grid(row=1, column=5, sticky="ew", padx=(0, 18), pady=(12, 0))
        ttk.Label(basic_tab, text="单步超时", style="Card.TLabel").grid(row=1, column=6, sticky="w", padx=(0, 8), pady=(12, 0))
        self.timeout_input = ttk.Entry(basic_tab, textvariable=self.timeout_value, width=10)
        self.timeout_input.grid(row=1, column=7, sticky="ew", pady=(12, 0))

        ttk.Label(position_tab, text="坐标模式", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.coordinate_mode_input = ttk.Combobox(position_tab, textvariable=self.coordinate_mode_value, values=tuple(COORDINATE_MODES.values()), state="readonly", width=18)
        self.coordinate_mode_input.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(0, 18))
        self.coordinate_mode_input.bind("<<ComboboxSelected>>", self._on_coordinate_mode_changed)
        ttk.Label(position_tab, text="显示器", style="Card.TLabel").grid(row=0, column=3, sticky="w", padx=(0, 8))
        self.display_input = ttk.Combobox(position_tab, textvariable=self.display_value, state="readonly")
        self.display_input.grid(row=0, column=4, columnspan=3, sticky="ew", padx=(0, 10))
        self.refresh_targets_button = ttk.Button(position_tab, text="刷新", command=self._refresh_desktop_targets)
        self.refresh_targets_button.grid(row=0, column=7, sticky="ew")
        ttk.Label(position_tab, text="目标窗口", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(12, 0))
        self.window_input = ttk.Combobox(position_tab, textvariable=self.window_value)
        self.window_input.grid(row=1, column=1, columnspan=5, sticky="ew", padx=(0, 18), pady=(12, 0))
        self.capture_button = ttk.Button(position_tab, text="⌖  3 秒后获取", command=self._start_capture)
        self.capture_button.grid(row=1, column=6, sticky="ew", padx=(0, 8), pady=(12, 0))
        self.preview_button = ttk.Button(position_tab, text="预览目标", command=self._show_preview)
        self.preview_button.grid(row=1, column=7, sticky="ew", pady=(12, 0))

        ttk.Label(safety_tab, text="执行条件", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.condition_input = ttk.Combobox(safety_tab, textvariable=self.condition_value, values=tuple(CONDITION_LABELS.values()), state="readonly", width=14)
        self.condition_input.grid(row=0, column=1, sticky="ew", padx=(0, 18))
        ttk.Label(safety_tab, text="条件值", style="Card.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.condition_parameter_input = ttk.Entry(safety_tab, textvariable=self.condition_parameter_value)
        self.condition_parameter_input.grid(row=0, column=3, sticky="ew", padx=(0, 18))
        ttk.Label(safety_tab, text="等待条件", style="Card.TLabel").grid(row=0, column=4, sticky="w", padx=(0, 8))
        self.condition_timeout_input = ttk.Entry(safety_tab, textvariable=self.condition_timeout_value, width=8)
        self.condition_timeout_input.grid(row=0, column=5, sticky="ew", padx=(0, 18))
        ttk.Label(safety_tab, text="成功 / 失败跳转", style="Card.TLabel").grid(row=0, column=6, sticky="w", padx=(0, 8))
        targets = ttk.Frame(safety_tab, style="Card.TFrame")
        targets.grid(row=0, column=7, sticky="ew")
        self.success_target_input = ttk.Entry(targets, textvariable=self.success_target_value, width=5)
        self.failure_target_input = ttk.Entry(targets, textvariable=self.failure_target_value, width=5)
        self.success_target_input.pack(side="left", fill="x", expand=True)
        self.failure_target_input.pack(side="left", fill="x", expand=True, padx=(6, 0))
        ttk.Label(safety_tab, text="点击前颜色", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(12, 0))
        self.expected_color_input = ttk.Entry(safety_tab, textvariable=self.expected_color_value)
        self.expected_color_input.grid(row=1, column=1, sticky="ew", padx=(0, 18), pady=(12, 0))
        ttk.Label(safety_tab, text="容差", style="Card.TLabel").grid(row=1, column=2, sticky="w", padx=(0, 8), pady=(12, 0))
        self.color_tolerance_input = ttk.Entry(safety_tab, textvariable=self.color_tolerance_value, width=8)
        self.color_tolerance_input.grid(row=1, column=3, sticky="ew", padx=(0, 18), pady=(12, 0))
        ttk.Label(safety_tab, text="允许区域", style="Card.TLabel").grid(row=1, column=4, sticky="w", padx=(0, 8), pady=(12, 0))
        self.allowed_region_input = ttk.Entry(safety_tab, textvariable=self.allowed_region_value)
        self.allowed_region_input.grid(row=1, column=5, columnspan=3, sticky="ew", pady=(12, 0))

        editor_actions = ttk.Frame(form_frame, style="Card.TFrame", padding=(12, 10))
        editor_actions.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(editor_actions, text="允许区域格式：X,Y,宽,高  ·  点击颜色格式：R,G,B", style="CardMuted.TLabel").pack(side="left")
        self.cancel_edit_button = ttk.Button(editor_actions, text="取消编辑", command=self._clear_form)
        self.cancel_edit_button.pack(side="right")
        self.save_step_button = ttk.Button(editor_actions, text="＋ 添加步骤", command=self._save_step, style="Accent.TButton")
        self.save_step_button.pack(side="right", padx=(0, 8))
        self.cancel_edit_button.state(["disabled"])

        steps_frame = ttk.LabelFrame(container, text="工作流步骤", padding=10)
        steps_frame.grid(row=3, column=0, sticky="nsew")
        steps_frame.columnconfigure(0, weight=1)
        steps_frame.rowconfigure(0, weight=1)

        columns = ("number", "action", "x", "y", "wait")
        self.steps_table = ttk.Treeview(
            steps_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=8,
        )
        headings = {
            "number": "步骤",
            "action": "操作",
            "x": "目标坐标",
            "y": "显示器 / 窗口",
            "wait": "执行前等待",
        }
        widths = {"number": 60, "action": 90, "x": 160, "y": 180, "wait": 130}
        for column in columns:
            self.steps_table.heading(column, text=headings[column])
            self.steps_table.column(
                column,
                width=widths[column],
                anchor="center",
                stretch=column == "wait",
            )
        self.steps_table.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            steps_frame, orient="vertical", command=self.steps_table.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.steps_table.configure(yscrollcommand=scrollbar.set)
        self.steps_table.tag_configure(
            "current_step", background="#2563eb", foreground="#ffffff"
        )
        self.steps_table.bind("<<TreeviewSelect>>", self._on_step_selected)
        self.steps_table.bind("<Double-1>", self._edit_selected_step)

        controls = ttk.Frame(steps_frame)
        controls.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.edit_button = ttk.Button(
            controls, text="编辑", command=self._edit_selected_step
        )
        self.delete_button = ttk.Button(
            controls, text="删除", command=self._delete_selected_step, style="Danger.TButton"
        )
        self.up_button = ttk.Button(
            controls, text="上移", command=lambda: self._move_selected_step(-1)
        )
        self.down_button = ttk.Button(
            controls, text="下移", command=lambda: self._move_selected_step(1)
        )
        for column, button in enumerate(
            (self.edit_button, self.delete_button, self.up_button, self.down_button)
        ):
            button.grid(row=0, column=column, padx=(0, 8))
            button.state(["disabled"])

        workflow_controls = ttk.Frame(steps_frame)
        workflow_controls.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Label(workflow_controls, text="整套循环次数").pack(side="left")
        self.workflow_repeat_input = ttk.Entry(
            workflow_controls, textvariable=self.workflow_repeat_value, width=7
        )
        self.workflow_repeat_input.pack(side="left", padx=(6, 12))
        self.infinite_loop_check = ttk.Checkbutton(
            workflow_controls, text="无限循环", variable=self.infinite_loop_value,
            command=self._toggle_infinite_loop,
        )
        self.infinite_loop_check.pack(side="left")
        self.load_button = ttk.Button(workflow_controls, text="载入 JSON", command=self._load_workflow)
        self.save_button = ttk.Button(workflow_controls, text="保存 JSON", command=self._save_workflow, style="Accent.TButton")
        self.save_button.pack(side="right")
        self.load_button.pack(side="right", padx=(0, 8))

        execution_frame = ttk.LabelFrame(container, text="执行控制", padding=10)
        execution_frame.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        for column in range(4):
            execution_frame.columnconfigure(column, weight=1)
        ttk.Label(execution_frame, textvariable=self.execution_status).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 8)
        )
        ttk.Label(execution_frame, textvariable=self.step_progress).grid(
            row=1, column=0, sticky="w", pady=(0, 8)
        )
        ttk.Label(execution_frame, textvariable=self.elapsed_display).grid(
            row=1, column=1, columnspan=2, sticky="w", pady=(0, 8)
        )
        ttk.Label(execution_frame, textvariable=self.completed_display).grid(
            row=1, column=3, sticky="e", pady=(0, 8)
        )
        self.start_button = ttk.Button(
            execution_frame, text="▶  开始执行", command=self._start_execution, style="Accent.TButton"
        )
        self.pause_button = ttk.Button(
            execution_frame, text="暂停", command=self._pause_execution
        )
        self.resume_button = ttk.Button(
            execution_frame, text="继续", command=self._resume_execution
        )
        self.stop_button = ttk.Button(
            execution_frame, text="■  停止", command=self._stop_execution, style="Danger.TButton"
        )
        for column, button in enumerate(
            (
                self.start_button,
                self.pause_button,
                self.resume_button,
                self.stop_button,
            )
        ):
            button.grid(row=2, column=column, padx=(0, 8), sticky="w")
        self._update_execution_buttons()

        permission_frame = ttk.Frame(container)
        permission_frame.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        permission_frame.columnconfigure(0, weight=1)

        ttk.Label(permission_frame, textvariable=self.permission_status).grid(
            row=0, column=0, sticky="w"
        )
        if platform.system() == "Darwin":
            ttk.Button(
                permission_frame,
                text="打开辅助功能设置",
                command=self._open_accessibility_settings,
            ).grid(row=0, column=1, padx=(10, 0))

    def _poll_mouse_position(self) -> None:
        try:
            position = pyautogui.position()
            self.live_position.set(f"X: {position.x:<5} Y: {position.y}")
        except Exception as error:  # PyAutoGUI exposes platform-specific errors.
            self.live_position.set("X: --    Y: --")
            self.capture_status.set(f"无法读取鼠标坐标：{error}")
        self._position_job = self.after(POLL_INTERVAL_MS, self._poll_mouse_position)

    def _refresh_desktop_targets(self) -> None:
        """Refresh displays/windows without changing a still-valid selection."""

        previous_display = self._selected_display_id()
        previous_window = self._selected_window_target()
        displays = self._desktop.displays()
        self._display_by_label = {
            f"{item.name} [{item.id}]  {item.bounds.width}×{item.bounds.height} @ {item.bounds.x},{item.bounds.y}": item
            for item in displays
        }
        self.display_input.configure(values=tuple(self._display_by_label))
        selected_display = next((label for label, item in self._display_by_label.items() if item.id == previous_display), None)
        if selected_display is None and self._display_by_label:
            primary = select_display(displays, None)
            selected_display = next(label for label, item in self._display_by_label.items() if item.id == primary.id)
        self.display_value.set(selected_display or "")

        windows = self._desktop.windows()
        self._window_by_label = {f"{item.label} [{item.id}]": item for item in windows}
        self.window_input.configure(values=tuple(self._window_by_label))
        selected_window = next((
            label for label, item in self._window_by_label.items()
            if item.id == previous_window or item.label == previous_window
        ), None)
        if selected_window:
            self.window_value.set(selected_window)
        self._on_coordinate_mode_changed()

    def _selected_display_id(self) -> str | None:
        item = self._display_by_label.get(self.display_value.get())
        return item.id if item else None

    def _selected_window_target(self) -> str | None:
        item = self._window_by_label.get(self.window_value.get())
        return item.label if item else self.window_value.get().strip() or None

    def _on_coordinate_mode_changed(self, _event: tk.Event | None = None) -> None:
        mode = LABEL_COORDINATE_MODES.get(self.coordinate_mode_value.get(), "absolute")
        self.display_input.state(["!disabled"] if mode == "display_percent" else ["disabled"])
        self.window_input.state(["!disabled"] if mode == "window" else ["disabled"])

    def _build_step_from_form(self, *, jumps: bool = True) -> Step:
        on_success = self._parse_jump_target(self.success_target_value.get(), "成功跳转") if jumps else None
        on_failure = self._parse_jump_target(self.failure_target_value.get(), "失败跳转") if jumps else None
        return validate_step_input(
            self.action_value.get(), self.x_value.get(), self.y_value.get(), self.wait_value.get(),
            repeat_text=self.step_repeat_value.get(), wait_max_text=self.wait_max_value.get(),
            condition=LABEL_CONDITIONS[self.condition_value.get()],
            condition_value=self.condition_parameter_value.get(),
            condition_timeout_text=self.condition_timeout_value.get(), retry_text=self.retry_value.get(),
            timeout_text=self.timeout_value.get(), on_success=on_success, on_failure=on_failure,
            coordinate_mode=LABEL_COORDINATE_MODES[self.coordinate_mode_value.get()],
            display_id=self._selected_display_id(), target_window=self._selected_window_target(),
            expected_color_text=self.expected_color_value.get(),
            color_tolerance_text=self.color_tolerance_value.get(),
            allowed_region_text=self.allowed_region_value.get(),
        )

    def _show_preview(self) -> None:
        try:
            step = self._build_step_from_form(jumps=False)
            image, marker, region = preview_region(step.action, self._desktop)
            image = image.convert("RGB")
            draw = ImageDraw.Draw(image)
            x, y = marker
            draw.ellipse((x - 8, y - 8, x + 8, y + 8), outline="#ff2d2d", width=3)
            draw.line((x - 14, y, x + 14, y), fill="#ff2d2d", width=2)
            draw.line((x, y - 14, x, y + 14), fill="#ff2d2d", width=2)
            image.thumbnail((800, 520))
            photo = ImageTk.PhotoImage(image)
        except Exception as error:
            messagebox.showerror("无法预览", str(error))
            return
        window = tk.Toplevel(self)
        window.title(f"目标预览 — {region.width}×{region.height} @ {region.x},{region.y}")
        ttk.Label(window, image=photo).pack(padx=12, pady=12)
        ttk.Label(window, text="红色十字为执行时重新解析的目标位置").pack(pady=(0, 12))
        window._preview_image = photo  # type: ignore[attr-defined]

    def _start_capture(self) -> None:
        if self._editor_locked or self._capture_job is not None:
            return
        self.capture_button.state(["disabled"])
        self._run_capture_countdown(CAPTURE_COUNTDOWN_SECONDS)

    def _run_capture_countdown(self, seconds_left: int) -> None:
        if seconds_left > 0:
            self.capture_status.set(
                f"请将鼠标移到目标位置，{seconds_left} 秒后获取坐标…"
            )
            self._capture_job = self.after(
                1000, self._run_capture_countdown, seconds_left - 1
            )
            return

        try:
            position = pyautogui.position()
            mode = LABEL_COORDINATE_MODES[self.coordinate_mode_value.get()]
            x, y = position.x, position.y
            if mode == "display_percent":
                display = select_display(self._desktop.displays(), self._selected_display_id())
                x = (position.x - display.bounds.x) * 100 / display.bounds.width
                y = (position.y - display.bounds.y) * 100 / display.bounds.height
                if not (0 <= x <= 100 and 0 <= y <= 100):
                    raise ValueError("鼠标不在所选显示器范围内。")
                self.x_value.set(f"{x:.4f}")
                self.y_value.set(f"{y:.4f}")
            elif mode == "window":
                target = select_window(self._desktop.windows(), self._selected_window_target())
                x, y = position.x - target.bounds.x, position.y - target.bounds.y
                self.x_value.set(str(x))
                self.y_value.set(str(y))
            else:
                self.x_value.set(str(x))
                self.y_value.set(str(y))
            self.capture_status.set(f"已获取坐标：X {self.x_value.get()}，Y {self.y_value.get()}")
        except Exception as error:
            messagebox.showerror("获取失败", f"无法获取鼠标坐标：\n{error}")
            self.capture_status.set("坐标获取失败")
        finally:
            self._capture_job = None
            self.capture_button.state(["!disabled"])

    def _save_step(self) -> None:
        if self._editor_locked:
            return
        try:
            step = self._build_step_from_form()
        except ValueError as error:
            messagebox.showerror("步骤内容有误", str(error))
            return

        if self._editing_index is None:
            self.steps.append(step)
            selected_index = len(self.steps) - 1
        else:
            selected_index = self._editing_index
            self.steps[selected_index] = replace(step, id=self.steps[selected_index].id)

        self._refresh_steps_table(selected_index)
        self._clear_form()

    def _parse_jump_target(self, text: str, name: str) -> str | None:
        """Resolve a user-facing number immediately to a stable step ID."""

        if not text.strip():
            return None
        try:
            target = int(text.strip())
        except ValueError as error:
            raise ValueError(f"{name}必须是步骤编号。") from error
        if not 1 <= target <= len(self.steps):
            raise ValueError(f"{name}必须指向已存在的步骤。")
        return self.steps[target - 1].id

    def _selected_step_index(self) -> int | None:
        selection = self.steps_table.selection()
        if not selection:
            return None
        return int(selection[0].removeprefix("step-"))

    def _refresh_steps_table(self, selected_index: int | None = None) -> None:
        for item in self.steps_table.get_children():
            self.steps_table.delete(item)
        for index, step in enumerate(self.steps):
            wait_display = f"{step.wait_seconds:g}"
            if step.wait_max_seconds is not None:
                wait_display += f"–{step.wait_max_seconds:g}"
            if step.repeat_count > 1:
                wait_display += f" 秒 × {step.repeat_count}"
            else:
                wait_display += " 秒"
            coordinate_display = f"{step.x:g}, {step.y:g}"
            if step.action.coordinate_mode == "display_percent":
                coordinate_display = f"{step.x:g}%, {step.y:g}%"
            elif step.action.coordinate_mode == "window":
                coordinate_display = f"窗口+{step.x:g}, {step.y:g}"
            self.steps_table.insert(
                "",
                "end",
                iid=f"step-{index}",
                values=(
                    index + 1,
                    ACTION_LABELS[step.action_type],
                    coordinate_display,
                    step.action.display_id or step.action.target_window or "—",
                    wait_display,
                ),
            )
        if selected_index is not None and 0 <= selected_index < len(self.steps):
            item_id = f"step-{selected_index}"
            self.steps_table.selection_set(item_id)
            self.steps_table.focus(item_id)
            self.steps_table.see(item_id)
        self._update_step_buttons()

    def _on_step_selected(self, _event: tk.Event | None = None) -> None:
        selected_index = self._selected_step_index()
        if (
            self._editing_index is not None
            and selected_index != self._editing_index
        ):
            self._clear_form()
        self._update_step_buttons()

    def _update_step_buttons(self) -> None:
        index = self._selected_step_index()
        has_selection = index is not None and not self._editor_locked
        for button in (self.edit_button, self.delete_button):
            button.state(["!disabled"] if has_selection else ["disabled"])
        self.up_button.state(
            ["!disabled"]
            if not self._editor_locked and index is not None and index > 0
            else ["disabled"]
        )
        self.down_button.state(
            ["!disabled"]
            if not self._editor_locked
            and index is not None
            and index < len(self.steps) - 1
            else ["disabled"]
        )

    def _edit_selected_step(self, _event: tk.Event | None = None) -> None:
        if self._editor_locked:
            return
        index = self._selected_step_index()
        if index is None:
            messagebox.showinfo("请选择步骤", "请先在列表中选择需要编辑的步骤。")
            return
        step = self.steps[index]
        self._editing_index = index
        self.action_value.set(ACTION_LABELS[step.action_type])
        self.x_value.set(str(step.x))
        self.y_value.set(str(step.y))
        self.coordinate_mode_value.set(COORDINATE_MODES[step.action.coordinate_mode])
        display_label = next((label for label, item in self._display_by_label.items() if item.id == step.action.display_id), "")
        self.display_value.set(display_label)
        window_label = next((label for label, item in self._window_by_label.items() if item.label == step.action.target_window or item.id == step.action.target_window), step.action.target_window or "")
        self.window_value.set(window_label)
        self.expected_color_value.set("" if step.action.expected_color is None else ",".join(map(str, step.action.expected_color)))
        self.color_tolerance_value.set(str(step.action.color_tolerance))
        region = step.action.allowed_region
        self.allowed_region_value.set("" if region is None else f"{region.x},{region.y},{region.width},{region.height}")
        self._on_coordinate_mode_changed()
        self.wait_value.set(f"{step.wait_seconds:g}")
        self.wait_max_value.set(
            "" if step.wait_max_seconds is None else f"{step.wait_max_seconds:g}"
        )
        self.step_repeat_value.set(str(step.repeat_count))
        self.condition_value.set(CONDITION_LABELS[step.condition_type])
        self.condition_parameter_value.set(step.condition_value)
        self.condition_timeout_value.set(f"{step.condition_timeout_seconds:g}")
        self.retry_value.set(str(step.retry_count))
        self.timeout_value.set(
            "" if step.timeout_seconds is None else f"{step.timeout_seconds:g}"
        )
        ids = [item.id for item in self.steps]
        self.success_target_value.set("" if step.on_success is None else str(ids.index(step.on_success) + 1))
        self.failure_target_value.set("" if step.on_failure is None else str(ids.index(step.on_failure) + 1))
        self.form_frame.configure(text=f"编辑第 {index + 1} 步")
        self.save_step_button.configure(text="保存修改")
        self.cancel_edit_button.state(["!disabled"])

    def _delete_selected_step(self) -> None:
        if self._editor_locked:
            return
        index = self._selected_step_index()
        if index is None:
            messagebox.showinfo("请选择步骤", "请先在列表中选择需要删除的步骤。")
            return
        deleted_id = self.steps[index].id
        del self.steps[index]
        self.steps = [
            replace(
                step,
                on_success=None if step.on_success == deleted_id else step.on_success,
                on_failure=None if step.on_failure == deleted_id else step.on_failure,
            )
            for step in self.steps
        ]
        self._clear_form()
        next_index = min(index, len(self.steps) - 1) if self.steps else None
        self._refresh_steps_table(next_index)

    def _move_selected_step(self, offset: int) -> None:
        if self._editor_locked:
            return
        index = self._selected_step_index()
        if index is None:
            messagebox.showinfo("请选择步骤", "请先在列表中选择需要移动的步骤。")
            return
        target_index = index + offset
        if not 0 <= target_index < len(self.steps):
            return
        self.steps[index], self.steps[target_index] = (
            self.steps[target_index],
            self.steps[index],
        )
        self._clear_form()
        self._refresh_steps_table(target_index)

    def _clear_form(self) -> None:
        self._editing_index = None
        self.action_value.set(ACTION_LABELS["move"])
        self.x_value.set("")
        self.y_value.set("")
        self.coordinate_mode_value.set(COORDINATE_MODES["absolute"])
        self.expected_color_value.set("")
        self.color_tolerance_value.set("0")
        self.allowed_region_value.set("")
        self.window_value.set("")
        self._on_coordinate_mode_changed()
        self.wait_value.set("0.5")
        self.wait_max_value.set("")
        self.step_repeat_value.set("1")
        self.condition_value.set(CONDITION_LABELS["always"])
        self.condition_parameter_value.set("")
        self.condition_timeout_value.set("0")
        self.retry_value.set("0")
        self.timeout_value.set("")
        self.success_target_value.set("")
        self.failure_target_value.set("")
        self.form_frame.configure(text="添加操作步骤")
        self.save_step_button.configure(text="添加步骤")
        self.cancel_edit_button.state(["disabled"])

    def _toggle_infinite_loop(self) -> None:
        self.workflow_repeat_input.state(
            ["disabled"] if self.infinite_loop_value.get() else ["!disabled"]
        )

    def _current_workflow(self) -> Workflow:
        if self.infinite_loop_value.get():
            repeat_count = None
        else:
            try:
                repeat_count = int(self.workflow_repeat_value.get().strip())
            except ValueError as error:
                raise ValueError("整套流程循环次数必须是整数。") from error
        workflow = Workflow(tuple(self.steps), repeat_count)
        validate_workflow(workflow)
        return workflow

    def _save_workflow(self) -> None:
        if self._editor_locked:
            return
        try:
            workflow = self._current_workflow()
        except ValueError as error:
            messagebox.showerror("无法保存", str(error))
            return
        path = filedialog.asksaveasfilename(
            title="保存 MacClickPath 工作流",
            defaultextension=".json",
            filetypes=(("JSON 文件", "*.json"), ("所有文件", "*.*")),
        )
        if not path:
            return
        try:
            save_workflow(path, workflow)
        except (OSError, ValueError) as error:
            messagebox.showerror("保存失败", str(error))
            return
        messagebox.showinfo("保存成功", "工作流已保存。")

    def _load_workflow(self) -> None:
        if self._editor_locked:
            return
        path = filedialog.askopenfilename(
            title="载入 MacClickPath 工作流",
            filetypes=(("JSON 文件", "*.json"), ("所有文件", "*.*")),
        )
        if not path:
            return
        try:
            workflow = load_workflow(path)
        except ValueError as error:
            messagebox.showerror("载入失败", str(error))
            return
        self.steps = list(workflow.steps)
        self.infinite_loop_value.set(workflow.repeat_count is None)
        if workflow.repeat_count is not None:
            self.workflow_repeat_value.set(str(workflow.repeat_count))
        self._toggle_infinite_loop()
        self._clear_form()
        self._refresh_steps_table()

    def _start_execution(self) -> None:
        if self._execution_state in {
            ExecutionState.COUNTDOWN,
            ExecutionState.RUNNING,
            ExecutionState.PAUSED,
            ExecutionState.STOPPING,
        }:
            return
        if self._capture_job is not None:
            messagebox.showinfo("正在获取坐标", "请等待坐标获取完成后再开始。")
            return
        if self._editing_index is not None:
            messagebox.showinfo("步骤尚未保存", "请先保存修改或取消编辑。")
            return
        try:
            workflow = self._current_workflow()
        except ValueError as error:
            messagebox.showerror("无法开始", str(error))
            return

        permission = get_accessibility_permission()
        if permission is AccessibilityPermission.DENIED:
            messagebox.showerror(
                "无法开始",
                "尚未获得 macOS 辅助功能权限，请授权后再运行。",
            )
            self._refresh_permission_status()
            return

        self._stop_event.clear()
        self._workflow_repeat_count = workflow.repeat_count
        self._reset_run_statistics()
        self._execution_state = ExecutionState.COUNTDOWN
        self._set_editor_locked(True)
        self._update_execution_buttons()
        self._run_start_countdown(START_COUNTDOWN_SECONDS)

    def _run_start_countdown(self, seconds_left: int) -> None:
        if self._stop_event.is_set():
            self._finish_execution(ExecutionState.STOPPED, "执行状态：停止")
            return
        if seconds_left > 0:
            self.execution_status.set(f"执行状态：倒计时（{seconds_left} 秒）")
            self._countdown_job = self.after(
                1000, self._run_start_countdown, seconds_left - 1
            )
            return

        self._countdown_job = None
        self._execution_state = ExecutionState.RUNNING
        self.execution_status.set("执行状态：运行")
        self._running_started_at = time.monotonic()
        self._update_execution_buttons()
        workflow = Workflow(tuple(self.steps), self._workflow_repeat_count)
        self._runner = WorkflowRunner(
            workflow,
            self._execution_queue.put,
            action_executor=DirectActionExecutor(lambda action: perform_action(action)),
        )
        self._execution_thread = self._runner.start()

    def _pause_execution(self) -> None:
        if self._execution_state is not ExecutionState.RUNNING:
            return
        if self._runner is not None:
            self._runner.pause()
        self._freeze_elapsed_clock()
        self._execution_state = ExecutionState.PAUSED
        self.execution_status.set("执行状态：暂停")
        self._update_execution_buttons()

    def _resume_execution(self) -> None:
        if self._execution_state is not ExecutionState.PAUSED:
            return
        if self._runner is not None:
            self._runner.resume()
        self._running_started_at = time.monotonic()
        self._execution_state = ExecutionState.RUNNING
        self.execution_status.set("执行状态：运行")
        self._update_execution_buttons()

    def _stop_execution(self) -> None:
        if self._execution_state is ExecutionState.COUNTDOWN:
            self._stop_event.set()
            if self._countdown_job is not None:
                self.after_cancel(self._countdown_job)
                self._countdown_job = None
            self._finish_execution(ExecutionState.STOPPED, "执行状态：停止")
            return
        if self._execution_state not in {
            ExecutionState.RUNNING,
            ExecutionState.PAUSED,
        }:
            return
        self._execution_state = ExecutionState.STOPPING
        self.execution_status.set("执行状态：正在停止…")
        if self._runner is not None:
            self._runner.cancel()
        self._update_execution_buttons()

    def _poll_execution_messages(self) -> None:
        try:
            while True:
                runner_event = self._execution_queue.get_nowait()
                event = runner_event.type
                if event == "step_started":
                    self._current_step_number = runner_event.step_number or 0
                    self.step_progress.set(
                        f"当前步骤：{self._current_step_number} / {self._total_steps}"
                    )
                    self._highlight_current_step(self._current_step_number - 1)
                elif event == "step_completed":
                    self._completed_operations = runner_event.completed_operations or 0
                    self.completed_display.set(
                        f"已完成操作：{self._completed_operations} 次"
                    )
                elif event == "step_retry":
                    self.execution_status.set(f"执行状态：运行 — {runner_event.message}")
                elif event == "completed":
                    self._finish_execution(
                        ExecutionState.COMPLETED, "执行状态：完成"
                    )
                elif event == "stopped":
                    self._finish_execution(
                        ExecutionState.STOPPED, "执行状态：停止"
                    )
                elif event == "error":
                    error_message = runner_event.message or "未知错误"
                    self._finish_execution(
                        ExecutionState.ERROR,
                        f"执行状态：错误 — {error_message}",
                    )
                    messagebox.showerror("执行失败", error_message)
        except queue.Empty:
            pass
        self._refresh_elapsed_display()
        self._execution_poll_job = self.after(100, self._poll_execution_messages)

    def _finish_execution(self, state: ExecutionState, status: str) -> None:
        self._freeze_elapsed_clock()
        self._execution_state = state
        self._execution_thread = None
        self._runner = None
        self.execution_status.set(status)
        self._set_editor_locked(False)
        self._update_execution_buttons()

    def _reset_run_statistics(self) -> None:
        self._total_steps = len(self.steps)
        self._current_step_number = 0
        self._completed_operations = 0
        self._elapsed_accumulated = 0.0
        self._running_started_at = None
        self.step_progress.set(f"当前步骤：0 / {self._total_steps}")
        self.completed_display.set("已完成操作：0 次")
        self.elapsed_display.set("运行时间：00:00:00")
        self._highlight_current_step(None)

    def _freeze_elapsed_clock(self) -> None:
        if self._running_started_at is not None:
            self._elapsed_accumulated += time.monotonic() - self._running_started_at
            self._running_started_at = None
        self._refresh_elapsed_display()

    def _refresh_elapsed_display(self) -> None:
        elapsed = self._elapsed_accumulated
        if self._running_started_at is not None:
            elapsed += time.monotonic() - self._running_started_at
        self.elapsed_display.set(f"运行时间：{format_elapsed(elapsed)}")

    def _highlight_current_step(self, index: int | None) -> None:
        for item_id in self.steps_table.get_children():
            self.steps_table.item(item_id, tags=())
        if index is None:
            return
        item_id = f"step-{index}"
        if self.steps_table.exists(item_id):
            self.steps_table.item(item_id, tags=("current_step",))
            self.steps_table.see(item_id)

    def _set_editor_locked(self, locked: bool) -> None:
        self._editor_locked = locked
        self.action_input.configure(state="disabled" if locked else "readonly")
        self.condition_input.configure(state="disabled" if locked else "readonly")
        self.coordinate_mode_input.configure(state="disabled" if locked else "readonly")
        self.display_input.configure(state="disabled" if locked else "readonly")
        self.window_input.configure(state="disabled" if locked else "normal")
        for widget in (
            self.x_input,
            self.y_input,
            self.wait_input,
            self.wait_max_input,
            self.step_repeat_input,
            self.retry_input,
            self.timeout_input,
            self.condition_parameter_input,
            self.condition_timeout_input,
            self.success_target_input,
            self.failure_target_input,
            self.expected_color_input,
            self.color_tolerance_input,
            self.allowed_region_input,
            self.workflow_repeat_input,
            self.steps_table,
        ):
            widget.state(["disabled"] if locked else ["!disabled"])
        for button in (
            self.capture_button,
            self.preview_button,
            self.refresh_targets_button,
            self.save_step_button,
            self.load_button,
            self.save_button,
            self.infinite_loop_check,
        ):
            button.state(["disabled"] if locked else ["!disabled"])
        if not locked:
            self._toggle_infinite_loop()
            self._on_coordinate_mode_changed()
        if locked or self._editing_index is None:
            self.cancel_edit_button.state(["disabled"])
        else:
            self.cancel_edit_button.state(["!disabled"])
        self._update_step_buttons()

    def _update_execution_buttons(self) -> None:
        state = self._execution_state
        active = state in {
            ExecutionState.COUNTDOWN,
            ExecutionState.RUNNING,
            ExecutionState.PAUSED,
            ExecutionState.STOPPING,
        }
        self.start_button.state(["disabled"] if active else ["!disabled"])
        self.pause_button.state(
            ["!disabled"] if state is ExecutionState.RUNNING else ["disabled"]
        )
        self.resume_button.state(
            ["!disabled"] if state is ExecutionState.PAUSED else ["disabled"]
        )
        self.stop_button.state(
            ["!disabled"]
            if state
            in {
                ExecutionState.COUNTDOWN,
                ExecutionState.RUNNING,
                ExecutionState.PAUSED,
            }
            else ["disabled"]
        )

    def _refresh_permission_status(self, *, show_warning: bool = False) -> None:
        permission = get_accessibility_permission()
        if permission is AccessibilityPermission.GRANTED:
            self.permission_status.set("辅助功能权限：已授权")
        elif permission is AccessibilityPermission.DENIED:
            self.permission_status.set("辅助功能权限：未授权，鼠标操作将无法执行")
            if show_warning:
                messagebox.showwarning(
                    "需要辅助功能权限",
                    "程序需要 macOS 辅助功能权限才能移动和点击鼠标。\n\n"
                    "请在“系统设置 → 隐私与安全性 → 辅助功能”中授权当前的"
                    " Terminal、Python 或打包后的应用。",
                )
        elif permission is AccessibilityPermission.NOT_MACOS:
            self.permission_status.set("辅助功能权限：仅支持在 macOS 上检查")
        else:
            self.permission_status.set(
                "辅助功能权限：检测失败，请打开系统设置手动确认"
            )

    def _open_accessibility_settings(self) -> None:
        if not open_accessibility_settings():
            messagebox.showerror(
                "无法打开系统设置",
                "请手动打开“系统设置 → 隐私与安全性 → 辅助功能”。",
            )
            return
        self.after(1000, self._refresh_permission_status)

    def _on_focus_in(self, _event: tk.Event) -> None:
        """Refresh permission state after returning from System Settings."""

        self._refresh_permission_status()

    def _on_close(self) -> None:
        self._stop_event.set()
        if self._runner is not None:
            self._runner.cancel()
        if self._capture_job is not None:
            self.after_cancel(self._capture_job)
        if self._position_job is not None:
            self.after_cancel(self._position_job)
        if self._countdown_job is not None:
            self.after_cancel(self._countdown_job)
        if self._execution_poll_job is not None:
            self.after_cancel(self._execution_poll_job)
        self.destroy()


def main() -> None:
    app = ClickFlowApp()
    app.mainloop()


if __name__ == "__main__":
    main()
