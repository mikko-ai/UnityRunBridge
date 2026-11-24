import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from unityctl.run_events import RunEvents
from unityctl.watch import create_watch_server, read_events, select_session

PNG = b"\x89PNG\r\n\x1a\nfixture"


def create_session(tmp_path, name="测试-01"):
    for folder in ("Assets", "Packages", "ProjectSettings"):
        (tmp_path / folder).mkdir(exist_ok=True)
    session = tmp_path / ".unity-agent" / "sessions" / name
    (session / "artifacts").mkdir(parents=True)
    return session


def test_reads_only_complete_event_rows(tmp_path):
    session = create_session(tmp_path)
    RunEvents(session).emit("run-started", {"status": "running"})
    with (session / "run-events.jsonl").open("a") as stream:
        stream.write('{"truncated":')
    assert len(read_events(session)) == 1
    assert select_session(tmp_path) == session
    assert select_session(tmp_path, "../sessions/测试-01") is None


def test_watch_live_readonly_scoped_endpoints(tmp_path):
    session = create_session(tmp_path)
    frame = session / "artifacts" / "frame.png"
    frame.write_bytes(PNG)
    invalid = session / "artifacts" / "private.png"
    invalid.write_bytes(PNG)
    events = RunEvents(session)
    events.emit("run-started", {"status": "running", "name": "test"})
    server, url = create_watch_server(tmp_path)
    listener = threading.Thread(target=server.serve_forever)
    listener.start()
    try:
        with urlopen(url + "state") as response:
            assert response.headers["Cache-Control"] == "no-store"
            assert json.load(response)["status"] == "running"
        events.emit("step-finished", {"stepIndex": 0, "frame": "frame.png", "status": "passed"})
        events.emit("run-finished", {"status": "passed"})
        with urlopen(url + "state") as response:
            state = json.load(response)
        assert len(state["events"]) == 3 and state["status"] == "passed"
        name = "%E6%B5%8B%E8%AF%95-01"
        with urlopen(url + f"frame/{name}/frame.png") as response:
            assert response.read() == PNG
        host = f"http://127.0.0.1:{server.server_port}/"
        for request in (
            Request(url + "state", headers={"Host": "bad.example"}),
            Request(host + "state"),
            Request(url + f"frame/{name}/private.png"),
            Request(url + "frame/%2e%2e%2fsessions/private.png"),
        ):
            with pytest.raises(HTTPError) as error:
                urlopen(request)
            assert error.value.code == 404
        with pytest.raises(HTTPError) as error:
            urlopen(Request(url + "state", method="POST"))
        assert error.value.code == 501
    finally:
        server.shutdown()
        listener.join()
        server.server_close()
