def test_create_trade(client, mocker):
    mock_trade = mocker.MagicMock()
    mock_trade.id = 1
    mocker.patch("routers.trades.trade_service.record_trade", return_value=mock_trade)
    
    response = client.post("/api/trades", json={
        "strike": 10000,
        "option_type": "CE",
        "entry_price": 100,
        "qty": 50
    })
    data = response.json()
    
    assert response.status_code == 200
    assert data["trade_id"] == 1
    assert data["data_source"] == "DB"
    assert "timestamp" in data


def test_close_trade(client, mocker):
    mock_trade = mocker.MagicMock()
    mock_trade.id = 1
    mock_trade.pnl = 500
    mock_trade.net_pnl = 450
    mock_trade.charges = 50
    
    mocker.patch("routers.trades.trade_service.close_trade", return_value=mock_trade)
    
    response = client.put("/api/trades/1/close", json={"exit_price": 110})
    data = response.json()
    
    assert response.status_code == 200
    assert data["pnl"] == 500
    assert data["data_source"] == "DB"


def test_get_active_trades(client, mocker):
    mocker.patch("routers.trades.trade_service.get_active_trades", return_value=[{"id": 1}])
    
    response = client.get("/api/trades/active")
    data = response.json()
    
    assert response.status_code == 200
    assert data["count"] == 1
    assert data["data_source"] == "DB"


def test_trade_metadata(client, mocker):
    mocker.patch("routers.trades.trade_service.get_trade_summary", return_value={"total_pnl": 1000})
    response = client.get("/api/trades/summary")
    data = response.json()
    
    assert response.status_code == 200
    assert data["data_source"] == "DB"
    assert "timestamp" in data
    assert "latency_ms" in data
