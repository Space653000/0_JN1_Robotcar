#!/bin/bash
# ============================================================
# M46：管理（開發）駕駛艙頁面 部署腳本
# 只做：備份 → 寫檔 → 錨點插入 → 語法檢查 → 重啟 → 原始輸出驗證 → commit
# 全程只印「原始指令輸出」，不產生摘要表格。
# ============================================================
set -e
REPO="/home/jetson/0_JN1_Robotcar"
cd "$REPO" || { echo "❌ 找不到 $REPO，請確認實際路徑後手動 cd 進去再貼下面內容"; exit 1; }

TS=$(date +%Y%m%d%H%M%S)
echo "== [1/8] 備份 =="
cp -v acoustic_app/modes.py "acoustic_app/modes.py.bak.$TS"
cp -v acoustic_app/server.py "acoustic_app/server.py.bak.$TS"

echo "== [2/8] 寫入新版 modes.py（含模型覆寫＋原始 GPU 查詢）=="
cat > acoustic_app/modes.py <<'PYEOF'
# acoustic_app/modes.py — JN1 五模式（注意力分配）管理
#
# 理念：全部能力常駐，但 GPU 大模型「一次一個」隨模式切換。
# 切模式＝卸掉不要的大模型、載上要的（背景），並寫下目前模式供各頁顯示。
#
# 大模型槽 big：None=不載大模型 / "chat"=qwen / "vlm"=llava
# 由 server.py 匯入：import modes；提供 get_mode() / set_mode() / MODES
#
# v2（管理頁用）新增：
#   - chat_model / vlm_model 可在管理頁「即時覆寫」（存 data/mode_config.json），
#     不覆寫則沿用環境變數預設。
#   - list_installed_models()：直接問 ollama /api/tags，原始查詢、不用猜的。
#   - get_gpu_status()：直接轉手 ollama /api/ps 原始回應，給網頁「不信摘要、只信原始輸出」用。

import os
import json
import time
import threading

try:
    import httpx
except Exception:  # 萬一沒有 httpx，退用標準庫
    httpx = None
    import urllib.request

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
_ENV_CHAT_MODEL = os.environ.get("JN1_CHAT_MODEL", "qwen2.5:3b")
_ENV_VLM_MODEL = os.environ.get("JN1_VLM_MODEL", "llava")

_HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(_HERE, "..", "data", "mode.json")
CONFIG_FILE = os.path.join(_HERE, "..", "data", "mode_config.json")

MODES = {
    "manage":  {"label": "管理（開發）", "big": None,   "vlm": False, "cloud": True,
                "vision": "normal", "desc": "開發駕駛艙：全功能檢查＋各模式設定＋模式選單"},
    "chat":    {"label": "對話",         "big": "chat", "vlm": False, "cloud": True,
                "vision": "low",    "desc": "停下來聊天/思考/查雲端，不細看"},
    "observe": {"label": "觀察",         "big": "vlm",  "vlm": True,  "cloud": True,
                "vision": "normal", "desc": "專心看仔細：整句描述＋讀字"},
    "patrol":  {"label": "巡航",         "big": None,   "vlm": False, "cloud": False,
                "vision": "high",   "desc": "移動警覺：偵測＋聲音方向＋播報"},
    "standby": {"label": "待機",         "big": None,   "vlm": False, "cloud": False,
                "vision": "off",    "wake": "嗨",
                "desc": "打盹省電，喚醒詞『嗨』叫醒"},
}

DEFAULT_MODE = "manage"
_config_lock = threading.Lock()


def _post(url, body, timeout):
    try:
        if httpx is not None:
            r = httpx.post(url, json=body, timeout=timeout)
            return r.text
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode()
    except Exception:
        return None


def _get(url, timeout):
    try:
        if httpx is not None:
            r = httpx.get(url, timeout=timeout)
            return r.text
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read().decode()
    except Exception:
        return None


def _ollama_unload(model):
    _post(OLLAMA + "/api/generate",
          {"model": model, "keep_alive": 0, "prompt": ""}, timeout=30)


def _ollama_warm(model):
    _post(OLLAMA + "/api/generate",
          {"model": model, "keep_alive": -1, "prompt": "hi", "stream": False}, timeout=180)


def _load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_chat_model():
    return _load_config().get("chat_model") or _ENV_CHAT_MODEL


def get_vlm_model():
    return _load_config().get("vlm_model") or _ENV_VLM_MODEL


def get_model_config():
    cfg = _load_config()
    return {
        "chat_model": cfg.get("chat_model") or _ENV_CHAT_MODEL,
        "vlm_model": cfg.get("vlm_model") or _ENV_VLM_MODEL,
        "chat_model_is_override": bool(cfg.get("chat_model")),
        "vlm_model_is_override": bool(cfg.get("vlm_model")),
        "env_default_chat": _ENV_CHAT_MODEL,
        "env_default_vlm": _ENV_VLM_MODEL,
    }


def set_model_config(chat_model=None, vlm_model=None):
    with _config_lock:
        cfg = _load_config()
        if chat_model is not None:
            v = chat_model.strip()
            if v:
                cfg["chat_model"] = v
            else:
                cfg.pop("chat_model", None)
        if vlm_model is not None:
            v = vlm_model.strip()
            if v:
                cfg["vlm_model"] = v
            else:
                cfg.pop("vlm_model", None)
        _save_config(cfg)
    return get_model_config()


def list_installed_models():
    txt = _get(OLLAMA + "/api/tags", timeout=10)
    if txt is None:
        return {"error": "連不到 ollama /api/tags"}
    try:
        data = json.loads(txt)
        return [m.get("name") for m in data.get("models", []) if m.get("name")]
    except Exception as e:
        return {"error": "解析失敗: " + type(e).__name__}


def get_gpu_status():
    txt = _get(OLLAMA + "/api/ps", timeout=10)
    if txt is None:
        return {"error": "連不到 ollama /api/ps"}
    try:
        return json.loads(txt)
    except Exception:
        return {"raw": txt}


def get_mode():
    try:
        with open(STATE_FILE) as f:
            st = json.load(f)
        if st.get("mode") in MODES:
            return st
    except Exception:
        pass
    return {"mode": DEFAULT_MODE, "ts": 0}


def _apply_async(big):
    chat_model = get_chat_model()
    vlm_model = get_vlm_model()
    if big != "chat":
        _ollama_unload(chat_model)
    if big != "vlm":
        _ollama_unload(vlm_model)
    if big == "chat":
        _ollama_warm(chat_model)
    elif big == "vlm":
        _ollama_warm(vlm_model)


def set_mode(mode):
    if mode not in MODES:
        return {"ok": False, "error": "unknown mode: " + str(mode)}
    m = MODES[mode]
    st = {"mode": mode, "ts": time.time()}
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(st, f)
    except Exception as e:
        return {"ok": False, "error": "write state failed: " + type(e).__name__}
    threading.Thread(target=_apply_async, args=(m["big"],), daemon=True).start()
    return {"ok": True, "mode": mode, "config": m, "switching": bool(m["big"])}
PYEOF
python3 -c "import ast; ast.parse(open('acoustic_app/modes.py').read())" && echo "modes.py 語法 OK" || { echo "❌ modes.py 語法錯誤，停止"; exit 1; }

echo "== [3/8] 寫入 manage.html（管理駕駛艙頁面） =="
mkdir -p acoustic_app/static
cat > acoustic_app/static/manage.html <<'HTMLEOF'
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>JN1 管理（開發）駕駛艙</title>
<style>
  :root{
    --bg:#0b0f14; --panel:#121821; --panel2:#161f2b; --line:#223047;
    --text:#e6edf3; --dim:#8fa3b8; --accent:#4fd1c5; --warn:#f5a623;
    --bad:#ff5c5c; --good:#3ddc84;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);font-family:"PingFang TC","Noto Sans TC","Microsoft JhengHei",system-ui,sans-serif;padding:16px 12px 60px;}
  h1{font-size:1.25rem;margin:0 0 4px}
  .sub{color:var(--dim);font-size:.85rem;margin-bottom:16px}
  .topbar{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:16px}
  .badge{display:inline-block;padding:4px 10px;border-radius:999px;font-size:.8rem;background:var(--panel2);border:1px solid var(--line)}
  .badge.mode-manage{border-color:var(--accent);color:var(--accent)}
  .badge.mode-chat{border-color:#7cc4ff;color:#7cc4ff}
  .badge.mode-observe{border-color:var(--warn);color:var(--warn)}
  .badge.mode-patrol{border-color:#c792ea;color:#c792ea}
  .badge.mode-standby{border-color:var(--dim);color:var(--dim)}
  section{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:14px}
  section h2{font-size:1rem;margin:0 0 10px;color:var(--text);display:flex;align-items:center;gap:8px}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
  .modebtn{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:12px 8px;color:var(--text);cursor:pointer;text-align:center;font-size:.9rem;transition:transform .1s}
  .modebtn:active{transform:scale(.96)}
  .modebtn.active{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset;background:#0f2622}
  .modebtn .ic{font-size:1.4rem;display:block;margin-bottom:4px}
  .modebtn .desc{display:block;color:var(--dim);font-size:.72rem;margin-top:4px;line-height:1.3}
  .cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:10px}
  .card{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:10px;font-size:.85rem}
  .card a{color:var(--text);text-decoration:none}
  .card .name{font-weight:600;display:flex;align-items:center;gap:6px}
  .dot{width:9px;height:9px;border-radius:50%;background:var(--dim);display:inline-block;flex:none}
  .dot.ok{background:var(--good);box-shadow:0 0 6px var(--good)}
  .dot.bad{background:var(--bad);box-shadow:0 0 6px var(--bad)}
  .dot.pending{background:var(--warn)}
  .card .meta{color:var(--dim);font-size:.72rem;margin-top:4px;word-break:break-all}
  .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
  input[type=text],input[type=url],select{background:var(--panel2);border:1px solid var(--line);color:var(--text);padding:8px 10px;border-radius:8px;font-size:.9rem;flex:1;min-width:140px}
  button{background:var(--accent);color:#04211d;border:none;padding:8px 14px;border-radius:8px;font-weight:600;cursor:pointer;font-size:.85rem}
  button.secondary{background:var(--panel2);color:var(--text);border:1px solid var(--line)}
  button:disabled{opacity:.5;cursor:default}
  pre{background:#060a0e;border:1px solid var(--line);border-radius:8px;padding:10px;font-size:.75rem;overflow-x:auto;color:#9fe6d0;white-space:pre-wrap;word-break:break-all}
  .warn-text{color:var(--warn);font-size:.78rem}
  .bad-text{color:var(--bad);font-size:.78rem}
  .good-text{color:var(--good);font-size:.78rem}
  .field-label{font-size:.78rem;color:var(--dim);display:block;margin-bottom:4px}
  .stack{display:flex;flex-direction:column;gap:10px}
  .flex2{display:flex;gap:10px;flex-wrap:wrap}
  .flex2>div{flex:1;min-width:220px}
  .footer-note{color:var(--dim);font-size:.72rem;text-align:center;margin-top:20px}
  @media (min-width:700px){ body{max-width:960px;margin:0 auto} }
</style>
</head>
<body>

<div class="topbar">
  <div>
    <h1>🎛️ JN1 管理（開發）駕駛艙</h1>
    <div class="sub">全部能力常駐・注意力槽隨模式切換・不進終端機</div>
  </div>
  <div style="text-align:right">
    <span class="badge" id="modeBadge">讀取中…</span>
    <div class="sub" id="lastUpdated">—</div>
  </div>
</div>

<section>
  <h2>🧭 模式切換</h2>
  <div class="grid" id="modeGrid"></div>
</section>

<section>
  <h2>🖥️ GPU 注意力槽（ollama 原始查詢，非摘要）<button class="secondary" style="margin-left:auto" onclick="loadGpu()">🔄 重新查詢</button></h2>
  <pre id="gpuRaw">尚未查詢</pre>
</section>

<section>
  <h2>⚙️ 各模式大模型設定</h2>
  <div class="stack">
    <div class="flex2">
      <div>
        <span class="field-label">對話模式（chat）用的模型</span>
        <div class="row">
          <input type="text" id="chatModelInput" list="modelList" placeholder="例如 qwen2.5:3b">
        </div>
      </div>
      <div>
        <span class="field-label">觀察模式（observe / VLM）用的模型</span>
        <div class="row">
          <input type="text" id="vlmModelInput" list="modelList" placeholder="例如 llava 或 moondream">
        </div>
      </div>
    </div>
    <datalist id="modelList"></datalist>
    <div class="row">
      <button onclick="saveModelConfig()">💾 儲存設定</button>
      <button class="secondary" onclick="loadModelConfig()">↺ 重新讀取</button>
      <span id="modelConfigMsg" class="sub"></span>
    </div>
    <div class="sub">已安裝模型（原始查詢 ollama /api/tags）：<span id="installedModels">讀取中…</span></div>
  </div>
</section>

<section>
  <h2>📡 服務即時狀態</h2>
  <div class="cards" id="healthCards"></div>
  <div class="sub" style="margin-top:8px">連接埠設定為目前已知配置，若顯示異常請請終端機核對 docker-compose.yml 實際對外埠。</div>
</section>

<section>
  <h2>🔗 四頁快速入口</h2>
  <div class="cards">
    <div class="card"><a href="dashboard.html">📊 系統儀表板</a></div>
    <div class="card"><a href="index.html">🎧 聲學即時</a></div>
    <div class="card"><a href="vision.html">👁️ 視覺即時</a></div>
    <div class="card"><a href="assistant.html">💬 助手即時</a></div>
  </div>
</section>

<section>
  <h2>🔊 語音測試（雙輸出：J4012 耳機＋此網頁）</h2>
  <div class="row">
    <input type="text" id="ttsText" placeholder="輸入要念的文字…" value="管理駕駛艙語音測試">
    <button onclick="testSpeak()">🔊 念一句</button>
  </div>
  <div class="sub" id="ttsMsg"></div>
</section>

<section>
  <h2>🌐 對外公開網址（Cloudflare Tunnel）</h2>
  <div class="row">
    <input type="url" id="tunnelUrl" placeholder="https://xxxx.trycloudflare.com">
    <button class="secondary" onclick="saveTunnel()">💾 記住</button>
  </div>
  <div class="sub">此網址會變動（重開機後可能不同），請終端機回報目前網址後貼在這裡，方便手機直接開。</div>
</section>

<div class="footer-note">JN1 Robotcar・管理（開發）駕駛艙・開機預設頁面</div>

<script>
const MODE_ICON = {manage:"🎛️", chat:"🗣️", observe:"👁️", patrol:"🏃", standby:"😴"};
let ALL_MODES = {};
let CURRENT_MODE = null;

async function jget(url){
  try{ const r = await fetch(url); return await r.json(); }
  catch(e){ return {error: String(e)}; }
}
async function jpost(url, body){
  try{
    const r = await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body||{})});
    return await r.json();
  }catch(e){ return {error: String(e)}; }
}

function fmtTime(){ return new Date().toLocaleTimeString('zh-TW',{hour12:false}); }

async function loadMode(){
  const st = await jget('/api/mode');
  if(st && st.all){ ALL_MODES = st.all; }
  CURRENT_MODE = st.mode || null;
  const badge = document.getElementById('modeBadge');
  if(CURRENT_MODE && ALL_MODES[CURRENT_MODE]){
    badge.textContent = MODE_ICON[CURRENT_MODE]+' '+ALL_MODES[CURRENT_MODE].label+' 模式';
    badge.className = 'badge mode-'+CURRENT_MODE;
  }else{
    badge.textContent = '⚠️ 無法讀取模式（/api/mode 無回應或格式異常）';
    badge.className = 'badge';
  }
  document.getElementById('lastUpdated').textContent = '更新於 '+fmtTime();
  renderModeGrid();
}

function renderModeGrid(){
  const grid = document.getElementById('modeGrid');
  grid.innerHTML = '';
  const order = ['manage','chat','observe','patrol','standby'];
  order.forEach(key=>{
    const m = ALL_MODES[key];
    if(!m) return;
    const btn = document.createElement('button');
    btn.className = 'modebtn'+(key===CURRENT_MODE?' active':'');
    btn.innerHTML = '<span class="ic">'+(MODE_ICON[key]||'●')+'</span>'+m.label+'<span class="desc">'+m.desc+'</span>';
    btn.onclick = ()=>switchMode(key);
    grid.appendChild(btn);
  });
}

async function switchMode(key){
  document.getElementById('modeBadge').textContent = '切換中…';
  const res = await jpost('/api/mode', {mode:key});
  if(!res || res.ok===false){
    alert('切換失敗：'+(res && res.error ? res.error : '未知錯誤（請看瀏覽器主控台/Network）'));
  }
  await loadMode();
  setTimeout(loadGpu, 2500);
}

async function loadGpu(){
  const pre = document.getElementById('gpuRaw');
  pre.textContent = '查詢中…';
  const res = await jget('/api/mode/gpu');
  pre.textContent = JSON.stringify(res, null, 2);
}

async function loadModelConfig(){
  const cfg = await jget('/api/mode/config');
  if(cfg && !cfg.error){
    document.getElementById('chatModelInput').value = cfg.chat_model || '';
    document.getElementById('vlmModelInput').value = cfg.vlm_model || '';
    document.getElementById('modelConfigMsg').textContent =
      (cfg.chat_model_is_override? '對話=自訂 ':'對話=環境變數預設 ') +
      (cfg.vlm_model_is_override? '／觀察=自訂':'／觀察=環境變數預設');
  }else{
    document.getElementById('modelConfigMsg').textContent = '讀取失敗：'+(cfg&&cfg.error||'');
  }
}

async function saveModelConfig(){
  const chat_model = document.getElementById('chatModelInput').value.trim();
  const vlm_model = document.getElementById('vlmModelInput').value.trim();
  const res = await jpost('/api/mode/config', {chat_model, vlm_model});
  document.getElementById('modelConfigMsg').textContent = res && !res.error ? '已儲存 ✓（下次切到該模式生效）' : '儲存失敗：'+(res&&res.error||'');
}

async function loadInstalledModels(){
  const res = await jget('/api/mode/models');
  const el = document.getElementById('installedModels');
  const list = document.getElementById('modelList');
  if(res && Array.isArray(res.installed)){
    el.textContent = res.installed.length? res.installed.join('、') : '（空清單）';
    list.innerHTML = res.installed.map(n=>'<option value="'+n+'">').join('');
  }else{
    el.textContent = '查不到（'+(res&&(res.installed&&res.installed.error||res.error)||'未知錯誤')+'）';
  }
}

const HEALTH_TARGETS = [
  {key:'asr', name:'ASR 語音辨識', hint:':8003'},
  {key:'tts', name:'TTS 語音合成', hint:':8004'},
  {key:'perception', name:'Perception 偵測', hint:':8001'},
  {key:'ocr', name:'OCR 讀字', hint:':8002'},
  {key:'brain', name:'Brain 大腦', hint:':21500'},
  {key:'ollama', name:'Ollama', hint:':11434'},
];

async function loadHealth(){
  const res = await jget('/api/health');
  const wrap = document.getElementById('healthCards');
  wrap.innerHTML = '';
  HEALTH_TARGETS.forEach(t=>{
    const info = (res && res[t.key]) || {ok:null};
    const dotClass = info.ok===true ? 'ok' : info.ok===false ? 'bad' : 'pending';
    const div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = '<div class="name"><span class="dot '+dotClass+'"></span>'+t.name+'</div>'+
      '<div class="meta">'+t.hint+(info.latency_ms!=null?(' ・ '+info.latency_ms+'ms'):'')+'</div>'+
      '<div class="meta">'+(info.detail? String(info.detail).slice(0,60) : (info.ok===null?'尚未回應':''))+'</div>';
    wrap.appendChild(div);
  });
  if(!res || res.error){
    const div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = '<div class="bad-text">/api/health 尚未部署或無回應</div>';
    wrap.appendChild(div);
  }
}

async function testSpeak(){
  const text = document.getElementById('ttsText').value.trim();
  if(!text) return;
  document.getElementById('ttsMsg').textContent = '送出中…';
  const res = await jpost('/api/tts/say', {text});
  document.getElementById('ttsMsg').textContent = res && res.ok!==false ? '已送出（J4012 耳機播放）✓' : ('失敗：'+(res&&res.error||JSON.stringify(res)));
}

function saveTunnel(){
  const v = document.getElementById('tunnelUrl').value.trim();
  try{ localStorage.setItem('jn1_tunnel_url', v); }catch(e){}
}
function loadTunnelSaved(){
  try{
    const v = localStorage.getItem('jn1_tunnel_url');
    if(v) document.getElementById('tunnelUrl').value = v;
  }catch(e){}
}

async function refreshAll(){
  await loadMode();
  await loadGpu();
  await loadHealth();
}

loadTunnelSaved();
loadModelConfig();
loadInstalledModels();
refreshAll();
setInterval(loadHealth, 8000);
setInterval(loadMode, 15000);
</script>
</body>
</html>
HTMLEOF
echo "manage.html 寫入完成，行數："; wc -l acoustic_app/static/manage.html

echo "== [4/8] 錨點檢查（server.py 是否有既有 /api/mode 區塊） =="
grep -n 'async def api_set_mode' acoustic_app/server.py || { echo "❌ 找不到錨點 api_set_mode，停止，回報我看實際 server.py 內容"; exit 1; }
grep -n 'return _jn1_modes.set_mode' acoustic_app/server.py || { echo "❌ 找不到插入點，停止，回報我"; exit 1; }
grep -c 'api/mode/models' acoustic_app/server.py | grep -q '^0$' || { echo "⚠️ /api/mode/models 似乎已存在，跳過插入避免重複"; SKIP_INSERT=1; }

if [ -z "$SKIP_INSERT" ]; then
python3 <<'PYEOF'
import re

path = "acoustic_app/server.py"
with open(path, encoding="utf-8") as f:
    src = f.read()

anchor = 'return _jn1_modes.set_mode((payload or {}).get("mode", ""))\n'
idx = src.find(anchor)
if idx == -1:
    raise SystemExit("錨點字串找不到，中止（不動檔案）")
insert_at = idx + len(anchor)

new_block = '''

import os as _jn1_os
import time as _jn1_time


@app.get("/api/mode/models")
async def api_mode_models():
    return {"installed": _jn1_modes.list_installed_models()}


@app.get("/api/mode/config")
async def api_mode_config():
    return _jn1_modes.get_model_config()


@app.post("/api/mode/config")
async def api_mode_config_set(payload: dict):
    p = payload or {}
    return _jn1_modes.set_model_config(
        chat_model=p.get("chat_model"),
        vlm_model=p.get("vlm_model"),
    )


@app.get("/api/mode/gpu")
async def api_mode_gpu():
    return _jn1_modes.get_gpu_status()


_JN1_HEALTH_TARGETS = {
    "asr": _jn1_os.environ.get("ASR_HEALTH_URL", "http://127.0.0.1:8003/health"),
    "tts": _jn1_os.environ.get("TTS_HEALTH_URL", "http://127.0.0.1:8004/health"),
    "perception": _jn1_os.environ.get("PERCEPTION_HEALTH_URL", "http://127.0.0.1:8001/health"),
    "ocr": _jn1_os.environ.get("OCR_HEALTH_URL", "http://127.0.0.1:8002/health"),
    "brain": _jn1_os.environ.get("BRAIN_HEALTH_URL", "http://127.0.0.1:21500/health"),
    "ollama": _jn1_os.environ.get("OLLAMA_HEALTH_URL", "http://127.0.0.1:11434/api/tags"),
}


@app.get("/api/health")
async def api_health():
    out = {}
    async with httpx.AsyncClient(timeout=3.0) as c:
        for name, url in _JN1_HEALTH_TARGETS.items():
            t0 = _jn1_time.time()
            try:
                r = await c.get(url)
                out[name] = {"ok": r.status_code < 400, "latency_ms": int((_jn1_time.time()-t0)*1000), "detail": "HTTP "+str(r.status_code)}
            except Exception as e:
                out[name] = {"ok": False, "latency_ms": int((_jn1_time.time()-t0)*1000), "detail": type(e).__name__}
    return out

'''

src2 = src[:insert_at] + new_block + src[insert_at:]
with open(path, "w", encoding="utf-8") as f:
    f.write(src2)
print("插入完成，新檔案行數：", src2.count("\n"))
PYEOF
fi

echo "== [5/8] 語法檢查 server.py =="
python3 -c "import ast; ast.parse(open('acoustic_app/server.py', encoding='utf-8').read())" && echo "server.py 語法 OK" || { echo "❌ server.py 語法錯誤！立刻回復備份："; echo "cp acoustic_app/server.py.bak.$TS acoustic_app/server.py"; exit 1; }

echo "== [6/8] 重啟 jn1-web =="
systemctl --user restart jn1-web
sleep 2
systemctl --user status jn1-web --no-pager -l | head -15

echo "== [7/8] 原始輸出驗證（不信摘要，只信這裡印出來的東西）=="
echo "--- /api/mode ---"
curl -sS http://127.0.0.1:8011/api/mode
echo ""
echo "--- /api/mode/gpu ---"
curl -sS http://127.0.0.1:8011/api/mode/gpu
echo ""
echo "--- /api/mode/models ---"
curl -sS http://127.0.0.1:8011/api/mode/models
echo ""
echo "--- /api/mode/config ---"
curl -sS http://127.0.0.1:8011/api/mode/config
echo ""
echo "--- /api/health ---"
curl -sS http://127.0.0.1:8011/api/health
echo ""
echo "--- manage.html HTTP 狀態 ---"
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8011/manage.html

echo "== [8/8] git commit（不 push，push 留給下一步驗證） =="
git add acoustic_app/modes.py acoustic_app/server.py acoustic_app/static/manage.html
git status --short
git commit -m "M46: 管理（開發）駕駛艙頁面 + /api/mode/models /api/mode/config /api/mode/gpu /api/health

- modes.py：chat_model/vlm_model 可在管理頁即時覆寫（data/mode_config.json）
- modes.py：get_gpu_status()/list_installed_models() 直接轉手 ollama 原始查詢
- server.py：新增 /api/mode/models /api/mode/config(GET/POST) /api/mode/gpu /api/health
- static/manage.html：五模式切換＋GPU原始狀態＋各模式模型設定＋服務即時狀態＋四頁入口＋語音測試

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
git log --oneline -5

echo ""
echo "############################################################"
echo "M46 部署完成。以上全部是原始指令輸出，請直接看，不要相信任何摘要。"
echo "接下來請貼上「驗證區」的內容做兩件事：1) 真的 push  2) LLAVA 孤立測試"
echo "############################################################"
