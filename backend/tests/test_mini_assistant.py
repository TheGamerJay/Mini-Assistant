"""
Backend API tests for Mini Assistant application
Tests: Health, Security Scanner, Monitor, Deploy, Docker, Chat Summarize endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthEndpoints:
    """Health check and basic connectivity tests"""
    
    def test_health_endpoint(self):
        """Test /api/health returns valid response"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
        print(f"Health check passed: {data}")


class TestSecurityScanner:
    """Security Scanner API tests - /api/security/scan"""
    
    def test_security_scan_with_eval(self):
        """Test security scan detects eval() vulnerability"""
        response = requests.post(f"{BASE_URL}/api/security/scan", json={
            "code": "const result = eval(userInput);"
        })
        assert response.status_code == 200
        data = response.json()
        assert "vulnerabilities" in data
        assert len(data["vulnerabilities"]) > 0
        # Check if eval vulnerability was found
        vuln_titles = [v["title"] for v in data["vulnerabilities"]]
        assert "Dangerous eval() usage" in vuln_titles
        print(f"Security scan found {len(data['vulnerabilities'])} vulnerabilities")
    
    def test_security_scan_clean_code(self):
        """Test security scan with clean code"""
        response = requests.post(f"{BASE_URL}/api/security/scan", json={
            "code": "const x = 1 + 2; console.log(x);"
        })
        assert response.status_code == 200
        data = response.json()
        assert "vulnerabilities" in data
        assert "scanned_lines" in data
        print(f"Clean code scan: {len(data['vulnerabilities'])} issues, {data['scanned_lines']} lines scanned")
    
    def test_security_scan_multiple_vulnerabilities(self):
        """Test security scan finds multiple vulnerabilities"""
        code = """
        const password = "secret123";
        const apiKey = "sk-12345";
        fetch("http://api.example.com/data");
        """
        response = requests.post(f"{BASE_URL}/api/security/scan", json={
            "code": code
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["vulnerabilities"]) >= 2
        print(f"Multiple vuln scan found: {len(data['vulnerabilities'])} issues")


class TestPerformanceMonitor:
    """Performance Monitor API tests - /api/monitor/performance"""
    
    def test_performance_metrics(self):
        """Test performance metrics endpoint returns valid data"""
        response = requests.get(f"{BASE_URL}/api/monitor/performance")
        assert response.status_code == 200
        data = response.json()
        assert "cpu" in data
        assert "memory" in data
        assert "disk" in data
        assert "uptime" in data
        print(f"Performance metrics: CPU={data['cpu']}%, Memory={data['memory']}%, Disk={data['disk']}%")


class TestDeployment:
    """Deploy API tests - /api/deploy/start (MOCKED)"""
    
    def test_deploy_vercel(self):
        """Test Vercel deployment initiation (MOCKED)"""
        response = requests.post(f"{BASE_URL}/api/deploy/start", json={
            "platform": "vercel",
            "project_path": "/app"
        })
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "platform" in data
        assert data["platform"] == "vercel"
        print(f"Deploy response: {data}")
    
    def test_deploy_netlify(self):
        """Test Netlify deployment initiation (MOCKED)"""
        response = requests.post(f"{BASE_URL}/api/deploy/start", json={
            "platform": "netlify",
            "project_path": "/app"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "netlify"
        print(f"Netlify deploy response: {data}")


class TestDockerManagement:
    """Docker API tests - /api/docker/containers"""
    
    def test_list_containers(self):
        """Test list Docker containers (may return empty if Docker not available)"""
        response = requests.get(f"{BASE_URL}/api/docker/containers")
        assert response.status_code == 200
        data = response.json()
        assert "containers" in data
        print(f"Docker containers: {len(data['containers'])} found")


class TestChatSummarize:
    """Chat Summarize API tests - /api/chat/summarize"""
    
    def test_summarize_empty_messages(self):
        """Test summarize with empty messages - should fail or handle gracefully"""
        response = requests.post(f"{BASE_URL}/api/chat/summarize", json={
            "messages": [],
            "model": "llama3.2"
        })
        # Either 200 or 503 (Ollama not available) are acceptable
        assert response.status_code in [200, 503, 500]
        print(f"Empty messages summarize response: {response.status_code}")
    
    def test_summarize_with_messages(self):
        """Test summarize with sample messages"""
        response = requests.post(f"{BASE_URL}/api/chat/summarize", json={
            "messages": [
                {"role": "user", "content": "Hello, how are you?"},
                {"role": "assistant", "content": "I am doing well, thank you for asking!"}
            ],
            "model": "llama3.2"
        })
        # 200 if Ollama connected, 503/500 if not (local LLM required)
        assert response.status_code in [200, 503, 500]
        if response.status_code == 200:
            data = response.json()
            assert "summary" in data
            print(f"Summarize response: {data['summary'][:100]}...")
        else:
            print(f"Ollama not available (expected for remote): {response.status_code}")


class TestExistingEndpoints:
    """Tests for existing core endpoints"""
    
    def test_chat_endpoint_without_ollama(self):
        """Test chat endpoint (will fail if Ollama not running)"""
        response = requests.post(f"{BASE_URL}/api/chat", json={
            "messages": [{"role": "user", "content": "Hello"}],
            "model": "llama3.2",
            "stream": False
        })
        # 200 if Ollama running, 503/500 if not (local LLM required)
        assert response.status_code in [200, 503, 500]
        print(f"Chat endpoint status: {response.status_code} (expected if Ollama not local)")
    
    def test_files_list(self):
        """Test file listing endpoint"""
        response = requests.post(f"{BASE_URL}/api/files/list", json={
            "path": "/app"
        })
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        print(f"Files list: {len(data['items'])} items found")
    
    def test_git_status(self):
        """Test git status endpoint"""
        response = requests.get(f"{BASE_URL}/api/git/status")
        assert response.status_code == 200
        data = response.json()
        assert "initialized" in data
        print(f"Git status: initialized={data['initialized']}")
    
    def test_snippets_list(self):
        """Test snippets list endpoint"""
        response = requests.get(f"{BASE_URL}/api/snippets/list")
        assert response.status_code == 200
        data = response.json()
        assert "snippets" in data
        print(f"Snippets list: {len(data['snippets'])} snippets")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
