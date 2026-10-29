import json
from dataclasses import asdict

from airwave_csv.multi_config import MultiConfig, add_server
from airwave_csv.run_snapshot import BatchSnapshot, WorkerResult, read_snapshot, write_snapshot, write_worker_result


def test_snapshot_contains_no_credentials(tmp_path):
    cfg=MultiConfig(export_root=str(tmp_path))
    s=add_server(cfg,name="One",url="https://aw.example.invalid",username="ops")
    snap=BatchSnapshot(run_id="run-1",settings=cfg,servers=(s,),
                       selectors={s.id:{"table_root_css":"#list"}},created_at="2026-10-29T00:00:00Z")
    file=write_snapshot(tmp_path,snap)
    assert read_snapshot(file).run_id=="run-1"
    contents=file.read_text(encoding="utf-8")
    assert "password" not in contents.lower()
    assert "cookie" not in contents.lower()


def test_result_written_atomically_and_roundtrips(tmp_path):
    obj=WorkerResult(run_id="one",server_id="airwave-01",attempt=1,
                     status="SUCCESS",exit_code=0,retryable=False,rows=5,
                     filename="file.csv")
    from airwave_csv.run_snapshot import read_worker_result
    f=tmp_path/"result.json"
    write_worker_result(f,obj)
    assert read_worker_result(f)==obj
