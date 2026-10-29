"""실제 Windows Tk 위젯의 선택·입력 상태와 갱신 타이머를 점검합니다.

등록한 서버 주소는 반드시 example.invalid이며 AirWave에 접속하지 않습니다.
"""

from __future__ import annotations

import os
import time
import tkinter as tk
from tkinter import ttk

import pytest

from airwave_csv import gui
from airwave_csv.multi_config import MultiConfig, add_server, registry_path, save_v2


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows tkinter UI 전용")


def _setup_real_window(tmp_path, monkeypatch):
    cfg = MultiConfig(export_root=str(tmp_path / "exports"))
    for i in range(1, 4):
        add_server(
            cfg, name=f"AirWave {i}",
            url=f"https://synthetic-{i}.example.invalid", username="dummy-user",
        )
    save_v2(cfg, registry_path(tmp_path))
    monkeypatch.setattr(gui, "app_home", lambda: tmp_path)
    monkeypatch.setattr(gui, "task_status", lambda: "Ready")
    window = gui.ExporterWindow()
    window.withdraw()
    window.update()
    return window


def _find_entry_for_variable(widget, variable):
    for child in widget.winfo_children():
        if isinstance(child, ttk.Entry):
            if str(child.cget("textvariable")) == str(variable):
                return child
        found = _find_entry_for_variable(child, variable)
        if found is not None:
            return found
    return None


def test_real_windows_tk_entry_keeps_unsaved_value_and_selected_row(tmp_path, monkeypatch):
    window = _setup_real_window(tmp_path, monkeypatch)
    try:
        server_id = "airwave-01"
        window.table.selection_set(server_id)
        window.table.event_generate("<<TreeviewSelect>>")
        window.update()
        assert window.name_var.get() == "AirWave 1"

        input_field = _find_entry_for_variable(window, window.name_var)
        assert input_field is not None
        input_field.delete(0, tk.END)
        input_field.insert(0, "아직 저장하지 않은 편집값")
        assert input_field.get() == "아직 저장하지 않은 편집값"
        selected = window.table.selection()

        # 실제 Tk 루프를 2초 이상 순환시켜 자동 refresh도 실행합니다.
        until = time.monotonic() + 2.3
        while time.monotonic() < until:
            window.update()
            time.sleep(0.04)
        assert window.table.selection() == selected
        assert input_field.get() == "아직 저장하지 않은 편집값"
        assert window.name_var.get() == "아직 저장하지 않은 편집값"
    finally:
        window.destroy()


def test_real_windows_tk_repeated_refresh_keeps_single_timer(tmp_path, monkeypatch):
    window = _setup_real_window(tmp_path, monkeypatch)
    try:
        expected = tuple(window.tk.call("after", "info"))
        assert len(expected) == 1
        for _ in range(7):
            window.refresh()
            window.update_idletasks()
        pending = tuple(window.tk.call("after", "info"))
        assert pending == expected
        assert len(window.table.get_children()) == 3
    finally:
        window.destroy()
