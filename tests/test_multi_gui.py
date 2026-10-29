import pytest

from airwave_csv.gui_model import change_server, remove_server, set_enabled
from airwave_csv.multi_config import MultiConfig, add_server


def build():
    cfg=MultiConfig(export_root="C:/AirWaveCSV")
    one=add_server(cfg,name="AW1",url="https://a.example.invalid",username="ops")
    two=add_server(cfg,name="AW2",url="https://b.example.invalid",username="ops")
    return cfg,one,two


def test_change_server_keeps_immutable_id_and_rejects_duplicate_url():
    cfg,one,two=build()
    updated=change_server(cfg,one.id,name="New A",url="https://a.example.invalid",
                          username="newoperator")
    assert updated.id==one.id and updated.display_name=="New A"
    with pytest.raises(ValueError):
        change_server(cfg,one.id,name="bad",url=two.server_url,username="ops")
    assert cfg.servers[0].display_name=="New A"


def test_disabled_server_is_not_deleted():
    cfg,one,_=build()
    set_enabled(cfg,one.id,False)
    assert len(cfg.servers)==2
    assert cfg.servers[0].enabled is False


def test_remove_keeps_next_server_number():
    cfg,one,_=build()
    remove_server(cfg,one.id)
    assert len(cfg.servers)==1
    assert cfg.next_server_number==3
