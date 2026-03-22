def test_signal_response_structure(client, mocker):
    mocker.patch("routers.signals.market_state_manager.get_state", return_value={"current_price": 100})
    mocker.patch("routers.signals.cache.get", return_value=None)
    mocker.patch("routers.signals.market_service.get_candle_data", return_value=[])
    mocker.patch("routers.signals.market_service.get_option_chain", return_value={})
    mocker.patch("routers.signals.compute_all_indicators", return_value={"ema_9": 100})
    mocker.patch("routers.signals.options_engine.analyze", return_value={"pcr": 1.1})
    mocker.patch("routers.signals.strategy_engine.generate_signal", return_value={"final_signal": "BUY_CE", "direction": "BULLISH"})
    mocker.patch("routers.signals.risk_engine.validate_trade_allowed", return_value=(True, ""))
    mocker.patch("routers.signals.risk_engine.calculate_trade_plan", return_value=({"sl": 90, "tg": 120}, ""))
    
    response = client.get("/api/signals/current")
    data = response.json()
    
    assert response.status_code == 200
    assert "signal" in data
    assert "direction" in data
    assert data["signal"] == "BUY_CE"


def test_signal_contains_metadata(client, mocker):
    mocker.patch("routers.signals.market_state_manager.get_state", return_value={"current_price": 100})
    mocker.patch("routers.signals.cache.get", return_value=None)
    mocker.patch("routers.signals.market_service.get_candle_data", return_value=[])
    mocker.patch("routers.signals.market_service.get_option_chain", return_value={})
    mocker.patch("routers.signals.strategy_engine.generate_signal", return_value={"final_signal": "BUY_CE"})
    mocker.patch("routers.signals.risk_engine.validate_trade_allowed", return_value=(True, ""))
    mocker.patch("routers.signals.risk_engine.calculate_trade_plan", return_value=({"sl": 90, "tg": 120}, ""))
    
    response = client.get("/api/signals/current")
    data = response.json()
    
    assert response.status_code == 200
    assert data["data_source"] == "LIVE"
    assert "timestamp" in data
    assert "latency_ms" in data
    assert data["is_stale"] is False


def test_no_trade_scenario(client, mocker):
    mocker.patch("routers.signals.market_state_manager.get_state", return_value={"current_price": 100})
    mocker.patch("routers.signals.cache.get", return_value=None)
    mocker.patch("routers.signals.market_service.get_candle_data", return_value=[])
    mocker.patch("routers.signals.market_service.get_option_chain", return_value={})
    mocker.patch("routers.signals.strategy_engine.generate_signal", return_value={"final_signal": "NO_TRADE"})
    
    response = client.get("/api/signals/current")
    data = response.json()
    
    assert response.status_code == 200
    assert data["signal"] == "NO_TRADE"
