
from airwave_csv.multi_config import MultiConfig, add_server
from airwave_csv.orchestrator import run_batch
from airwave_csv.run_snapshot import BatchSnapshot, WorkerResult


class Clock:
    def __init__(self): self.t=0
    def monotonic(self): return self.t
    def sleep(self,s): self.t+=s


class FakeHandle:
    def __init__(self,launcher,sid,attempt,fail=False):
        self.launcher,self.sid,self.attempt,self.fail=launcher,sid,attempt,fail
        self.done=False
    def poll(self):
        if self.done:
            return None
        self.done=True
        self.launcher.running-=1
        return WorkerResult("run-1",self.sid,self.attempt,
                            "FAILED" if self.fail else "SUCCESS",
                            48 if self.fail else 0,self.fail,0 if self.fail else 1)
    def terminate(self):
        if not self.done:
            self.launcher.running-=1
        self.done=True


class Launcher:
    def __init__(self,fail_sid=None):
        self.fail_sid=fail_sid
        self.running=0
        self.max_active=0
        self.starts=[]
    def start(self,snapshot_path,sid,attempt,result_path):
        self.running+=1
        self.max_active=max(self.running,self.max_active)
        self.starts.append((sid,attempt))
        return FakeHandle(self,sid,attempt,
                          sid==self.fail_sid and attempt==1)


def snapshot(tmp_path,n):
    cfg=MultiConfig(export_root=str(tmp_path/"csv"),retry_delay_seconds=180)
    for i in range(1,n+1):
        add_server(cfg,name=f"AW{i}",url=f"https://aw{i}.example.invalid",username="ops")
    return BatchSnapshot("run-1",cfg,tuple(cfg.servers),{},
                         "2026-10-29T00:00:00Z")


def test_five_active_max_three_slots(tmp_path):
    launcher=Launcher()
    summary=run_batch(snapshot(tmp_path,5),launcher=launcher,clock=Clock(),home=tmp_path)
    assert summary.success==5
    assert launcher.max_active<=3
    assert [sid for sid,n in launcher.starts][:3]==["airwave-01","airwave-02","airwave-03"]


def test_retry_releases_slot_and_waits_for_first_attempts(tmp_path):
    launcher=Launcher("airwave-01")
    clock=Clock()
    result=run_batch(snapshot(tmp_path,5),launcher=launcher,clock=clock,home=tmp_path)
    ids=[sid for sid,n in launcher.starts]
    assert ids.index("airwave-04") < ids.index("airwave-01",1)
    assert ids.index("airwave-05") < ids.index("airwave-01",1)
    assert result.success==5
    assert clock.t>=180


def test_one_failed_server_does_not_stop_others(tmp_path):
    launcher=Launcher("airwave-01")
    cfg=snapshot(tmp_path,3)
    cfg.settings.max_attempts=1
    summary=run_batch(cfg,launcher=launcher,clock=Clock(),home=tmp_path)
    assert summary.success==2 and summary.failed==1
    assert summary.exit_code==2


def test_zero_active_reports_no_target(tmp_path):
    cfg=snapshot(tmp_path,1)
    cfg.settings.servers.clear()
    result=run_batch(BatchSnapshot("run-1",cfg,tuple(),{},""),launcher=Launcher(),
                     clock=Clock(),home=tmp_path)
    assert result.exit_code==3


def test_final_summary_and_active_marker_are_written_under_batch_lock(tmp_path, monkeypatch):
    """뒤따르는 예약 실행이 마지막 결과를 덮어쓰는 경쟁 상태를 막습니다."""
    import contextlib

    from airwave_csv import orchestrator

    holding = {"value": False}
    original_summary = orchestrator.write_batch_summary
    original_clear = orchestrator.clear_batch_active

    @contextlib.contextmanager
    def tracked_lock(_path):
        assert not holding["value"]
        holding["value"] = True
        try:
            yield
        finally:
            holding["value"] = False

    def checked_summary(*args, **kwargs):
        assert holding["value"], "배치 잠금이 해제되기 전에 요약을 저장해야 합니다."
        return original_summary(*args, **kwargs)

    def checked_clear(*args, **kwargs):
        assert holding["value"], "활성 마커 삭제까지 배치 잠금을 유지해야 합니다."
        return original_clear(*args, **kwargs)

    monkeypatch.setattr(orchestrator, "single_instance", tracked_lock)
    monkeypatch.setattr(orchestrator, "write_batch_summary", checked_summary)
    monkeypatch.setattr(orchestrator, "clear_batch_active", checked_clear)
    result = run_batch(snapshot(tmp_path, 1), launcher=Launcher(), clock=Clock(), home=tmp_path)
    assert result.success == 1


def test_all_disabled_servers_are_reported_skipped(tmp_path):
    """모든 서버가 비활성인 배치도 서버별 제외 사유를 결과에 보존합니다."""
    from dataclasses import replace

    from airwave_csv.events import read_last_batch

    initial = snapshot(tmp_path, 2)
    servers = tuple(replace(s, enabled=False) for s in initial.servers)
    batch = BatchSnapshot(initial.run_id, initial.settings, servers, {}, initial.created_at)
    outcome = run_batch(batch, launcher=Launcher(), clock=Clock(), home=tmp_path)

    assert outcome.exit_code == 3
    assert outcome.skipped == 2
    status = read_last_batch(tmp_path)
    assert status["servers"]["airwave-01"]["status"] == "SKIPPED"
    assert status["servers"]["airwave-02"]["status"] == "SKIPPED"
