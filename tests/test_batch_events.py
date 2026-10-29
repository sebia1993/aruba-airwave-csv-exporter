from airwave_csv.events import record_server_event, read_last_batch, write_batch_summary
from airwave_csv.orchestrator import BatchSummary
from airwave_csv.run_snapshot import WorkerResult


def test_summary_keeps_server_results_separate(tmp_path):
    summary=BatchSummary("batch-1",3,2,0,1,0,0,2,5.0)
    outcomes={
        "airwave-01":WorkerResult("batch-1","airwave-01",1,"SUCCESS",0,False,12),
        "airwave-02":WorkerResult("batch-1","airwave-02",1,"FAILED",45,False),
    }
    write_batch_summary(tmp_path,summary,outcomes)
    result=read_last_batch(tmp_path)
    assert result["run_id"]=="batch-1"
    assert result["servers"]["airwave-01"]["rows"]==12
    assert result["servers"]["airwave-02"]["exit_code"]==45


def test_log_records_no_sensitive_fields(tmp_path):
    record_server_event(tmp_path,run_id="run",server_id="airwave-01",
                        stage="complete",status="FAILED",code=45,attempt=1)
    p=next((tmp_path/"logs").glob("*.jsonl"))
    content=p.read_text(encoding="utf-8")
    assert '"server_id": "airwave-01"' in content
    assert "password" not in content
