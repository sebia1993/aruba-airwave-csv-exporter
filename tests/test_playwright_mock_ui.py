"""실제 장비 접근 없이 Windows Edge로 검증하는 모의 AirWave HTML E2E 테스트.

실제 AirWave 8.2.14.0의 DOM을 검증하는 테스트는 아닙니다.
"""

import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import threading

import pytest

from airwave_csv.config import Config, SELECTOR_TEMPLATE, SelectorProfile
from airwave_csv.csv_store import analyze
from airwave_csv.portal import AirWavePortal


MOCK_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Mock AirWave</title></head>
<body>
<nav><a id="devices" href="#">Devices</a> <a id="list" href="#">List</a></nav>
<label>Go to folder
<select id="folder"><option>Other</option><option>Top</option></select></label>
<div class="active-filter">Down only</div>
<button id="clear" onclick="document.querySelector('.active-filter').hidden = true">
Clear filters</button>
<button id="expand" onclick="expand()">Expand folders to show all devices</button>
<span id="expanded" hidden>Collapse folders</span>
<span id="loading" hidden>Loading ...</span>
<section id="devices-list">
  <label>Default View
    <select id="view"><option>Down Devices</option><option>Devices</option></select>
  </label>
  <span id="total">Showing 1 to 2 of 2</span>
  <table><tbody>
    <tr class="device-row"><td>ap1</td></tr>
    <tr class="device-row"><td>ap2</td></tr>
  </tbody></table>
  <button id="export" onclick="saveCSV()">Export as CSV</button>
</section>
<script>
function expand() {
  document.getElementById('expanded').hidden = false;
  document.getElementById('loading').hidden = false;
  setTimeout(() => { document.getElementById('loading').hidden = true; }, 100);
}
function saveCSV() {
  if (document.getElementById('view').selectedOptions[0].text !== 'Devices') {
    throw new Error('Wrong view');
  }
  if (document.getElementById('folder').value !== 'Top') {
    throw new Error('Wrong folder');
  }
  const text = 'Name,Model\nap1,AP-535\nap2,AP-535\n';
  const url = URL.createObjectURL(new Blob([text], { type:'text/csv' }));
  const a = document.createElement('a');
  a.href = url; a.download = 'devices.csv'; document.body.appendChild(a); a.click();
}
</script>
</body></html>
"""


@pytest.mark.skipif(os.name != "nt", reason="Windows Edge 브라우저 전용 테스트")
def test_browser_synthetic_ui_download(tmp_path):
    (tmp_path / "index.html").write_text(MOCK_HTML, encoding="utf-8")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        settings = Config(
            server_url=f"http://127.0.0.1:{server.server_address[1]}/",
            username="demo", export_dir=str(tmp_path),
            min_wait_seconds=0, max_wait_seconds=3,
        )
        css = dict(SELECTOR_TEMPLATE)
        css.update({
            "devices_nav_css": "#devices",
            "list_nav_css": "#list",
            "table_root_css": "#devices-list",
            "view_control_css": "#view",
            "folder_control_css": "#folder",
            "active_filters_css": ".active-filter:not([hidden])",
            "clear_filters_css": "#clear",
            "expand_control_css": "#expand",
            "expanded_marker_css": "#expanded",
            "loading_css": "#loading:not([hidden])",
            "rows_css": ".device-row",
            "total_count_css": "#total",
            "total_count_pattern": r"of\s+(\d+)",
            "export_control_css": "#export",
        })
        staged = Path(tmp_path / "staged.part")
        count = AirWavePortal(settings, SelectorProfile(css)).download(staged, "test-pass")
        assert count == 2
        assert analyze(staged).rows == 2
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
