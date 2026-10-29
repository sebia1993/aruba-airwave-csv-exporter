"""초급 네트워크 운영자를 위한 한국어 Windows GUI (tkinter)."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .config import Config, ProfileError, SelectorProfile, app_home
from .credentials import CredentialError, CredentialStore
from .events import last_event
from .scheduler import ScheduleError, executable_action, register_daily, task_status, unregister_daily


class ExporterWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AirWave CSV Exporter")
        self.geometry("675x570")
        self.minsize(600, 520)
        try:
            self.config_model = Config.load()
        except (ValueError, OSError, TypeError):
            self.config_model = Config()
            messagebox.showwarning("설정 오류", "기존 설정을 읽을 수 없어 기본값으로 시작합니다.")
        cfg = self.config_model
        self.server = tk.StringVar(value=cfg.server_url)
        self.username = tk.StringVar(value=cfg.username)
        self.password = tk.StringVar()
        self.export_dir = tk.StringVar(value=cfg.export_dir)
        self.schedule_time = tk.StringVar(value=cfg.schedule_time)
        self.headless = tk.BooleanVar(value=cfg.headless)
        self.status = tk.StringVar(value="상태 확인 전")
        self.last = tk.StringVar(value="실행 결과 없음")
        self._build()
        self.refresh()

    def _build(self) -> None:
        container = ttk.Frame(self, padding=18)
        container.pack(fill="both", expand=True)
        ttk.Label(
            container, text="AirWave 장비 목록 CSV 자동 다운로드",
            font=("맑은 고딕", 14, "bold")
        ).pack(anchor="w")
        ttk.Label(
            container, text="Devices → List / Default View: Devices / 전체 폴더 확장 / 15~30초 대기",
        ).pack(anchor="w", pady=(6, 10))

        form = ttk.LabelFrame(container, text="AirWave 접속 및 저장 설정", padding=12)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        entries = [
            ("AirWave HTTPS 주소", self.server, False),
            ("로그인 ID", self.username, False),
            ("로그인 비밀번호", self.password, True),
        ]
        for i, (caption, variable, secret) in enumerate(entries):
            ttk.Label(form, text=caption).grid(row=i, column=0, sticky="w", padx=(0, 12), pady=5)
            kwargs = {"show": "•"} if secret else {}
            ttk.Entry(form, textvariable=variable, **kwargs).grid(
                row=i, column=1, sticky="ew", pady=5
            )

        ttk.Label(form, text="CSV 저장 폴더").grid(
            row=3, column=0, sticky="w", padx=(0, 12), pady=5
        )
        ttk.Entry(form, textvariable=self.export_dir).grid(row=3, column=1, sticky="ew")
        ttk.Button(form, text="찾기", command=self.choose_directory).grid(
            row=3, column=2, padx=(6, 0)
        )
        ttk.Label(form, text="매일 실행 시간").grid(row=4, column=0, sticky="w", pady=5)
        ttk.Entry(form, textvariable=self.schedule_time, width=8).grid(
            row=4, column=1, sticky="w", pady=5
        )
        ttk.Label(form, text="HH:MM (예: 09:00)").grid(
            row=4, column=1, sticky="w", padx=(75, 0)
        )
        ttk.Checkbutton(
            form, text="자동 실행 시 브라우저 숨김 (권장)", variable=self.headless
        ).grid(row=5, column=1, sticky="w", pady=(4, 0))

        buttons = ttk.Frame(container)
        buttons.pack(fill="x", pady=12)
        ttk.Button(buttons, text="설정 저장", command=self.save).pack(side="left", padx=3)
        ttk.Button(buttons, text="지금 테스트", command=self.run_now).pack(side="left", padx=3)
        ttk.Button(buttons, text="매일 예약 등록/변경", command=self.schedule).pack(
            side="left", padx=3
        )
        ttk.Button(buttons, text="예약 해제", command=self.unschedule).pack(
            side="left", padx=3
        )

        tools = ttk.LabelFrame(container, text="현장 화면 연결 및 결과", padding=12)
        tools.pack(fill="x")
        ttk.Label(
            tools, text="필수 조건: Default View = Devices | 목록 대기: 15~30초",
        ).pack(anchor="w", pady=(0, 7))
        ttk.Label(tools, textvariable=self.status, wraplength=610).pack(anchor="w", pady=3)
        ttk.Label(tools, textvariable=self.last, wraplength=610).pack(anchor="w", pady=3)
        bottom = ttk.Frame(tools)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Button(bottom, text="현장 선택자 파일 열기", command=self.open_selectors).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(bottom, text="결과 새로고침", command=self.refresh).pack(
            side="left", padx=6
        )
        ttk.Button(bottom, text="CSV 폴더 열기", command=self.open_export_dir).pack(
            side="left", padx=6
        )
        ttk.Button(bottom, text="로그 폴더 열기", command=self.open_logs).pack(
            side="left", padx=6
        )
        ttk.Label(
            container,
            text=(
                "실제 AirWave 화면의 선택자 확인 전에는 자동 다운로드가 차단됩니다.\n"
                "예약 작업은 현재 Windows 계정이 로그인된 경우에 실행됩니다.\n"
                "비밀번호는 Windows 자격 증명 관리자에만 저장합니다."
            ), justify="left",
        ).pack(anchor="w", pady=(14, 0))

    def choose_directory(self) -> None:
        initial = self.export_dir.get()
        chosen = filedialog.askdirectory(initialdir=initial if Path(initial).exists() else None)
        if chosen:
            self.export_dir.set(chosen)

    def _save(self) -> bool:
        model = Config(
            server_url=self.server.get().strip(),
            username=self.username.get().strip(),
            export_dir=self.export_dir.get().strip(),
            schedule_time=self.schedule_time.get().strip(),
            headless=self.headless.get(),
            schedule_enabled=self.config_model.schedule_enabled,
        )
        model.validate(require_connection=True)
        password = self.password.get()
        if password:
            CredentialStore.set(model.server_url, model.username, password)
            self.password.set("")
        model.save()
        self.config_model = model
        return True

    def save(self) -> bool:
        try:
            return self._save()
        except (ValueError, CredentialError, OSError, TypeError) as exc:
            messagebox.showerror("저장 실패", str(exc))
            return False

    def run_now(self) -> None:
        if not self.save():
            return
        executable, argument_string = executable_action()
        args = [str(executable), *argument_string.split()]
        try:
            subprocess.Popen(args, cwd=str(executable.parent), close_fds=True)
            messagebox.showinfo(
                "작업 시작", "CSV 수집을 시작했습니다. 완료 후 '결과 새로고침'을 눌러 확인하세요."
            )
        except OSError:
            messagebox.showerror("실행 실패", "작업 프로세스를 시작하지 못했습니다.")

    def schedule(self) -> None:
        if not self.save():
            return
        try:
            register_daily(self.config_model.schedule_time)
            self.config_model.schedule_enabled = True
            self.config_model.save()
            self.refresh()
            messagebox.showinfo("예약 등록", "매일 예약 실행을 등록했습니다.")
        except (ScheduleError, OSError) as exc:
            messagebox.showerror("예약 실패", str(exc))

    def unschedule(self) -> None:
        try:
            unregister_daily()
            self.config_model.schedule_enabled = False
            self.config_model.save()
            self.refresh()
        except (ScheduleError, OSError) as exc:
            messagebox.showerror("예약 해제 실패", str(exc))

    def open_selectors(self) -> None:
        path = app_home() / "selectors.json"
        try:
            SelectorProfile.load(path)
        except ProfileError:
            pass  # 빈 템플릿을 만드는 것도 허용합니다.
        except (ValueError, OSError) as exc:
            messagebox.showerror("파일 오류", str(exc))
            return
        self._open_path(path)

    def open_export_dir(self) -> None:
        path = Path(os.path.expandvars(self.export_dir.get())).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        self._open_path(path)

    def open_logs(self) -> None:
        path = app_home() / "logs"
        path.mkdir(parents=True, exist_ok=True)
        self._open_path(path)

    @staticmethod
    def _open_path(path: Path) -> None:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            messagebox.showinfo("폴더 위치", str(path))

    def refresh(self) -> None:
        try:
            state = task_status()
            self.status.set("Windows 예약 상태: " + state)
        except ScheduleError:
            self.status.set("Windows 예약 상태: 이 PC에서는 확인할 수 없습니다.")
        event = last_event(app_home())
        if event:
            self.last.set(
                "최근 실행: {timestamp} | {status} | 오류코드 {code} | {rows}건 | {filename}".format(
                    timestamp=event.get("timestamp", "-"),
                    status=event.get("status", "-"),
                    code=event.get("code", "-"),
                    rows=event.get("rows", "-"),
                    filename=event.get("filename", "-"),
                )
            )


def launch() -> None:
    ExporterWindow().mainloop()
