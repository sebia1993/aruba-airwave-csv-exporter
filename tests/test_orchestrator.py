
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
