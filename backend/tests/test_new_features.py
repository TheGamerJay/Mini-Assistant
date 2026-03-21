"""
Backend API tests for new Mini Assistant features
Tests: Railway, PostgreSQL, Redis, FixLoop, TesterAgent endpoints
"""
import pytest
import requests
import os


def get_backend_url() -> str:
    return (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:5000").rstrip("/")


def _check_backend_reachable() -> bool:
    try:
        requests.get(f"{get_backend_url()}/api/health", timeout=3)
        return True
    except requests.exceptions.RequestException:
        return False


# Module-level connectivity check — warns once instead of crashing every test
_BACKEND_UP = _check_backend_reachable()
if not _BACKEND_UP:
    import warnings
    warnings.warn(
        f"Backend not running. Start server at {get_backend_url()} "
        "or set REACT_APP_BACKEND_URL. Integration tests will be skipped.",
        UserWarning,
        stacklevel=1,
    )

backend_required = pytest.mark.skipif(
    not _BACKEND_UP,
    reason=(
        f"Backend not running. Start server at {get_backend_url()} "
        "or set REACT_APP_BACKEND_URL."
    ),
)


@backend_required
class TestRailwayIntegration:
    """Railway API tests - /api/railway/* endpoints"""

    def test_railway_projects_invalid_token(self):
        """Test /api/railway/projects with invalid token returns proper error"""
        response = requests.post(f"{get_backend_url()}/api/railway/projects", json={
            "api_token": "invalid_token_12345"
        })
        assert response.status_code in [400, 500]
        print(f"Railway invalid token response: {response.status_code}")

    def test_railway_services_invalid_token(self):
        """Test /api/railway/services with invalid token"""
        response = requests.post(f"{get_backend_url()}/api/railway/services", json={
            "api_token": "invalid_token",
            "project_id": "fake_project_id"
        })
        assert response.status_code in [400, 500]
        print(f"Railway services response: {response.status_code}")

    def test_railway_deploy_endpoint_exists(self):
        """Test /api/railway/deploy endpoint exists"""
        response = requests.post(f"{get_backend_url()}/api/railway/deploy", json={
            "api_token": "test_token",
            "project_id": "test_project"
        })
        assert response.status_code in [200, 400, 500]
        if response.status_code == 200:
            data = response.json()
            assert "status" in data or "message" in data
        print(f"Railway deploy response: {response.status_code}")


@backend_required
class TestPostgreSQLIntegration:
    """PostgreSQL API tests - /api/postgres/* endpoints"""

    def test_postgres_connect_invalid_connection(self):
        """Test /api/postgres/connect with invalid connection string"""
        response = requests.post(f"{get_backend_url()}/api/postgres/connect", json={
            "connection_string": "postgresql://invalid:invalid@localhost:5432/invalid_db"
        })
        assert response.status_code in [500]
        data = response.json()
        assert "detail" in data
        print(f"Postgres connect (invalid) response: {response.status_code}")

    def test_postgres_tables_invalid_connection(self):
        """Test /api/postgres/tables with invalid connection"""
        response = requests.post(f"{get_backend_url()}/api/postgres/tables", json={
            "connection_string": "postgresql://invalid:invalid@localhost:5432/invalid"
        })
        assert response.status_code in [500]
        print(f"Postgres tables (invalid) response: {response.status_code}")

    def test_postgres_query_invalid_connection(self):
        """Test /api/postgres/query with invalid connection"""
        response = requests.post(f"{get_backend_url()}/api/postgres/query", json={
            "connection_string": "postgresql://invalid:invalid@localhost:5432/invalid",
            "query": "SELECT 1"
        })
        assert response.status_code in [500]
        print(f"Postgres query (invalid) response: {response.status_code}")

    def test_postgres_schema_invalid_connection(self):
        """Test /api/postgres/schema with invalid connection"""
        response = requests.post(f"{get_backend_url()}/api/postgres/schema", json={
            "connection_string": "postgresql://invalid:invalid@localhost:5432/invalid",
            "query": "users"
        })
        assert response.status_code in [500]
        print(f"Postgres schema (invalid) response: {response.status_code}")


@backend_required
class TestRedisIntegration:
    """Redis API tests - /api/redis/* endpoints"""

    def test_redis_connect_invalid_host(self):
        """Test /api/redis/connect with invalid host"""
        response = requests.post(f"{get_backend_url()}/api/redis/connect", json={
            "host": "invalid_host_12345.example.com",
            "port": 6379,
            "password": "",
            "db": 0
        })
        assert response.status_code in [500]
        data = response.json()
        assert "detail" in data
        print(f"Redis connect (invalid) response: {response.status_code}")

    def test_redis_keys_invalid_connection(self):
        """Test /api/redis/keys with invalid connection"""
        response = requests.post(f"{get_backend_url()}/api/redis/keys", json={
            "host": "invalid_host.example.com",
            "port": 6379,
            "password": "",
            "db": 0
        })
        assert response.status_code in [500]
        print(f"Redis keys (invalid) response: {response.status_code}")

    def test_redis_get_invalid_connection(self):
        """Test /api/redis/get with invalid connection"""
        response = requests.post(f"{get_backend_url()}/api/redis/get", json={
            "host": "invalid_host.example.com",
            "port": 6379,
            "password": "",
            "db": 0,
            "command": "get",
            "args": ["test_key"]
        })
        assert response.status_code in [500]
        print(f"Redis get (invalid) response: {response.status_code}")

    def test_redis_set_invalid_connection(self):
        """Test /api/redis/set with invalid connection"""
        response = requests.post(f"{get_backend_url()}/api/redis/set", json={
            "host": "invalid_host.example.com",
            "port": 6379,
            "password": "",
            "db": 0,
            "command": "set",
            "args": ["test_key", "test_value"]
        })
        assert response.status_code in [500]
        print(f"Redis set (invalid) response: {response.status_code}")

    def test_redis_delete_invalid_connection(self):
        """Test /api/redis/delete with invalid connection"""
        response = requests.post(f"{get_backend_url()}/api/redis/delete", json={
            "host": "invalid_host.example.com",
            "port": 6379,
            "password": "",
            "db": 0,
            "command": "delete",
            "args": ["test_key"]
        })
        assert response.status_code in [500]
        print(f"Redis delete (invalid) response: {response.status_code}")


@backend_required
class TestFixLoopFeature:
    """FixLoop API tests - /api/fixloop/* endpoints"""

    def test_fixloop_start_valid_url(self):
        """Test /api/fixloop/start with valid URL"""
        response = requests.post(f"{get_backend_url()}/api/fixloop/start", json={
            "url": "https://example.com",
            "error_description": "Testing FixLoop functionality",
            "auto_fix": False
        })
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert "url" in data
        assert "errors" in data
        assert "status" in data
        print(f"FixLoop start response: session_id={data['session_id']}, status={data['status']}")

    def test_fixloop_start_invalid_url(self):
        """Test /api/fixloop/start with invalid URL"""
        response = requests.post(f"{get_backend_url()}/api/fixloop/start", json={
            "url": "http://invalid-domain-12345.nonexistent",
            "error_description": "",
            "auto_fix": False
        })
        assert response.status_code == 200
        data = response.json()
        assert "errors" in data
        print(f"FixLoop invalid URL response: {len(data['errors'])} errors found")

    def test_fixloop_sessions(self):
        """Test /api/fixloop/sessions endpoint"""
        response = requests.get(f"{get_backend_url()}/api/fixloop/sessions")
        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        print(f"FixLoop sessions: {len(data['sessions'])} sessions found")


@backend_required
class TestTesterAgentFeature:
    """Tester Agent API tests - /api/tester/* endpoints"""

    def test_tester_run_smoke_test(self):
        """Test /api/tester/run with smoke test"""
        response = requests.post(f"{get_backend_url()}/api/tester/run", json={
            "url": "https://example.com",
            "test_type": "smoke",
            "endpoints": []
        })
        assert response.status_code == 200
        data = response.json()
        assert "test_run_id" in data
        assert "results" in data
        assert "summary" in data
        assert "passed" in data["summary"]
        assert "failed" in data["summary"]
        assert "total" in data["summary"]
        print(f"Tester run (smoke): {data['summary']}")

    def test_tester_run_api_test(self):
        """Test /api/tester/run with API test and endpoints"""
        response = requests.post(f"{get_backend_url()}/api/tester/run", json={
            "url": get_backend_url(),
            "test_type": "api",
            "endpoints": ["/api/health", "/api/profiles"]
        })
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) >= 2
        print(f"Tester run (api): {data['summary']}")

    def test_tester_generate(self):
        """Test /api/tester/generate endpoint (AI test generation)"""
        response = requests.post(f"{get_backend_url()}/api/tester/generate", json={
            "url": "https://example.com",
            "test_type": "smoke",
            "endpoints": []
        })
        assert response.status_code in [200, 500, 503]
        if response.status_code == 200:
            data = response.json()
            assert "generated_tests" in data
            print(f"Tester generate: Tests generated successfully")
        else:
            print(f"Tester generate: Ollama not available (expected)")

    def test_tester_history(self):
        """Test /api/tester/history endpoint"""
        response = requests.get(f"{get_backend_url()}/api/tester/history")
        assert response.status_code == 200
        data = response.json()
        assert "test_runs" in data
        print(f"Tester history: {len(data['test_runs'])} runs found")


@backend_required
class TestHealthEndpoint:
    """Health check to verify API is running"""

    def test_health_endpoint(self):
        """Test /api/health returns valid response"""
        response = requests.get(f"{get_backend_url()}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print(f"Health check: {data}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
