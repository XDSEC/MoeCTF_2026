import time
import requests

url = "http://127.0.0.1:8080/chat"
headers = {"Content-Type": "application/json"}
data = {"user": "林林", "msg": 0}

time.sleep(5)

while True:
    try:
        requests.post(url, json=data, headers=headers, timeout=2)
    except Exception:
        pass
    time.sleep(10)