#!/usr/bin/env python3
"""
Quick test script for Mini Casino World API endpoints
Run after: python scripts/init_db.py (to set up schema)
"""
import requests
import json

BASE_URL = "http://localhost:5000"

def test_health():
    """Test health endpoint"""
    print("=== Testing Health Endpoint ===")
    r = requests.get(f"{BASE_URL}/healthz")
    print(f"Status: {r.status_code}")
    print(f"Response: {r.json()}")
    print()

def test_blackjack():
    """Test blackjack game"""
    print("=== Testing Blackjack ===")
    data = {"user_id": 1, "bet": 10}
    r = requests.post(f"{BASE_URL}/api/blackjack/play", json=data)
    print(f"Status: {r.status_code}")
    result = r.json()
    print(f"Outcome: {result.get('outcome')}")
    print(f"Cards: {result.get('cards', {})}")
    print(f"Payout: ${result.get('payout', 0)}")
    print(f"New Balance: ${result.get('balance', 0)}")
    print()

def test_roulette():
    """Test roulette game"""
    print("=== Testing Roulette (Red) ===")
    data = {"user_id": 1, "bet": 5, "color": "red"}
    r = requests.post(f"{BASE_URL}/api/roulette/bet", json=data)
    print(f"Status: {r.status_code}")
    result = r.json()
    print(f"Number: {result.get('roll')}")
    print(f"Outcome: {result.get('outcome')}")
    print(f"Payout: ${result.get('payout', 0)}")
    print(f"New Balance: ${result.get('balance', 0)}")
    print()

def test_slots():
    """Test slots game"""
    print("=== Testing Slots ===")
    data = {"user_id": 1, "bet": 1}
    r = requests.post(f"{BASE_URL}/api/slots/spin", json=data)
    print(f"Status: {r.status_code}")
    result = r.json()
    print(f"Symbols: {result.get('symbols', [])}")
    print(f"Multiplier: {result.get('multiplier', 0)}x")
    print(f"Outcome: {result.get('outcome')}")
    print(f"Payout: ${result.get('payout', 0)}")
    print(f"New Balance: ${result.get('balance', 0)}")
    print()

def test_balance():
    """Test balance endpoint"""
    print("=== Testing Balance Check ===")
    r = requests.get(f"{BASE_URL}/api/users/1/balance")
    print(f"Status: {r.status_code}")
    result = r.json()
    print(f"Current Balance: ${result.get('balance', 0)}")
    print()

if __name__ == "__main__":
    print("Mini Casino World API Test Suite")
    print("Make sure the server is running on localhost:5000")
    print("And database is initialized with demo user (ID=1)")
    print()

    try:
        test_health()
        test_balance()
        test_blackjack()
        test_roulette()
        test_slots()
        test_balance()  # Final balance check
        print("✅ All tests completed!")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        print("Make sure:")
        print("1. Server is running: python app.py")
        print("2. Database is set up: python scripts/init_db.py")
        print("3. Demo user exists with some balance")