import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

# We must mock services before importing main because main triggers lifespan
@pytest.fixture(autouse=True)
def mock_lifespan_services(mocker):
    mocker.patch("main.init_db")
    mocker.patch("services.market_data_service.market_service.start_websocket")
    mocker.patch("services.market_data_service.market_service.stop_websocket")

@pytest.fixture
def client():
    # Import app inside the fixture to ensure mocks are applied first
    from main import app
    with TestClient(app) as test_client:
        yield test_client
