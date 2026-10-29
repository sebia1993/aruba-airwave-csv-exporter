from pathlib import Path

from airwave_csv.process_control import worker_command


def test_worker_command_hides_credentials(monkeypatch, tmp_path):
    cmd=worker_command(tmp_path/"snapshot.json","airwave-02",1,tmp_path/"result.json")
    assert "--server-id" in cmd and "airwave-02" in cmd
    assert "--worker" in cmd
    assert "secret" not in " ".join(cmd)


def test_result_ends_failed_if_child_exits_without_json(tmp_path):
    from airwave_csv.process_control import WorkerHandle
    class FakeProcess:
        def poll(self): return 1
        def close(self): pass
    h=WorkerHandle(FakeProcess(),tmp_path/"missing.json","run","airwave-01",1)
    out=h.poll()
    assert out is not None and out.status=="FAILED" and out.exit_code!=0
