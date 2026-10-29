"""AirWave 8.2.14.0 웹 UI 자동화.

현장 DOM 미확인 상태에서 CSS를 추정하지 않습니다. 선택자 프로필은 반드시
현장에서 검증해야 하며, view/folder/expanded/filters/total 중 검증 불가 시
CSV 다운로드 전에 종료합니다.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from .config import Config, ROOT_FOLDER, REQUIRED_VIEW, SelectorProfile


class PortalError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


class AirWavePortal:
    def __init__(self, config: Config, selectors: SelectorProfile):
        self.config = config
        self.selectors = selectors

    def _one(self, page, selector: str, code: int, label: str):
        locator = page.locator(selector)
        if locator.count() != 1:
            raise PortalError(code, label + " 화면 요소가 유일하지 않거나 없습니다.")
        return locator

    @staticmethod
    def _visible(locator) -> bool:
        return any(locator.nth(i).is_visible() for i in range(locator.count()))

    @staticmethod
    def _select_value(control, value_locator=None) -> str:
        tag = control.evaluate("(el) => el.tagName.toLowerCase()")
        if tag == "select":
            return control.evaluate(
                "(el) => el.selectedIndex < 0 ? '' : el.options[el.selectedIndex].text.trim()"
            )
        if value_locator is None:
            raise PortalError(45, "사용자 정의 메뉴의 현재 선택값 확인용 CSS가 필요합니다.")
        return value_locator.inner_text().strip()

    def _select_exact(
        self, page, control, expected: str, *, code: int, value_css: str, option_css: str
    ) -> None:
        selected = page.locator(value_css) if value_css else None
        tag = control.evaluate("(el) => el.tagName.toLowerCase()")
        if tag != "select" and (not selected or selected.count() != 1):
            raise PortalError(code, "현재 선택값을 검증할 수 없는 메뉴입니다.")
        current = self._select_value(control, selected)
        if current != expected:
            if tag == "select":
                try:
                    control.select_option(label=expected)
                except Exception as exc:
                    raise PortalError(code, "필수 선택 항목이 존재하지 않습니다.") from exc
            elif option_css:
                control.click()
                self._one(page, option_css, code, "메뉴 선택 항목").click()
            else:
                raise PortalError(code, "사용자 정의 메뉴의 옵션 선택 CSS가 필요합니다.")
        result = self._select_value(control, selected)
        if result != expected:
            raise PortalError(code, "메뉴가 요구한 값으로 설정되지 않았습니다.")

    def _verify_view(self, page) -> None:
        root = self._one(page, self.selectors["table_root_css"], 45, "Devices List")
        view = self._one(root, self.selectors["view_control_css"], 45, "Default View")
        selected = (self._one(root, self.selectors["view_selected_css"], 45, "보기 선택값")
                    if self.selectors["view_selected_css"] else None)
        if self._select_value(view, selected) != REQUIRED_VIEW:
            raise PortalError(45, "Default View가 Devices가 아닙니다. CSV를 내보내지 않습니다.")

    def _set_view(self, page) -> None:
        root = self._one(page, self.selectors["table_root_css"], 45, "Devices List")
        view = self._one(root, self.selectors["view_control_css"], 45, "Default View")
        try:
            self._select_exact(
                root, view, REQUIRED_VIEW, code=45,
                value_css=self.selectors["view_selected_css"],
                option_css=self.selectors["view_option_css"],
            )
            self._verify_view(page)
        except PortalError:
            raise
        except Exception as exc:
            raise PortalError(45, "Default View = Devices 전환에 실패했습니다.") from exc

    def _verify_filters(self, page) -> None:
        if self._visible(page.locator(self.selectors["active_filters_css"])):
            raise PortalError(46, "장비 검색 또는 상태 필터가 남아 있습니다.")

    def _clear_filters(self, page) -> None:
        active = page.locator(self.selectors["active_filters_css"])
        if self._visible(active):
            css = self.selectors["clear_filters_css"]
            if not css:
                raise PortalError(46, "활성 필터를 해제할 CSS가 설정되지 않았습니다.")
            self._one(page, css, 46, "필터 초기화").click()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and self._visible(active):
                time.sleep(0.3)
            self._verify_filters(page)

    def _verify_folder(self, page) -> None:
        folder = self._one(page, self.selectors["folder_control_css"], 46, "Go to folder")
        selected = (self._one(page, self.selectors["folder_selected_css"], 46, "선택된 폴더")
                    if self.selectors["folder_selected_css"] else None)
        if self._select_value(folder, selected) != ROOT_FOLDER:
            raise PortalError(46, "Top 폴더가 선택되지 않았습니다.")

    def _set_folder(self, page) -> None:
        folder = self._one(page, self.selectors["folder_control_css"], 46, "Go to folder")
        self._select_exact(
            page, folder, ROOT_FOLDER, code=46,
            value_css=self.selectors["folder_selected_css"],
            option_css=self.selectors["folder_option_css"],
        )
        self._verify_folder(page)

    def _verify_expanded(self, page) -> bool:
        return self._visible(page.locator(self.selectors["expanded_marker_css"]))

    def _expand(self, page) -> None:
        if not self._verify_expanded(page):
            self._one(page, self.selectors["expand_control_css"], 47, "전체 폴더 확장").click()

    def _total(self, page) -> int:
        root = self._one(page, self.selectors["table_root_css"], 47, "Devices List")
        element = self._one(root, self.selectors["total_count_css"], 47, "장비 총건수")
        match = re.search(self.selectors["total_count_pattern"], element.inner_text())
        if not match:
            raise PortalError(47, "장비 목록 총건수 표시를 해석할 수 없습니다.")
        try:
            count = int(match.group(1).replace(",", ""))
        except (IndexError, ValueError) as exc:
            raise PortalError(47, "장비 총건수 형식이 올바르지 않습니다.") from exc
        if count < 1:
            raise PortalError(47, "현재 장비 총건수가 0건입니다.")
        return count

    def _wait_for_all(self, page) -> int:
        """폴더 확장 후 최소 15초, 최대 30초 기다리며 완료 상태를 검사합니다."""
        started = time.monotonic()
        last_total = None
        stable_since = None
        while time.monotonic() - started <= self.config.max_wait_seconds:
            now = time.monotonic()
            elapsed = now - started
            if elapsed >= self.config.min_wait_seconds:
                spinner_css = self.selectors["loading_css"]
                busy = bool(spinner_css and self._visible(page.locator(spinner_css)))
                if self._verify_expanded(page) and not busy:
                    try:
                        rows = page.locator(self.selectors["rows_css"])
                        count = self._total(page)
                        if self._visible(rows):
                            if count != last_total:
                                last_total, stable_since = count, now
                            elif stable_since is not None and now - stable_since >= 1:
                                return count
                        else:
                            last_total, stable_since = None, None
                    except PortalError:
                        last_total, stable_since = None, None
                else:
                    last_total, stable_since = None, None
            time.sleep(0.5)
        raise PortalError(47, "30초 안에 전체 장비 목록 로딩을 확인하지 못했습니다.")

    def _navigate(self, page) -> None:
        try:
            css = self.selectors["devices_nav_css"]
            if css:
                self._one(page, css, 32, "Devices 메뉴").click()
            else:
                page.get_by_role("link", name="Devices", exact=True).click(timeout=10000)
            css = self.selectors["list_nav_css"]
            if css:
                self._one(page, css, 32, "List 메뉴").click()
            else:
                page.get_by_role("link", name="List", exact=True).click(timeout=10000)
        except PortalError:
            raise
        except Exception as exc:
            raise PortalError(32, "Devices > List 화면으로 이동하지 못했습니다.") from exc

    def _login_if_needed(self, page, password: str) -> None:
        css = self.selectors["login_user_css"]
        if css and page.locator(css).count() == 1:
            try:
                user = self._one(page, css, 31, "로그인 ID")
                pass_css = self.selectors["login_pass_css"]
                submit_css = self.selectors["login_submit_css"]
                if not pass_css or not submit_css:
                    raise PortalError(31, "로그인 선택자 구성이 부족합니다.")
                user.fill(self.config.username)
                self._one(page, pass_css, 31, "로그인 비밀번호").fill(password)
                self._one(page, submit_css, 31, "로그인 버튼").click()
            except PortalError:
                raise
            except Exception as exc:
                raise PortalError(31, "AirWave 로그인을 완료하지 못했습니다.") from exc
        # SSO/CAPTCHA/MFA를 자동으로 우회하지 않습니다. 후속 탐색 실패를 인증 오류로 기록합니다.

    def download(self, staged: Path, password: str) -> int:
        """요구사항을 모두 확인한 후에만 CSV 다운로드를 시작합니다."""
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeout
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise PortalError(33, "Playwright 실행 파일을 찾을 수 없습니다.") from exc
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    channel="msedge", headless=self.config.headless
                )
                try:
                    context = browser.new_context(accept_downloads=True, ignore_https_errors=False)
                    page = context.new_page()
                    page.set_default_timeout(15000)
                    page.goto(self.config.server_url, wait_until="domcontentloaded", timeout=45000)
                    self._login_if_needed(page, password)
                    self._navigate(page)
                    self._set_view(page)
                    self._clear_filters(page)
                    self._set_folder(page)
                    self._expand(page)
                    count = self._wait_for_all(page)
                    # 다운로드 직전에 모든 전제 조건을 다시 확인합니다.
                    self._verify_view(page)
                    self._verify_filters(page)
                    self._verify_folder(page)
                    if not self._verify_expanded(page):
                        raise PortalError(47, "하위 폴더 확장 상태가 해제됐습니다.")
                    if self._total(page) != count:
                        raise PortalError(47, "장비 목록 총건수가 다운로드 직전에 변경됐습니다.")
                    root = self._one(
                        page, self.selectors["table_root_css"], 48, "Devices List"
                    )
                    export = self._one(
                        root, self.selectors["export_control_css"], 48, "Export as CSV"
                    )
                    with page.expect_download(timeout=180000) as info:
                        export.click()
                    download = info.value
                    download.save_as(staged)
                    if download.failure():
                        raise PortalError(48, "AirWave CSV 다운로드가 실패했습니다.")
                    return count
                finally:
                    browser.close()
        except PortalError:
            raise
        except (PlaywrightError, PlaywrightTimeout) as exc:
            raise PortalError(48, "브라우저 실행 또는 AirWave 화면 동작에 실패했습니다.") from exc
        except OSError as exc:
            raise PortalError(48, "CSV 파일을 저장하지 못했습니다.") from exc
