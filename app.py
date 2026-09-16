"""ClickFlow desktop application."""

from __future__ import annotations

import platform
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

import pyautogui

from clickflow import (
    ACTION_LABELS,
    AccessibilityPermission,
    ExecutionState,
    Step,
    format_elapsed,
    get_accessibility_permission,
    open_accessibility_settings,
    perform_action,
    validate_step_input,
    validate_step_sequence,
)

POLL_INTERVAL_MS = 100
CAPTURE_COUNTDOWN_SECONDS = 3
START_COUNTDOWN_SECONDS = 3
class ClickFlowApp(tk.Tk):
    """Main desktop window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("ClickFlow")
        self.geometry("760x730")
        self.minsize(680, 670)

        self.live_position = tk.StringVar(value="X: --    Y: --")
        self.capture_status = tk.StringVar(value="移动鼠标可实时查看坐标")
        self.action_value = tk.StringVar(value=ACTION_LABELS["move"])
        self.x_value = tk.StringVar()
        self.y_value = tk.StringVar()
        self.wait_value = tk.StringVar(value="0.5")
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
        self._run_event = threading.Event()
        self._run_event.set()
        self._execution_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()

        self._build_window()
        self._refresh_permission_status(show_warning=True)
        self._poll_mouse_position()
        self._poll_execution_messages()
        self.bind("<FocusIn>", self._on_focus_in)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_window(self) -> None:
        container = ttk.Frame(self, padding=20)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(3, weight=1)

        title = ttk.Label(
            container,
            text="鼠标操作设置",
            font=("TkDefaultFont", 18, "bold"),
        )
        title.grid(row=0, column=0, sticky="w", pady=(0, 16))

        position_frame = ttk.LabelFrame(container, text="当前鼠标坐标", padding=14)
        position_frame.grid(row=1, column=0, sticky="ew")
        position_frame.columnconfigure(0, weight=1)

        ttk.Label(
            position_frame,
            textvariable=self.live_position,
            font=("TkFixedFont", 16, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(position_frame, textvariable=self.capture_status).grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )

        form_frame = ttk.LabelFrame(container, text="添加操作步骤", padding=14)
        self.form_frame = form_frame
        form_frame.grid(row=2, column=0, sticky="ew", pady=14)
        form_frame.columnconfigure(3, weight=1)
        form_frame.columnconfigure(5, weight=1)
        form_frame.columnconfigure(7, weight=1)

        ttk.Label(form_frame, text="操作").grid(row=0, column=0, padx=(0, 6))
        self.action_input = ttk.Combobox(
            form_frame,
            textvariable=self.action_value,
            values=tuple(ACTION_LABELS.values()),
            state="readonly",
            width=7,
        )
        self.action_input.grid(row=0, column=1, sticky="ew", padx=(0, 14))
        ttk.Label(form_frame, text="X").grid(row=0, column=2, padx=(0, 6))
        self.x_input = ttk.Entry(form_frame, textvariable=self.x_value, width=12)
        self.x_input.grid(row=0, column=3, sticky="ew", padx=(0, 14))
        ttk.Label(form_frame, text="Y").grid(row=0, column=4, padx=(0, 6))
        self.y_input = ttk.Entry(form_frame, textvariable=self.y_value, width=12)
        self.y_input.grid(row=0, column=5, sticky="ew", padx=(0, 14))
        ttk.Label(form_frame, text="等待(秒)").grid(
            row=0, column=6, padx=(0, 6)
        )
        self.wait_input = ttk.Entry(
            form_frame, textvariable=self.wait_value, width=10
        )
        self.wait_input.grid(row=0, column=7, sticky="ew")
        self.capture_button = ttk.Button(
            form_frame, text="3 秒后获取", command=self._start_capture
        )
        self.capture_button.grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(12, 0)
        )
        self.save_step_button = ttk.Button(
            form_frame, text="添加步骤", command=self._save_step
        )
        self.save_step_button.grid(row=1, column=6, sticky="e", pady=(12, 0))
        self.cancel_edit_button = ttk.Button(
            form_frame, text="取消编辑", command=self._clear_form
        )
        self.cancel_edit_button.grid(row=1, column=7, sticky="e", pady=(12, 0))
        self.cancel_edit_button.state(["disabled"])

        steps_frame = ttk.LabelFrame(container, text="操作步骤", padding=10)
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
            "x": "X",
            "y": "Y",
            "wait": "执行前等待",
        }
        widths = {"number": 60, "action": 100, "x": 100, "y": 100, "wait": 130}
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
            controls, text="删除", command=self._delete_selected_step
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
            execution_frame, text="开始", command=self._start_execution
        )
        self.pause_button = ttk.Button(
            execution_frame, text="暂停", command=self._pause_execution
        )
        self.resume_button = ttk.Button(
            execution_frame, text="继续", command=self._resume_execution
        )
        self.stop_button = ttk.Button(
            execution_frame, text="停止", command=self._stop_execution
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
            self.x_value.set(str(position.x))
            self.y_value.set(str(position.y))
            self.capture_status.set(f"已获取坐标：X {position.x}，Y {position.y}")
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
            step = validate_step_input(
                self.action_value.get(),
                self.x_value.get(),
                self.y_value.get(),
                self.wait_value.get(),
            )
        except ValueError as error:
            messagebox.showerror("步骤内容有误", str(error))
            return

        if self._editing_index is None:
            self.steps.append(step)
            selected_index = len(self.steps) - 1
        else:
            selected_index = self._editing_index
            self.steps[selected_index] = step

        self._refresh_steps_table(selected_index)
        self._clear_form()

    def _selected_step_index(self) -> int | None:
        selection = self.steps_table.selection()
        if not selection:
            return None
        return int(selection[0].removeprefix("step-"))

    def _refresh_steps_table(self, selected_index: int | None = None) -> None:
        for item in self.steps_table.get_children():
            self.steps_table.delete(item)
        for index, step in enumerate(self.steps):
            self.steps_table.insert(
                "",
                "end",
                iid=f"step-{index}",
                values=(
                    index + 1,
                    ACTION_LABELS[step.action],
                    step.x,
                    step.y,
                    f"{step.wait_seconds:g} 秒",
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
        self.action_value.set(ACTION_LABELS[step.action])
        self.x_value.set(str(step.x))
        self.y_value.set(str(step.y))
        self.wait_value.set(f"{step.wait_seconds:g}")
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
        del self.steps[index]
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
        self.wait_value.set("0.5")
        self.form_frame.configure(text="添加操作步骤")
        self.save_step_button.configure(text="添加步骤")
        self.cancel_edit_button.state(["disabled"])

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
            validate_step_sequence(self.steps)
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
        self._run_event.set()
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
        steps_snapshot = list(self.steps)
        self._execution_thread = threading.Thread(
            target=self._run_steps,
            args=(steps_snapshot,),
            name="mouse-step-runner",
            daemon=True,
        )
        self._execution_thread.start()

    def _run_steps(self, steps: list[Step]) -> None:
        try:
            for step_number, step in enumerate(steps, start=1):
                self._execution_queue.put(("step_started", str(step_number)))
                if not self._wait_interruptibly(step.wait_seconds):
                    self._execution_queue.put(("stopped", None))
                    return
                if not self._wait_until_resumed():
                    self._execution_queue.put(("stopped", None))
                    return
                perform_action(step)
                self._execution_queue.put(("step_completed", str(step_number)))
            self._execution_queue.put(("completed", None))
        except pyautogui.FailSafeException:
            self._execution_queue.put(
                ("error", "已触发左上角紧急停止，执行已终止。")
            )
        except Exception as error:
            self._execution_queue.put(
                ("error", f"{type(error).__name__}: {error}")
            )

    def _wait_until_resumed(self) -> bool:
        while not self._run_event.wait(0.05):
            if self._stop_event.is_set():
                return False
        return not self._stop_event.is_set()

    def _wait_interruptibly(self, duration: float) -> bool:
        remaining = duration
        last_tick = time.monotonic()
        while remaining > 0:
            if self._stop_event.is_set():
                return False
            if not self._run_event.is_set():
                if not self._wait_until_resumed():
                    return False
                last_tick = time.monotonic()
                continue

            wait_slice = min(0.05, remaining)
            if self._stop_event.wait(wait_slice):
                return False
            now = time.monotonic()
            if self._run_event.is_set():
                remaining -= now - last_tick
            last_tick = now
        return not self._stop_event.is_set()

    def _pause_execution(self) -> None:
        if self._execution_state is not ExecutionState.RUNNING:
            return
        self._run_event.clear()
        self._freeze_elapsed_clock()
        self._execution_state = ExecutionState.PAUSED
        self.execution_status.set("执行状态：暂停")
        self._update_execution_buttons()

    def _resume_execution(self) -> None:
        if self._execution_state is not ExecutionState.PAUSED:
            return
        self._run_event.set()
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
        self._stop_event.set()
        self._run_event.set()
        self._update_execution_buttons()

    def _poll_execution_messages(self) -> None:
        try:
            while True:
                event, detail = self._execution_queue.get_nowait()
                if event == "step_started":
                    self._current_step_number = int(detail or 0)
                    self.step_progress.set(
                        f"当前步骤：{self._current_step_number} / {self._total_steps}"
                    )
                    self._highlight_current_step(self._current_step_number - 1)
                elif event == "step_completed":
                    self._completed_operations = int(detail or 0)
                    self.completed_display.set(
                        f"已完成操作：{self._completed_operations} 次"
                    )
                elif event == "completed":
                    self._finish_execution(
                        ExecutionState.COMPLETED, "执行状态：完成"
                    )
                elif event == "stopped":
                    self._finish_execution(
                        ExecutionState.STOPPED, "执行状态：停止"
                    )
                elif event == "error":
                    error_message = detail or "未知错误"
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
        for widget in (self.x_input, self.y_input, self.wait_input, self.steps_table):
            widget.state(["disabled"] if locked else ["!disabled"])
        for button in (self.capture_button, self.save_step_button):
            button.state(["disabled"] if locked else ["!disabled"])
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
        self._run_event.set()
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
