from airwave_csv import __main__ as cli


def test_legacy_run_aliases_all(monkeypatch):
    calls=[]
    monkeypatch.setattr(cli,"run_all",lambda only=None: calls.append(only) or 0)
    assert cli.main(["--run","--headless"])==0
    assert calls==[None]


def test_select_server_id_passes_to_runner(monkeypatch):
    calls=[]
    monkeypatch.setattr(cli,"run_all",lambda only=None: calls.append(only) or 2)
    assert cli.main(["--run-one","airwave-02","--headless"])==2
    assert calls==["airwave-02"]


def test_worker_needs_all_arguments():
    try:
        cli.main(["--worker","--headless"])
    except SystemExit as exc:
        assert exc.code!=0
    else:
        raise AssertionError("missing worker inputs should fail")
