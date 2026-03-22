def test_place_paper_trade(client, mocker):
    mock_trade = mocker.MagicMock()
    mock_trade.id = 2
    mocker.patch("routers.paper_trading.paper_trade_service.place_paper_trade", return_value=mock_trade)
    
    response = client.post("/paper/trade/place", json={
        "strike": 10000,
        "option_type": "PE",
        "entry_price": 50,
        "qty": 25
    })
    data = response.json()
    assert response.status_code == 200
    assert data["trade_id"] == 2
    assert data["data_source"] == "DB"


def test_close_paper_trade(client, mocker):
    mock_trade = mocker.MagicMock()
    mock_trade.id = 2
    mock_trade.pnl = -100
    mock_trade.net_pnl = -140
    mock_trade.exit_price = 45
    
    mocker.patch("routers.paper_trading.paper_trade_service.close_paper_trade", return_value=mock_trade)
    
    response = client.post("/paper/trade/close/2", json={"exit_price": 45})
    data = response.json()
    assert response.status_code == 200
    assert data["exit_price"] == 45
    assert data["data_source"] == "DB"


def test_account_summary(client, mocker):
    mocker.patch("routers.paper_trading.paper_trade_service.get_account_summary", return_value={"balance": 100000})
    
    response = client.get("/paper/account")
    data = response.json()
    assert response.status_code == 200
    assert data["data"]["balance"] == 100000
    assert data["data_source"] == "DB"
