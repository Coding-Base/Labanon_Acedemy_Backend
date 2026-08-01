import socket
import urllib.request
import sys

print("Testing connection to open.er-api.com:443 via socket...")
try:
    s = socket.create_connection(('104.26.4.5', 443), timeout=5)
    print("Socket connection to open.er-api.com (104.26.4.5:443) successful!")
    s.close()
except Exception as e:
    print("Socket connection to open.er-api.com failed:", e)

print("\nTesting HTTPS request to open.er-api.com using urllib...")
try:
    with urllib.request.urlopen('https://open.er-api.com/v6/latest/USD', timeout=5) as response:
        print("urllib open.er-api.com success! Status:", response.status)
        data = response.read().decode('utf-8')
        print("Data length:", len(data))
except Exception as e:
    print("urllib open.er-api.com failed:", e)
