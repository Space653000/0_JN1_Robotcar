# M32 gateway 網路修復 Sat Aug 29 12:15:41 AM UTC 2026

## 1) 現況：各自在哪個網路
brain: robotcar_default 
cloud-gw: robotcar_default 
brain 主網路=robotcar_default

## 2) 宣告式修復：移除 cloud-gw 的 networks 區塊（改成自動加入 default）
✅ 已移除 cloud-gw networks 區塊
✅ compose OK

## 3) 重建 cloud-gw
 Container robotcar-cloud-gw-1 Starting 
 Container robotcar-cloud-gw-1 Started 

cloud-gw 現在所在網路：
robotcar_default 

## 4) 保險：把 cloud-gw runtime 接到 brain 的網路
ℹ️  (已同網路或已連接，免補)

## 5) ★重測 brain→cloud-gw
測試容器內部連接：
Traceback (most recent call last):
  File "/usr/local/lib/python3.10/site-packages/urllib3/connection.py", line 204, in _new_conn
    sock = connection.create_connection(
  File "/usr/local/lib/python3.10/site-packages/urllib3/util/connection.py", line 85, in create_connection
    raise err
  File "/usr/local/lib/python3.10/site-packages/urllib3/util/connection.py", line 73, in create_connection
    sock.connect(sa)
ConnectionRefusedError: [Errno 111] Connection refused

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/usr/local/lib/python3.10/site-packages/urllib3/connectionpool.py", line 788, in urlopen
    response = self._make_request(
  File "/usr/local/lib/python3.10/site-packages/urllib3/connectionpool.py", line 493, in _make_request
    conn.request(
  File "/usr/local/lib/python3.10/site-packages/urllib3/connection.py", line 500, in request
    self.endheaders()
  File "/usr/local/lib/python3.10/http/client.py", line 1326, in endheaders
    self._send_output(message_body, encode_chunked=encode_chunked)
  File "/usr/local/lib/python3.10/http/client.py", line 1086, in _send_output
    self.send(msg)
  File "/usr/local/lib/python3.10/http/client.py", line 1024, in send
    self.connect()
  File "/usr/local/lib/python3.10/site-packages/urllib3/connection.py", line 331, in connect
    self.sock = self._new_conn()
  File "/usr/local/lib/python3.10/site-packages/urllib3/connection.py", line 219, in _new_conn
    raise NewConnectionError(
urllib3.exceptions.NewConnectionError: HTTPConnection(host='cloud-gw', port=8000): Failed to establish a new connection: [Errno 111] Connection refused

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/usr/local/lib/python3.10/site-packages/requests/adapters.py", line 667, in send
    resp = conn.urlopen(
  File "/usr/local/lib/python3.10/site-packages/urllib3/connectionpool.py", line 842, in urlopen
    retries = retries.increment(
  File "/usr/local/lib/python3.10/site-packages/urllib3/util/retry.py", line 543, in increment
    raise MaxRetryError(_pool, url, reason) from reason  # type: ignore[arg-type]
urllib3.exceptions.MaxRetryError: HTTPConnectionPool(host='cloud-gw', port=8000): Max retries exceeded with url: /ask (Caused by NewConnectionError("HTTPConnection(host='cloud-gw', port=8000): Failed to establish a new connection: [Errno 111] Connection refused"))

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "/usr/local/lib/python3.10/site-packages/requests/api.py", line 115, in post
    return request("post", url, data=data, json=json, **kwargs)
  File "/usr/local/lib/python3.10/site-packages/requests/api.py", line 59, in request
    return session.request(method=method, url=url, **kwargs)
  File "/usr/local/lib/python3.10/site-packages/requests/sessions.py", line 589, in request
    resp = self.send(prep, **send_kwargs)
  File "/usr/local/lib/python3.10/site-packages/requests/sessions.py", line 703, in send
    r = adapter.send(request, **kwargs)
  File "/usr/local/lib/python3.10/site-packages/requests/adapters.py", line 700, in send
    raise ConnectionError(e, request=request)
requests.exceptions.ConnectionError: HTTPConnectionPool(host='cloud-gw', port=8000): Max retries exceeded with url: /ask (Caused by NewConnectionError("HTTPConnection(host='cloud-gw', port=8000): Failed to establish a new connection: [Errno 111] Connection refused"))

## 6) 服務數（應 9）
time="2026-08-29T08:15:48+08:00" level=warning msg="The \"WEBUI_USER\" variable is not set. Defaulting to a blank string."
time="2026-08-29T08:15:48+08:00" level=warning msg="The \"WEBUI_PASS\" variable is not set. Defaulting to a blank string."
Up 數: 9
