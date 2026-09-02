# /frame.jpg 没画面诊断报告

## 逐环测试结果

### 1. perception 原始端点（主机访问）
```bash
$ curl -s -o /tmp/p.jpg -w "code=%{http_code} size=%{size_download}\n" \
       http://127.0.0.1:8001/frame.jpg
```

**结果**：✓ **工作正常**
```
perception: code=200 size=74033
✓ 文件存在且非空
✓ JPEG image data, 640x480, components 3
```

**结论**：perception 的 /frame.jpg 端点可以从主机访问，返回真实相机画面。

---

### 2. acoustic 代理端点（主机访问）
```bash
$ curl -s -o /tmp/a.jpg -w "code=%{http_code} size=%{size_download}\n" \
       http://127.0.0.1:8011/frame.jpg
```

**结果**：❌ **404 Not Found**
```
acoustic: code=404 size=22
✓ 文件存在（错误响应）
✓ JSON data: {"detail":"Not Found"}
```

**结论**：acoustic 服务**没有 /frame.jpg 端点**，前端无法从后端获取相机画面。

---

### 3. 前端是否有 pollFrame 代码
```bash
$ grep -c "pollFrame\|/frame.jpg\|GET.*frame" acoustic_app/static/index.html
```

**结果**：❌ **0 次匹配**

**结论**：前端**没有定时轮询** /frame.jpg 的代码。

#### 前端实际配置（行 224）：
```javascript
const state = {
  camUrl:'/camera.mjpg'  // ← 指向 acoustic 的虚拟 MJPEG（黑屏）
};
```

#### 前端相机元素（行 260）：
```javascript
camImg.src = state.camUrl;  // ← 设置为 /camera.mjpg
```

**问题**：前端硬编码使用 acoustic 的 /camera.mjpg（虚拟黑屏模式），没有机制拉取真实相机。

---

### 4. acoustic 的 httpx 依赖
```bash
$ python3 -c "import httpx; print(f'✓ httpx {httpx.__version__}')"
```

**结果**：✓ **已安装**
```
httpx 0.28.1
```

**结论**：依赖充分，可以编写 HTTP 代理代码。

---

### 5. 日志分析
```
[INIT] 初始化摄像头...
[CAMERA] 错误: 无法打开 /dev/video0
[WARN] 无法初始化摄像头，将以音频模式运行
INFO: 127.0.0.1:54730 - "GET /frame.jpg HTTP/1.1" 404 Not Found
```

**分析**：
- ✓ acoustic 尝试打开 /dev/video0（失败，被 vision/perception 占用）
- ✓ 因此降级到音频模式
- ✓ 虚拟 /camera.mjpg 返回黑屏
- ❌ 没有代码处理 /frame.jpg 请求，返回 404

---

## 断点研判

### 问题链：
```
perception 有真实相机 ✓
       ↓
acoustic 没代理 /frame.jpg ❌  ← 【断点 1】
       ↓
前端用的是虚拟 /camera.mjpg ❌  ← 【断点 2】
       ↓
/frame.jpg 404 → 前端无法显示真实画面
```

### 具体断点：

#### 【断点 1】acoustic 后端缺少代理端点
**位置**：`src/acoustic_app/server.py`

**现象**：GET /frame.jpg → 404

**原因**：没有以下代码：
```python
@app.get("/frame.jpg")
async def proxy_frame_jpg():
    """代理 perception /frame.jpg"""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get("http://perception:8000/frame.jpg", timeout=5)
            r.raise_for_status()
            return StreamingResponse(
                io.BytesIO(r.content),
                media_type="image/jpeg"
            )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=503)
```

**需要修改的文件**：`acoustic_app/server.py`（无 docker/compose 改动）

#### 【断点 2】前端硬编码虚拟相机
**位置**：`acoustic_app/static/index.html` 行 224, 260

**现象**：
```javascript
camUrl: '/camera.mjpg'  // 虚拟黑屏
camImg.src = state.camUrl;  // 总是显示黑屏
```

**原因**：没有动态 URL 的选项或轮询逻辑。

**修复方案**（前端）：
```javascript
// 定时拉取真实相机帧
setInterval(async () => {
  try {
    const resp = await fetch('/frame.jpg');
    if (resp.ok) {
      const blob = await resp.blob();
      camImg.src = URL.createObjectURL(blob);
    }
  } catch (e) {
    console.warn('Failed to fetch frame:', e);
  }
}, 100);  // 10fps
```

---

## 修复方案（最小改动）

### 短期（推荐，无 docker 改动）
1. **后端**：在 `acoustic_app/server.py` 添加 `@app.get("/frame.jpg")` 代理端点
   - 代码量：~12 行
   - 依赖：httpx（已安装）✓
   - 副作用：无

2. **前端**：在 `acoustic_app/static/index.html` 添加轮询逻辑
   - 代码量：~8 行
   - 副作用：无

### 长期（可选）
1. 为 perception 新增 MJPEG 流端点（见 VISION_STREAM_INVESTIGATION.md）

---

## 当前状态总结

| 组件 | 状态 | 备注 |
|------|------|------|
| perception /frame.jpg | ✓ 工作 | code=200, size=74KB |
| acoustic /frame.jpg | ❌ 缺失 | 404 Not Found |
| 前端轮询代码 | ❌ 无 | 硬编码虚拟相机 |
| httpx 依赖 | ✓ 有 | 0.28.1 |
| 相机初始化 | ⚠️ 虚拟 | 被 vision/perception 占用 |

## 推荐下一步

1. **启用实时相机**：停止 vision/perception 容器 OR 为 perception 添加 MJPEG 流
2. **实施修复**：
   - acoustic 后端：添加 /frame.jpg 代理
   - 前端：添加轮询逻辑
3. **验证**：curl /frame.jpg 返回 200，前端显示真实画面

---
诊断时间：2026-09-02 15:55 UTC+8
诊断范围：唯讀（无任何代码修改）
