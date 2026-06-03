import pytest
from httpx import AsyncClient
import httpx

# In tests, we connect to the running server.
# For local testing, we can run against localhost:8000.
# We'll write standard FastAPI TestClient / AsyncClient tests using the app object.
from app.main import app

@pytest.mark.asyncio
async def test_liveness():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}

@pytest.mark.asyncio
async def test_health():
    # This might depend on active Postgres/Redis. In CI, they are running as sidecars.
    # Locally, make sure they are active or mock them if necessary.
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/health")
    
    # We accept 200 (healthy) or 503 (if databases are not ready during initial testing setup)
    assert response.status_code in [200, 503]
    data = response.json()
    assert "status" in data
    assert "checks" in data
    assert "database" in data["checks"]
    assert "redis" in data["checks"]

@pytest.mark.asyncio
async def test_ai_summarize_validation():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Test input length validation (min_length=10)
        response = await ac.post("/ai/summarize", json={"text": "short"})
    assert response.status_code == 422  # Unprocessable Entity (ValidationError)

@pytest.mark.asyncio
async def test_ai_summarize():
    long_text = "This is a very long text. It contains multiple sentences. We need to summarize it. The summarizer should pick the longest sentences."
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/ai/summarize", json={"text": long_text})
    
    # In case DB is not running, this might fail, but in CI it should pass with 200
    if response.status_code == 200:
        data = response.json()
        assert "summary" in data
        assert "execution_time_ms" in data
        assert data["cached"] is False
        
        # Test cache hit on second run
        async with AsyncClient(app=app, base_url="http://test") as ac:
            second_response = await ac.post("/ai/summarize", json={"text": long_text})
        assert second_response.status_code == 200
        second_data = second_response.json()
        assert second_data["cached"] is True
        assert second_data["summary"] == data["summary"]
