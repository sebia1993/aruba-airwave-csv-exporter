"""실제 AirWave 대신 격리된 모의 HTML을 쓰는 Windows Edge 동시 다운로드 테스트."""

import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_playwright_mock_ui import test_browser_synthetic_ui_download


@pytest.mark.skipif(os.name != "nt", reason="Windows Microsoft Edge 전용")
def test_three_mock_servers_have_independent_downloads(tmp_path):
    def one(index):
        path=tmp_path/f"server-{index}"
        path.mkdir()
        test_browser_synthetic_ui_download(path)
        assert (path/"staged.part").exists()
        return path

    with ThreadPoolExecutor(max_workers=3) as pool:
        dirs=list(pool.map(one,(1,2,3)))
    assert len(set(map(str,dirs)))==3
    assert all((p/"staged.part").exists() for p in dirs)
