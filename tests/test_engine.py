from airwave_csv.config import Config, SELECTOR_TEMPLATE, SelectorProfile
from airwave_csv.engine import run_once
from airwave_csv.portal import PortalError


class FakeVault:
    @staticmethod
    def get(server, username):
        return "test-secret"


class SuccessPortal:
    def __init__(self, config, profile):
        pass

    def download(self, path, password):
        assert password == "test-secret"
        path.write_text("Name,Model\nap1,AP-535\nap2,AP-535\n", encoding="utf-8")
        return 2


class WrongViewPortal:
    calls = 0

    def __init__(self, config, profile):
        pass

    def download(self, path, password):
        WrongViewPortal.calls += 1
        raise PortalError(45, "Default View가 Devices가 아닙니다.")


def config_for(tmp_path):
    return Config(
        server_url="https://airwave.example.invalid",
        username="operator",
        export_dir=str(tmp_path / "exports"),
        retry_delay_seconds=0,
    )


def test_run_once_success(tmp_path):
    result = run_once(
        config=config_for(tmp_path), profile=SelectorProfile(dict(SELECTOR_TEMPLATE)),
        portal_factory=SuccessPortal, credential_store=FakeVault, home=tmp_path,
    )
    assert result.exit_code == 0
    assert result.saved.rows == 2
    assert (tmp_path / "exports" / "latest.csv").exists()
    log = next((tmp_path / "logs").glob("*.jsonl")).read_text(encoding="utf-8")
    assert "test-secret" not in log


def test_wrong_view_does_not_retry_or_export(tmp_path):
    WrongViewPortal.calls = 0
    result = run_once(
        config=config_for(tmp_path), profile=SelectorProfile(dict(SELECTOR_TEMPLATE)),
        portal_factory=WrongViewPortal, credential_store=FakeVault, home=tmp_path,
    )
    assert result.exit_code == 45
    assert WrongViewPortal.calls == 1
    assert not (tmp_path / "exports" / "latest.csv").exists()


def test_empty_csv_retry_succeeds(tmp_path):
    attempts = []

    class RetryPortal:
        def __init__(self, config, profile):
            pass

        def download(self, path, password):
            attempts.append(1)
            if len(attempts) == 1:
                path.write_bytes(b"")
            else:
                path.write_text("Name,Model\nap1,AP-535\n", encoding="utf-8")
            return 1

    wait_calls = []
    result = run_once(
        config=config_for(tmp_path), profile=SelectorProfile(dict(SELECTOR_TEMPLATE)),
        portal_factory=RetryPortal, credential_store=FakeVault, sleeper=wait_calls.append,
        home=tmp_path,
    )
    assert result.exit_code == 0
    assert len(attempts) == 2
    assert wait_calls == [0]


def test_missing_credential_fails_without_csv(tmp_path):
    class MissingVault:
        @staticmethod
        def get(server, username):
            from airwave_csv.credentials import CredentialError

            raise CredentialError("저장된 비밀번호가 없습니다.")

    result = run_once(
        config=config_for(tmp_path), profile=SelectorProfile(dict(SELECTOR_TEMPLATE)),
        portal_factory=SuccessPortal, credential_store=MissingVault, home=tmp_path,
    )
    assert result.exit_code == 31
    assert not (tmp_path / "exports").exists()
