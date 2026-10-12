"""测试环境隔离 + 共享 fixture。

整个测试会话都不读仓库根目录的 .env，否则开发者本机若已配好真实密钥：
1. 用例可能意外打真实上游，产生费用或把结果算进免费额度；
2. `monkeypatch.delenv("LLM_API_KEY")` 一类用例会被 .env 的值重新填上而失败。

`fake_provider`（本地假模型端点）放在这里而不是某个测试文件里，是因为
`test_collate_pipeline.py` 与 `test_analyze_pipeline.py` 都要用它；
它按端口**单例**启动，放 conftest 才能保证整个会话只起一个上游
（放在两个测试文件里各起一份会撞端口）。
"""

from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn

from server import config
from server.tests.fake_llm_provider import app as fake_app

FAKE_PORT = 3099
FAKE_BASE_URL = f"http://127.0.0.1:{FAKE_PORT}/v1"


def _wait_for_port(port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.05)
    raise RuntimeError(f"假模型端点未在 {timeout}s 内就绪（端口 {port}）")


@pytest.fixture(scope="session")
def fake_provider() -> str:
    """在后台线程里跑一个本地假模型，返回其 base_url。"""
    server_config = uvicorn.Config(fake_app, host="127.0.0.1", port=FAKE_PORT, log_level="warning")
    server = uvicorn.Server(server_config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_port(FAKE_PORT)
    yield FAKE_BASE_URL
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session", autouse=True)
def _isolate_env_file(tmp_path_factory: pytest.TempPathFactory):
    missing = tmp_path_factory.mktemp("isolated") / ".env"
    original = config.ENV_FILE
    config.ENV_FILE = missing
    yield
    config.ENV_FILE = original
