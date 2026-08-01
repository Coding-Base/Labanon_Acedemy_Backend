import socket
import urllib.request
import json
import sys

print("Python version:", sys.version)

print("\n1. Resolving api.paystack.co...")
try:
    ips = socket.gethostbyname_ex('api.paystack.co')
    print("Resolved IPs:", ips)
except Exception as e:
    print("DNS Resolution failed:", e)

print("\n2. Trying to connect to api.paystack.co:443 via socket...")
for ip in ips[2] if 'ips' in locals() else []:
    try:
        s = socket.create_connection((ip, 443), timeout=5)
        print(f"Socket connection to {ip}:443 successful!")
        s.close()
    except Exception as e:
        print(f"Socket connection to {ip}:445 failed:", e)

print("\n3. Testing HTTPS request using urllib...")
try:
    req = urllib.request.Request(
        'https://api.paystack.co/decision/bin/601111',
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        print("urllib success! Status:", response.status)
except Exception as e:
    print("urllib failed:", e)
