# Tailscale 設置指南

## 【步驟 1】檢查安裝狀態

```bash
tailscale version
```

✅ 已安裝：v1.102.3

---

## 【步驟 2】執行登入（需要在 Jetson 本機終端）

### 在 Jetson 上執行：

```bash
sudo tailscale up
```

### 預期輸出：

會看到類似的訊息：
```
To authenticate, visit:

    https://login.tailscale.com/a/1234567890abc

```

---

## 【步驟 3】登入 Tailscale

1. **複製登入網址** — 上面的 `https://login.tailscale.com/a/...`
2. **在你的電腦/手機瀏覽器開啟** 這個網址
3. **登入你的 Tailscale 帳號**
4. **授權 Jetson 裝置**

---

## 【步驟 4】驗證連線（登入後）

### 在 Jetson 上執行：

```bash
sudo tailscale ip -4
```

### 預期輸出：

```
100.x.x.x
```

例如：`100.64.42.15`

---

## 【步驟 5】WebUI 訪問地址

### 任何網路都能開啟：

```
http://100.x.x.x:8080
```

例如：`http://100.64.42.15:8080`

---

## 驗證 WebUI 綁定

```bash
sudo netstat -tulpn | grep 8080
```

應該看到：
```
tcp        0      0 0.0.0.0:8080      0.0.0.0:*      LISTEN
```

✅ 0.0.0.0:8080 表示所有網卡都可訪問

---

## 【故障排除】

### 如果 Tailscale 要求重新登入

```bash
sudo tailscale logout
sudo tailscale up
```

### 重啟 Tailscale 服務

```bash
sudo systemctl restart tailscaled
```

### 檢查服務狀態

```bash
sudo systemctl status tailscaled
```

---

## 【使用說明】

現在你可以：
- ✅ 在辦公室連到家裡的機器車 WebUI
- ✅ 在外面連到公司實驗室的機器車
- ✅ 手機、平板、電腦都能用
- ✅ Tailscale 加密，比開放 WiFi 更安全

---

## 【下一步】

1. 執行 `sudo tailscale up`
2. 用瀏覽器登入提供的 URL
3. 取得 Tailscale IP (`sudo tailscale ip -4`)
4. 用 `http://100.x.x.x:8080` 訪問 WebUI

