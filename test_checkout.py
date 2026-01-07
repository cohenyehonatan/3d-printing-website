#!/usr/bin/env python3
import subprocess
import sys
import time

# Kill any existing uvicorn processes
subprocess.run(['pkill', '-f', 'uvicorn'], capture_output=True)
time.sleep(1)

# Start the server
print("Starting uvicorn server...")
proc = subprocess.Popen(
    ['uvicorn', 'api.quote:app', '--reload', '--port', '8003'],
    cwd='/Users/jonathancohen/3d-printing-website',
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

# Give it time to start
time.sleep(3)

# Test the API
import requests
print("\nTesting /api/checkout...")
try:
    response = requests.post(
        'http://localhost:8003/api/checkout',
        json={
            "email": "test@test.com",
            "name": "john",
            "phone": "555",
            "zip_code": "18274",
            "filament_type": "PETG HF",
            "quantity": 1,
            "rush_order": False,
            "volume": 100,
            "weight": 127,
            "use_usps_connect_local": False
        },
        timeout=10
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
except Exception as e:
    print(f"Error: {e}")

# Keep server running
print("\nServer still running. Press Ctrl+C to stop.")
try:
    proc.wait()
except KeyboardInterrupt:
    proc.terminate()
