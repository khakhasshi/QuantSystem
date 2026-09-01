from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server
from server import DEFAULT_DB_PATH, create_app


def test_templates_endpoint():
    client = TestClient(create_app(DEFAULT_DB_PATH))
    response = client.get("/api/templates")
    assert response.status_code == 200
    keys = {item["key"] for item in response.json()["templates"]}
    assert {"dual_ma", "bollinger_mean_reversion", "bollinger_breakout", "rsi_reversal"} <= keys


def test_root_static_asset_fallbacks():
    client = TestClient(create_app(DEFAULT_DB_PATH))
    index = client.get("/")
    assert index.status_code == 200
    assert 'href="styles.css"' in index.text
    assert 'src="app.js?v=20260901-9"' in index.text
    assert 'id="llmPanel"' in index.text
    assert client.get("/styles.css").status_code == 200
    assert client.get("/app.js").status_code == 200


def test_llm_status_defaults(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    client = TestClient(create_app(DEFAULT_DB_PATH))
    response = client.get("/api/llm/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "deepseek"
    assert payload["configured"] is False
    assert payload["chat_model"] == "deepseek-v4-flash"


def test_llm_evaluate_requires_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    client = TestClient(create_app(DEFAULT_DB_PATH))
    response = client.post("/api/llm/evaluate", json={"result": {"metrics": {}}})
    assert response.status_code == 400
    assert "API Key" in response.json()["detail"]


def test_llm_evaluate_openai_compatible_payload(monkeypatch):
    captured = {}

    def fake_chat(base_url, api_key, request_body):
        captured["base_url"] = base_url
        captured["api_key"] = api_key
        captured["request_body"] = request_body
        return {"choices": [{"message": {"content": "## 结论\n\n可继续观察。"}}]}

    monkeypatch.setattr(server, "call_openai_compatible_chat", fake_chat)
    client = TestClient(create_app(DEFAULT_DB_PATH))
    response = client.post(
        "/api/llm/evaluate",
        json={
            "api_key": "test-key",
            "base_url": "https://api.deepseek.com/v1",
            "result": {"market": "usstock", "symbol": "AAPL.US", "metrics": {"sharpe": 1.2}},
            "run_request": {"symbol": "AAPL.US"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["markdown"].startswith("## 结论")
    assert captured["base_url"] == "https://api.deepseek.com/v1"
    assert captured["api_key"] == "test-key"
    assert captured["request_body"]["messages"][0]["role"] == "system"


def test_llm_evaluate_falls_back_when_reasoning_has_no_content(monkeypatch):
    models = []

    def fake_chat(_base_url, _api_key, request_body):
        models.append(request_body["model"])
        if len(models) == 1:
            return {"choices": [{"message": {"content": "", "reasoning_content": "hidden reasoning"}}]}
        return {"choices": [{"message": {"content": "## 结论\n\n兜底评价完成。"}}]}

    monkeypatch.setattr(server, "call_openai_compatible_chat", fake_chat)
    client = TestClient(create_app(DEFAULT_DB_PATH))
    response = client.post(
        "/api/llm/evaluate",
        json={
            "api_key": "test-key",
            "thinking_mode": True,
            "result": {"market": "ashare", "symbol": "000001.SZ", "metrics": {"sharpe": 0.64}},
            "run_request": {"symbol": "000001.SZ"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert models == ["deepseek-reasoner", "deepseek-v4-flash"]
    assert payload["model"] == "deepseek-v4-flash"
    assert payload["fallback_model"] == "deepseek-v4-flash"
    assert payload["markdown"].startswith("## 结论")


def test_real_duckdb_backtest_smoke():
    if not DEFAULT_DB_PATH.exists():
        return
    client = TestClient(create_app(DEFAULT_DB_PATH))
    symbols = client.get("/api/symbols?market=usstock&adjustment=qfq&q=AAPL&limit=5")
    assert symbols.status_code == 200
    symbol_items = symbols.json()["symbols"]
    if not symbol_items:
        return
    symbol = symbol_items[0]["symbol"]
    response = client.post(
        "/api/backtest",
        json={
            "market": "usstock",
            "adjustment": "qfq",
            "symbol": symbol,
            "start_date": "2020-01-01",
            "end_date": "2021-12-31",
            "entry_expression": "cross_over(sma(close, 5), sma(close, 20))",
            "exit_expression": "cross_under(sma(close, 5), sma(close, 20))",
            "initial_capital": 100000,
            "fee_bps": 1,
            "target_percent": 0.98,
            "capacity_participation": 0.05,
            "monte_carlo_runs": 50,
            "walk_forward_window": 252,
            "walk_forward_step": 126,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == symbol
    assert payload["metrics"]["final_equity"] > 0
    assert "turnover" in payload["metrics"]
    assert "liquidity" in payload
    assert "robustness" in payload
    assert payload["robustness"]["monte_carlo"]["terminal_return_histogram"]
    assert payload["robustness"]["walk_forward"]["windows"]
    assert "equity" in payload and payload["equity"]


def test_real_duckdb_optimization_smoke():
    if not DEFAULT_DB_PATH.exists():
        return
    client = TestClient(create_app(DEFAULT_DB_PATH))
    symbols = client.get("/api/symbols?market=usstock&adjustment=qfq&q=AAPL&limit=5")
    assert symbols.status_code == 200
    symbol_items = symbols.json()["symbols"]
    if not symbol_items:
        return
    symbol = symbol_items[0]["symbol"]
    response = client.post(
        "/api/optimize",
        json={
            "market": "usstock",
            "adjustment": "qfq",
            "symbol": symbol,
            "start_date": "2020-01-01",
            "end_date": "2021-12-31",
            "template_key": "dual_ma",
            "x_param": "fast",
            "y_param": "slow",
            "ranges": {
                "fast": {"min": 3, "max": 6, "step": 3},
                "slow": {"min": 12, "max": 18, "step": 6},
            },
            "objective": "sharpe",
            "initial_capital": 100000,
            "fee_bps": 1,
            "target_percent": 0.98,
            "capacity_participation": 0.05,
            "max_combinations": 20,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == symbol
    assert payload["total_combinations"] == 4
    assert payload["valid_combinations"] >= 1
    assert payload["best"]["entry_expression"]
    assert payload["heatmap"]["cells"]
