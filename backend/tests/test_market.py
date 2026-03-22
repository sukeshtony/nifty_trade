def test_live_data_priority(client, mocker):
    mocker.patch("routers.market.market_state_manager.get_state", return_value={
        "current_price": 100,
        "change": 1.5,
        "change_pct": 1.5,
        "vwap": 99,
        "ema_9": 99.5,
        "ema_21": 98.5,
        "session_high": 105,
        "session_low": 95
    })

    response = client.get("/api/market/nifty-price")
    data = response.json()

    assert response.status_code == 200
    assert data["ltp"] == 100
    assert data["data_source"] == "LIVE"
    assert data["is_stale"] is False
    assert "timestamp" in data
    assert "latency_ms" in data


def test_cache_fallback(client, mocker):
    mocker.patch("routers.market.market_state_manager.get_state", return_value={})
    mocker.patch("routers.market.cache.get", return_value={
        "ltp": 200,
        "change": 2.5
    })

    response = client.get("/api/market/nifty-price")
    data = response.json()

    assert response.status_code == 200
    assert data["ltp"] == 200
    assert data["data_source"] == "CACHE"
    assert data["is_stale"] is True
    assert "timestamp" in data


def test_api_fallback(client, mocker):
    mocker.patch("routers.market.market_state_manager.get_state", return_value={})
    mocker.patch("routers.market.cache.get", return_value=None)
    mocker.patch("routers.market.market_service.get_full_market_data", return_value={
        "ltp": 300,
        "change": 3.5
    })

    response = client.get("/api/market/nifty-price")
    data = response.json()

    assert response.status_code == 200
    assert data["ltp"] == 300
    assert data["data_source"] == "API"
    assert data["is_stale"] is True
    assert "timestamp" in data


def test_no_data_case(client, mocker):
    mocker.patch("routers.market.market_state_manager.get_state", return_value={})
    mocker.patch("routers.market.cache.get", return_value=None)
    mocker.patch("routers.market.market_service.get_full_market_data", return_value=None)

    response = client.get("/api/market/nifty-price")
    data = response.json()

    assert response.status_code == 200
    assert data["ltp"] == 0
    assert data["error"] == "No data available"
    assert data["data_source"] == "DB" # Defaulted to DB
    assert data["is_stale"] is False # Default is False for DB in our attach_metadata
    assert "timestamp" in data


def test_metadata_fields_present(client, mocker):
    """Test to ensure all required root level metadata fields are present."""
    mocker.patch("routers.market.market_state_manager.get_state", return_value={"current_price": 500})
    response = client.get("/api/market/nifty-price")
    data = response.json()
    
    assert "data_source" in data
    assert "timestamp" in data
    assert "is_stale" in data
    assert "latency_ms" in data
