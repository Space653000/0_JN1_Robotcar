# M31 brain 接雲端顧問 Sat Aug 29 12:08:00 AM UTC 2026

## 0) gateway /ask 先確認(fail-open,失敗也不擋)


## 1) 備份 brain server.py
✅ 已備份 .bak-m31

## 2) Python 精準 patch(插 helper + 改 /ask)
✅ patch 完成

## 3) ★語法閘(錯就還原,brain 不會掛)
✅ 語法 OK

## 4) 疊加 override(掛載 patched server.py + CLOUD_GW_URL,不改主 compose)
✅ docker-compose.override.yml 已建
✅ compose OK

## 5) 只重建 brain(掛載生效)
 Container robotcar-brain-1 Starting 
 Container robotcar-brain-1 Started 
容器狀態：
time="2026-08-29T08:08:12+08:00" level=warning msg="The \"WEBUI_USER\" variable is not set. Defaulting to a blank string."
time="2026-08-29T08:08:12+08:00" level=warning msg="The \"WEBUI_PASS\" variable is not set. Defaulting to a blank string."
NAME               IMAGE                  COMMAND                  SERVICE   CREATED          STATUS         PORTS
robotcar-brain-1   robotcar-brain:0.2.0   "uvicorn server:app …"   brain     10 seconds ago   Up 8 seconds   127.0.0.1:21500->8000/tcp

## 6) 本地功能沒壞?(一般問題,qwen 本地答)
提問：用一句話介紹你自己
{"ok":true,"intent":"chat","reply":"我是你的機器車助理，隨時準備協助你。","source":"llm","tts":{"ok":true,"wav":"/data/logs/tts_1787962097342.wav","engine":"piper","played":false,"play_error":"Connection failure: Access denied\n"}}

## 7) brain->cloud-gw 內網通不通(直接驗 wiring)
測試容器內部連接：
Traceback (most recent call last):
  File "/usr/local/lib/python3.10/site-packages/urllib3/connection.py", line 204, in _new_conn
    sock = connection.create_connection(
  File "/usr/local/lib/python3.10/site-packages/urllib3/util/connection.py", line 60, in create_connection
    for res in socket.getaddrinfo(host, port, family, socket.SOCK_STREAM):
  File "/usr/local/lib/python3.10/socket.py", line 967, in getaddrinfo
    for res in _socket.getaddrinfo(host, port, family, type, proto, flags):
socket.gaierror: [Errno -3] Temporary failure in name resolution

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
  File "/usr/local/lib/python3.10/site-packages/urllib3/connection.py", line 211, in _new_conn
    raise NameResolutionError(self.host, self, e) from e
urllib3.exceptions.NameResolutionError: HTTPConnection(host='cloud-gw', port=8000): Failed to resolve 'cloud-gw' ([Errno -3] Temporary failure in name resolution)

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/usr/local/lib/python3.10/site-packages/requests/adapters.py", line 667, in send
    resp = conn.urlopen(
  File "/usr/local/lib/python3.10/site-packages/urllib3/connectionpool.py", line 842, in urlopen
    retries = retries.increment(
  File "/usr/local/lib/python3.10/site-packages/urllib3/util/retry.py", line 543, in increment
    raise MaxRetryError(_pool, url, reason) from reason  # type: ignore[arg-type]
urllib3.exceptions.MaxRetryError: HTTPConnectionPool(host='cloud-gw', port=8000): Max retries exceeded with url: /ask (Caused by NameResolutionError("HTTPConnection(host='cloud-gw', port=8000): Failed to resolve 'cloud-gw' ([Errno -3] Temporary failure in name resolution)"))

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
requests.exceptions.ConnectionError: HTTPConnectionPool(host='cloud-gw', port=8000): Max retries exceeded with url: /ask (Caused by NameResolutionError("HTTPConnection(host='cloud-gw', port=8000): Failed to resolve 'cloud-gw' ([Errno -3] Temporary failure in name resolution)"))

## 8) ★斷網實測:停 cloud-gw,brain 一般問題仍本地答(不掛不卡)
停止 cloud-gw...
 Container robotcar-cloud-gw-1 Stopped 
gateway 已停，測試本地 fallback：
{"ok":true,"intent":"chat","reply":"我是一個能說中文的語音助手，隨時為你服務。","source":"llm","tts":{"ok":true,"wav":"/data/logs/tts_1787962105578.wav","engine":"piper","played":false,"play_error":"Connection failure: Access denied\n"}}
重啟 cloud-gw...
 Container robotcar-cloud-gw-1 Started 

## 9) 服務數(應 9 Up)
time="2026-08-29T08:08:29+08:00" level=warning msg="The \"WEBUI_USER\" variable is not set. Defaulting to a blank string."
time="2026-08-29T08:08:29+08:00" level=warning msg="The \"WEBUI_PASS\" variable is not set. Defaulting to a blank string."
9
