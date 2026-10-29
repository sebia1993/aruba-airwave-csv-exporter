"""Windows 자격 증명 관리자 전용 저장. 평문 설정 파일 사용 금지."""

from __future__ import annotations

import os
import re


class CredentialError(Exception):
    pass


class CredentialStore:
    SERVICE = "AirWaveCsvExporter"

    @staticmethod
    def _vault():
        if os.name != "nt":
            raise CredentialError("Windows 자격 증명 관리자는 Windows에서만 사용 가능합니다.")
        try:
            from keyring.backends.Windows import WinVaultKeyring
            return WinVaultKeyring()
        except Exception as exc:
            raise CredentialError("Windows 자격 증명 관리자를 사용할 수 없습니다.") from exc

    @classmethod
    def set(cls, server: str, user: str, password: str) -> None:
        if not server or not user or not password:
            raise CredentialError("주소·아이디·비밀번호가 모두 필요합니다.")
        try:
            cls._vault().set_password(cls.SERVICE, server + "|" + user, password)
        except CredentialError:
            raise
        except Exception as exc:
            raise CredentialError("Windows 자격 증명을 저장하지 못했습니다.") from exc

    @classmethod
    def get(cls, server: str, user: str) -> str:
        try:
            result = cls._vault().get_password(cls.SERVICE, server + "|" + user)
        except CredentialError:
            raise
        except Exception as exc:
            raise CredentialError("Windows 자격 증명을 읽지 못했습니다.") from exc
        if not result:
            raise CredentialError("저장된 AirWave 비밀번호가 없습니다.")
        return result

    @classmethod
    def set_for_server(cls, server_id: str, password: str) -> None:
        if not re.fullmatch(r"airwave-\d{2,}", server_id) or not password:
            raise CredentialError("올바른 서버 ID와 비밀번호가 필요합니다.")
        try:
            cls._vault().set_password(cls.SERVICE, "server|" + server_id, password)
        except Exception as exc:
            raise CredentialError("Windows 자격 증명을 저장하지 못했습니다.") from exc

    @classmethod
    def get_for_server(cls, server_id: str) -> str:
        if not re.fullmatch(r"airwave-\d{2,}", server_id):
            raise CredentialError("잘못된 서버 ID입니다.")
        try:
            value = cls._vault().get_password(cls.SERVICE, "server|" + server_id)
        except Exception as exc:
            raise CredentialError("Windows 자격 증명을 읽지 못했습니다.") from exc
        if not value:
            raise CredentialError("서버별 AirWave 비밀번호를 등록하세요.")
        return value
