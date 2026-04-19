import urllib.request
import json

def test_connect():
    url = "http://127.0.0.1:2026/connect-peer"
    data = json.dumps({
        "peer_id": "PEER_B", 
        "ip": "127.0.0.1", 
        "port": 2027
    }).encode('utf-8')
    
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    
    try:
        with urllib.request.urlopen(req) as response:
            print("Kết quả:", response.read().decode('utf-8'))
    except Exception as e:
        print("Lỗi:", e)

test_connect()