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



def test_manual_one_server_ignores_daily_enabled_flag(monkeypatch, tmp_path):
    from dataclasses import replace
    from types import SimpleNamespace

    from airwave_csv.multi_config import MultiConfig, add_server

    config=MultiConfig(export_root=str(tmp_path/"csv"))
    server=add_server(config,name="AW1",url="https://a.example.invalid",username="ops")
    config.servers[0]=replace(server,enabled=False)
    observed=[]
    monkeypatch.setattr(cli,"app_home",lambda:tmp_path)
    monkeypatch.setattr(cli,"migrate_if_needed",lambda home:config)
    monkeypatch.setattr(cli,"run_batch",lambda snap,home: observed.append(snap) or SimpleNamespace(exit_code=0))
    assert cli.run_all(only=server.id)==0
    assert observed[0].servers[0].enabled is True
