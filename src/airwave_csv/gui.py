"""한국어 다중 AirWave 관리 UI. Windows 예약과 각 서버 실행을 별도 프로세스로 시작."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import SELECTOR_TEMPLATE, app_home
from .credentials import CredentialError, CredentialStore
from .events import read_last_batch
from .gui_model import change_server, remove_server, schedule_check_due, set_enabled
from .migration import migrate_if_needed
from .multi_config import (
    add_server, registry_path, save_v2, validate_settings,
)
from .paths import server_selectors_path
from .scheduler import ScheduleError, register_daily, task_status, unregister_daily


class ExporterWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AirWave CSV Exporter - 다중 서버")
        self.geometry("960x700")
        self.minsize(800, 610)
        try:
            self.settings = migrate_if_needed(app_home())
        except (OSError, ValueError, TypeError):
            messagebox.showerror("설정 오류", "기존 설정을 읽을 수 없습니다. 오류를 수정하세요.")
            self.destroy()
            return
        self.time_var = tk.StringVar(value=self.settings.schedule_time)
        self.parallel_var = tk.StringVar(value=str(self.settings.parallel_limit))
        self.dir_var = tk.StringVar(value=self.settings.export_root)
        self.name_var = tk.StringVar()
        self.url_var = tk.StringVar()
        self.user_var = tk.StringVar()
        self.pass_var = tk.StringVar()
        self.enabled_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="서버를 선택하거나 추가하세요.")
        self._last_schedule_check: float | None = None
        self._cached_schedule_status = "확인 전"
        self._build()
        self.refresh()

    def _build(self):
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="AirWave 장비 목록 CSV 자동 수집",
                  font=("맑은 고딕", 14, "bold")).pack(anchor="w")
        ttk.Label(root, text="최대 5대 등록 · 기본 3대 병렬 실행 · 추가 서버는 대기열",
                  ).pack(anchor="w", pady=(4, 10))
        schedule = ttk.LabelFrame(root, text="전체 예약 설정", padding=10)
        schedule.pack(fill="x")
        ttk.Label(schedule, text="매일 실행").grid(row=0, column=0, padx=5)
        ttk.Entry(schedule, textvariable=self.time_var, width=9).grid(row=0, column=1)
        ttk.Label(schedule, text="동시 실행").grid(row=0, column=2, padx=(18, 5))
        ttk.Combobox(schedule, textvariable=self.parallel_var,
                     values=[str(n) for n in range(1, 6)],
                     state="readonly", width=6).grid(row=0, column=3)
        ttk.Label(schedule, text="CSV 상위 폴더").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Entry(schedule, textvariable=self.dir_var, width=68).grid(
            row=1, column=1, columnspan=4, sticky="ew", pady=8)
        ttk.Button(schedule, text="찾기", command=self.choose_dir).grid(row=1, column=5)
        ttk.Button(schedule, text="설정 저장", command=self.save).grid(row=0, column=4, padx=5)
        ttk.Button(schedule, text="예약 등록/변경", command=self.register).grid(
            row=0, column=5, padx=5)
        ttk.Button(schedule, text="예약 해제", command=self.unregister).grid(
            row=0, column=6, padx=5)
        schedule.columnconfigure(4, weight=1)

        table_frame = ttk.LabelFrame(root, text="서버 목록 (선택 후 수정·개별 테스트)", padding=10)
        table_frame.pack(fill="both", expand=True, pady=(12, 7))
        cols = ("name", "enabled", "state", "rows", "download")
        self.table = ttk.Treeview(table_frame, columns=cols, show="tree headings",
                                  height=8, selectmode="browse")
        self.table.heading("#0", text="서버 ID")
        self.table.heading("name", text="AirWave 이름")
        self.table.heading("enabled", text="활성")
        self.table.heading("state", text="최근 결과")
        self.table.heading("rows", text="장비 수")
        self.table.heading("download", text="마지막 CSV")
        self.table.column("#0", width=110)
        self.table.column("name", width=145)
        self.table.column("enabled", width=70, anchor="center")
        self.table.column("state", width=95, anchor="center")
        self.table.column("rows", width=70, anchor="center")
        self.table.column("download", width=210)
        self.table.pack(fill="both", expand=True)
        self.table.bind("<<TreeviewSelect>>", self.selected)

        edit = ttk.LabelFrame(root, text="서버 추가/수정", padding=10)
        edit.pack(fill="x", pady=7)
        ttk.Label(edit, text="이름").grid(row=0, column=0, sticky="w")
        ttk.Entry(edit, textvariable=self.name_var, width=17).grid(row=0, column=1)
        ttk.Label(edit, text="HTTPS 주소").grid(row=0, column=2, padx=(10, 2))
        ttk.Entry(edit, textvariable=self.url_var, width=42).grid(row=0, column=3, sticky="ew")
        ttk.Label(edit, text="계정 ID").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Entry(edit, textvariable=self.user_var, width=17).grid(row=1, column=1)
        ttk.Label(edit, text="비밀번호").grid(row=1, column=2, padx=(10, 2))
        ttk.Entry(edit, textvariable=self.pass_var, show="•", width=26).grid(
            row=1, column=3, sticky="w")
        ttk.Checkbutton(edit, text="예약 수집 대상", variable=self.enabled_var).grid(
            row=2, column=1, sticky="w")
        edit.columnconfigure(3, weight=1)

        actions = ttk.Frame(root)
        actions.pack(fill="x", pady=8)
        for caption, callback in [
            ("신규 입력", self.reset_form), ("서버 추가", self.add),
            ("선택 서버 저장", self.edit), ("서버 삭제", self.delete),
            ("선택자 파일 열기", self.open_selectors),
            ("선택 서버 테스트", self.test_one),
            ("전체 지금 실행", self.run_all),
            ("CSV 폴더 열기", self.open_export_dir),
        ]:
            ttk.Button(actions, text=caption, command=callback).pack(side="left", padx=3)
        ttk.Label(root, textvariable=self.status_var, wraplength=910).pack(
            anchor="w", pady=8)
        ttk.Label(root, text=(
            "각 서버: Default View = Devices → Top → 전체 폴더 확장 → 15~30초 로딩 후 CSV\n"
            "비밀번호는 Windows 자격 증명 관리자에 저장 · 미확인 CSS는 해당 서버만 실패\n"
            "예약 실행은 현재 Windows 계정에 로그인된 경우에 동작합니다."
        )).pack(anchor="w")

    def _selected_id(self) -> str | None:
        items = self.table.selection()
        return items[0] if items else None

    def _current(self):
        sid = self._selected_id()
        return next((s for s in self.settings.servers if s.id == sid), None)

    def selected(self, _event=None):
        profile = self._current()
        if not profile:
            return
        self.name_var.set(profile.display_name)
        self.url_var.set(profile.server_url)
        self.user_var.set(profile.username)
        self.pass_var.set("")
        self.enabled_var.set(profile.enabled)

    def reset_form(self):
        self.table.selection_remove(*self.table.selection())
        for v in (self.name_var, self.url_var, self.user_var, self.pass_var):
            v.set("")
        self.enabled_var.set(True)

    def choose_dir(self):
        directory=filedialog.askdirectory()
        if directory:
            self.dir_var.set(directory)

    def save(self) -> bool:
        try:
            self.settings.schedule_time = self.time_var.get().strip()
            self.settings.parallel_limit = int(self.parallel_var.get())
            self.settings.export_root = self.dir_var.get().strip()
            validate_settings(self.settings)
            save_v2(self.settings, registry_path(app_home()))
            self.status_var.set("설정을 저장했습니다.")
            return True
        except (ValueError, OSError) as exc:
            messagebox.showerror("설정 저장 실패", str(exc))
            return False

    def add(self):
        try:
            if not self.pass_var.get():
                raise ValueError("새 서버의 비밀번호를 입력하세요.")
            profile = add_server(self.settings, name=self.name_var.get(),
                                 url=self.url_var.get(), username=self.user_var.get())
            try:
                CredentialStore.set_for_server(profile.id, self.pass_var.get())
                from dataclasses import replace
                self.settings.servers[-1] = replace(profile, enabled=self.enabled_var.get())
                if not self.save():
                    raise ValueError("설정 저장에 실패했습니다.")
            except Exception:
                self.settings.servers = [s for s in self.settings.servers if s.id != profile.id]
                raise
            self.pass_var.set("")
            self.refresh()
            self.table.selection_set(profile.id)
            self.selected()
        except (ValueError, CredentialError) as exc:
            messagebox.showerror("서버 추가 실패", str(exc))

    def edit(self):
        server = self._current()
        if not server:
            messagebox.showwarning("선택", "수정할 서버를 먼저 선택하세요.")
            return
        try:
            change_server(
                self.settings, server.id, name=self.name_var.get(), url=self.url_var.get(),
                username=self.user_var.get()
            )
            set_enabled(self.settings, server.id, self.enabled_var.get())
            if self.pass_var.get():
                CredentialStore.set_for_server(server.id, self.pass_var.get())
            if not self.save():
                raise ValueError("설정 저장에 실패했습니다.")
            self.pass_var.set("")
            self.refresh()
            self.table.selection_set(server.id)
        except (ValueError, CredentialError) as exc:
            messagebox.showerror("수정 실패", str(exc))

    def delete(self):
        sid=self._selected_id()
        if not sid:
            return
        if not messagebox.askyesno(
            "서버 삭제", "서버 등록을 삭제하겠습니까?\n기존 CSV 파일은 삭제되지 않습니다."
        ):
            return
        remove_server(self.settings, sid)
        self.save()
        self.reset_form()
        self.refresh()

    def open_selectors(self):
        server=self._current()
        if not server:
            messagebox.showwarning("선택", "먼저 서버를 선택하세요.")
            return
        path=server_selectors_path(app_home(), server.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(json.dumps(SELECTOR_TEMPLATE, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        if os.name=="nt":
            os.startfile(path)  # type: ignore[attr-defined]

    def _command(self, *args):
        prefix=[sys.executable]
        if not getattr(sys, "frozen", False):
            prefix += ["-m", "airwave_csv"]
        try:
            subprocess.Popen(
                [*prefix,*args,"--headless"],
                close_fds=True,
                cwd=str(Path(sys.executable).resolve().parent),
            )
            self.status_var.set("수집을 시작했습니다. 서버별 결과는 자동 갱신됩니다.")
        except OSError:
            messagebox.showerror("실행 실패", "다운로드 프로세스를 시작하지 못했습니다.")

    def test_one(self):
        sid=self._selected_id()
        if sid and self.save():
            self._command("--run-one",sid)

    def run_all(self):
        if self.save():
            self._command("--run-all")

    def register(self):
        if not self.save():
            return
        try:
            register_daily(self.settings.schedule_time)
            messagebox.showinfo("예약 완료", "하루 1회 전체 서버 수집이 등록되었습니다.")
            self.refresh()
        except ScheduleError as exc:
            messagebox.showerror("예약 실패", str(exc))

    def unregister(self):
        try:
            unregister_daily()
            self.refresh()
        except ScheduleError as exc:
            messagebox.showerror("해제 실패", str(exc))

    def open_export_dir(self):
        path=Path(self.dir_var.get()).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        if os.name=="nt":
            os.startfile(path)  # type: ignore[attr-defined]

    def refresh(self):
        state=read_last_batch(app_home())
        per=state.get("servers",{})
        progress = {}
        progress_file = app_home() / "state" / "progress.json"
        active = app_home() / "state" / "active_batch.json"
        if active.exists() and progress_file.exists():
            try:
                run_id=json.loads(active.read_text(encoding="utf-8"))["run_id"]
                p=json.loads(progress_file.read_text(encoding="utf-8"))
                if p.get("run_id")==run_id:
                    progress=p.get("servers",{})
            except (OSError, ValueError, KeyError):
                pass
        selection=self._selected_id()
        for item in self.table.get_children():
            self.table.delete(item)
        for s in self.settings.servers:
            result=per.get(s.id,{})
            state_text=progress.get(s.id) or result.get("status","준비")
            self.table.insert("", "end", iid=s.id,text=s.id,values=(
                s.display_name, "사용" if s.enabled else "제외",
                state_text, result.get("rows","-"),result.get("filename","-"),
            ))
        if selection and self.table.exists(selection):
            self.table.selection_set(selection)
        now = time.monotonic()
        if schedule_check_due(now=now, last=self._last_schedule_check):
            self._last_schedule_check = now
            try:
                self._cached_schedule_status = task_status()
            except ScheduleError:
                self._cached_schedule_status = "확인 불가"
        self.status_var.set(
            f"등록 서버 {len(self.settings.servers)}/5 · 예약: {self._cached_schedule_status}"
        )
        self.after(2000,self.refresh)


def launch():
    app=ExporterWindow()
    if app.winfo_exists():
        app.mainloop()
