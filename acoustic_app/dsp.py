"""
XVF3800 音频 DSP 处理模块

提供实时的频谱、方位角 (DoA)、置信度、音量分析。
主要方法：
  - AudioCapture: 从 XVF3800 持续读 2ch @ 16kHz
  - compute_frame: 每个 block 计算 FRAME_CONTRACT 的所有字段
"""

import numpy as np
import sounddevice as sd
from scipy import signal
from scipy.fft import fft, fftfreq, rfft, irfft
import time
import threading
from queue import Queue
import os
import subprocess

class AudioCapture:
    """从 ALSA 装置连续读取音频"""

    def __init__(self, device="hw:1,0", sr=16000, channels=2, blocksize=512):
        self.device = device
        self.sr = sr
        self.channels = channels
        self.blocksize = blocksize
        self.stream = None
        self.buffer = np.zeros((blocksize, channels), dtype=np.float32)
        self.running = False

    def start(self):
        """启动音频流"""
        try:
            self.stream = sd.InputStream(
                device=self.device,
                samplerate=self.sr,
                channels=self.channels,
                blocksize=self.blocksize,
                dtype=np.float32
            )
            self.stream.start()
            self.running = True
            print(f"[DSP] 音频流启动: {self.device} {self.channels}ch @ {self.sr}Hz block={self.blocksize}")
            return True
        except Exception as e:
            print(f"[DSP] 错误: 无法打开 {self.device} — {e}")
            return False

    def read_block(self):
        """读取一个 block"""
        if not self.running or self.stream is None:
            return None
        try:
            data, overflow = self.stream.read(self.blocksize)
            if overflow:
                print(f"[DSP] WARNING: 音频缓冲区溢出")
            return data  # shape: (blocksize, channels)
        except Exception as e:
            print(f"[DSP] 错误读取: {e}")
            return None

    def stop(self):
        """停止音频流"""
        if self.stream:
            self.stream.stop()
            self.stream.close()
        self.running = False
        print("[DSP] 音频流已停止")


class DOAEstimator:
    """方位角 (DoA) 估计"""

    def __init__(self, sr=16000, mic_distance_m=0.1):
        """
        sr: 采样率
        mic_distance_m: 两个麦克风间距（米）
        """
        self.sr = sr
        self.mic_distance = mic_distance_m
        self.sound_speed = 343  # m/s @ 20°C
        self.gcc_history = []
        self.gcc_max_len = 10  # 保持最近 10 帧的历史
        self.onboard_doa = None
        self.onboard_confidence = 0.0
        self._onboard_dead = False  # 标志：一旦失败，后续不再尝试

    # ------------------------------------------------------------------
    # 板載 DoA（XVF3800 晶片自己算的方向）
    #
    # 重大更正：舊版執行 `xvf_host --query-doa` —— 此參數不存在，必定失敗，
    # 於是誤判「方向是硬體天花板」。實機已證明：官方 aarch64 binary 可讀，
    # 指令 AUDIO_MGR_SELECTED_AZIMUTHS，不用 sudo（udev 規則已設）。
    #
    # 設計：背景 daemon 執行緒以 POLL_HZ 輪詢，把最新值寫進共享變數；
    #       WS 幀只讀共享變數，永不在事件迴圈裡開 subprocess（避免阻塞）。
    #
    # 實測輸出格式（第 1 個 (X deg) = 處理後方位角，nan = 當下無語音）：
    #   AUDIO_MGR_SELECTED_AZIMUTHS nan (nan deg) 4.48922 (257.21 deg)
    #   AUDIO_MGR_SELECTED_AZIMUTHS 2.42139 (138.74 deg) 3.09523 (177.34 deg)
    # ------------------------------------------------------------------
    POLL_HZ = 5.0
    STALE_SEC = 1.5

    def _find_xvf(self):
        import shutil as _sh
        cand = [os.environ.get("XVF_HOST", ""),
                "/home/jetson/xvf_host_pkg/xvf_host",
                _sh.which("xvf_host") or ""]
        for p in cand:
            if p and os.path.isfile(p):
                return p
        return None

    def _poll_once(self, exe):
        """跑一次 xvf_host，回 (angle_deg or None, confidence)。非同步安全（在背景執行緒）。"""
        import re as _re
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = os.path.dirname(exe) + ":" + env.get("LD_LIBRARY_PATH", "")
        r = subprocess.run([exe, "AUDIO_MGR_SELECTED_AZIMUTHS"],
                           capture_output=True, text=True, timeout=1.5, env=env)
        txt = (r.stdout or "") + (r.stderr or "")
        if not self._logged_raw:
            line = ""
            for ln in txt.splitlines():
                if "AUDIO_MGR" in ln:
                    line = ln.strip(); break
            print("[DSP] xvf_host 首次原始輸出（供人工核對）: %r" % (line or txt.strip()[:160]))
            self._logged_raw = True
        m = _re.search(r'AUDIO_MGR_SELECTED_AZIMUTHS(.*)', txt)
        if not m:
            return None, 0.0
        vals = _re.findall(r'\(\s*(nan|[-+]?[0-9.]+)\s*deg\s*\)', m.group(1), _re.I)
        # 第 1 個 = 處理後方位角；nan = 當下沒有語音來源 → 無方向
        if vals and vals[0].lower() != "nan":
            try:
                return float(vals[0]) % 360.0, 0.7
            except ValueError:
                return None, 0.0
        return None, 0.0

    def _poll_loop(self):
        import time as _t
        backoff = 1.0
        while not self._stop_poll:
            exe = self._xvf or self._find_xvf()
            if not exe:
                if not self._warned:
                    print("[DSP] 找不到 xvf_host —— 板載 DoA 無法讀取，改用 GCC-PHAT。"
                          "（binary 應在 /home/jetson/xvf_host_pkg）")
                    self._warned = True
                _t.sleep(min(backoff, 30.0)); backoff = min(backoff * 2, 30.0); continue
            self._xvf = exe
            try:
                a, c = self._poll_once(exe)
                self.onboard_doa = a
                self.onboard_confidence = c
                self._onboard_ts = _t.time()
                backoff = 1.0
            except FileNotFoundError:
                self._xvf = None
                _t.sleep(min(backoff, 30.0)); backoff = min(backoff * 2, 30.0); continue
            except Exception:
                pass  # timeout 等暫時性錯誤：跳過這次，不放棄
            _t.sleep(1.0 / self.POLL_HZ)

    def _ensure_poller(self):
        if getattr(self, "_poll_thread", None) is not None:
            return
        import threading as _th
        self._stop_poll = False
        self._xvf = None
        self._warned = False
        self._logged_raw = False
        self._onboard_ts = 0.0
        self._poll_thread = _th.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        print("[DSP] 板載 DoA 背景輪詢已啟動（%.1f Hz，AUDIO_MGR_SELECTED_AZIMUTHS）" % self.POLL_HZ)

    def try_read_onboard_doa(self):
        """非阻塞：只讀背景執行緒放好的最新值。過期或無語音回 (None, 0.0)。"""
        import time as _t
        self._ensure_poller()
        if self.onboard_doa is None:
            return None, 0.0
        if (_t.time() - getattr(self, "_onboard_ts", 0.0)) > self.STALE_SEC:
            return None, 0.0
        return self.onboard_doa, self.onboard_confidence

    def gcc_phat(self, ch0, ch1, max_delay=None):
        """GCC-PHAT FFT-based method for estimating time difference of arrival

        使用频域交叉相关计算（O(n log n) 而非 O(n²) 时域）
        返回: (delay_samples, peak_strength_0_to_1)
        """
        if max_delay is None:
            max_delay = int(self.sr * self.mic_distance / self.sound_speed)

        # FFT-based GCC-PHAT: X0 * conj(X1) / |X0*conj(X1)|
        X0 = rfft(ch0)
        X1 = rfft(ch1)

        # 交叉功率谱
        R = X0 * np.conj(X1)

        # PHAT 加权（相位信息，幅度归一）
        R_phat = R / (np.abs(R) + 1e-8)

        # 逆 FFT 得到时域相关
        cc = irfft(R_phat, n=len(ch0)*2)[:len(ch0)*2]

        # 寻找峰值位置（使用 fftshift 处理环绕）
        cc_shifted = np.fft.fftshift(cc)
        peak_idx_shifted = np.argmax(np.abs(cc_shifted))
        peak_idx = peak_idx_shifted - len(cc) // 2

        # 限制在合理延迟范围
        if abs(peak_idx) > max_delay:
            peak_idx = max_delay if peak_idx > 0 else -max_delay

        delay = peak_idx
        peak_strength = np.abs(cc[peak_idx]) / (np.max(np.abs(cc)) + 1e-10)

        return delay, peak_strength

    def delay_to_angle(self, delay_samples):
        """将延迟样本转换为方位角（度）

        基于简单的 TDOA (Time Difference of Arrival)
        假设 ch0 在左，ch1 在右
        """
        delay_time = delay_samples / self.sr
        angle_rad = np.arcsin(np.clip(
            delay_time * self.sound_speed / self.mic_distance, -1, 1
        ))
        angle_deg = np.degrees(angle_rad)

        # 处理模糊：TDOA 给出 [-90, 90]，但前后有模糊
        # 我们在这里返回 [-90, 90]，让融合阶段用板载 DoA 消歧
        return angle_deg

    def estimate_doa(self, ch0, ch1):
        """融合板载 DoA + GCC-PHAT

        返回: (azimuth_deg_0_359, confidence_0_1, ambiguous, info_dict)
        其中 ambiguous=true 表示有前后模糊（只用 GCC-PHAT）
        """
        info = {'method': 'none', 'gcc_delay': None, 'gcc_strength': None, 'onboard': None}
        ambiguous = False  # 是否有前后模糊

        # 1. 尝试读板载 DoA（每帧调用，但 _onboard_dead 后快速返回）
        onboard_angle, onboard_conf = self.try_read_onboard_doa()
        info['onboard'] = (onboard_angle, onboard_conf) if onboard_angle is not None else None

        # 2. 用 GCC-PHAT 做辅助估计
        delay, peak_strength = self.gcc_phat(ch0, ch1)
        gcc_angle = self.delay_to_angle(delay)
        info['gcc_delay'] = delay
        info['gcc_strength'] = peak_strength

        # 3. 融合
        if onboard_angle is not None:
            # 有板载 DoA：用它作主，GCC-PHAT 验证
            # GCC-PHAT 的 [-90, 90] 对应前半球；[90, 270] 后半球（前后模糊）
            # 用板载 DoA 来消歧
            azimuth = onboard_angle % 360
            # 置信度：板载 + GCC 峰强一致性
            consistency = 1.0 - min(abs(onboard_angle - gcc_angle) / 180.0, 1.0)
            confidence = 0.7 * onboard_conf + 0.3 * (peak_strength * consistency)
            info['method'] = 'hybrid (onboard + gcc)'
            ambiguous = False  # 有板载 DoA 消歧
        else:
            # 无板载 DoA：只用 GCC-PHAT，但置信度要压低
            # 因为 GCC-PHAT 无法消歧前后
            gcc_angle_360 = gcc_angle + 90 if gcc_angle >= 0 else gcc_angle + 270
            azimuth = gcc_angle_360 % 360
            confidence = peak_strength * 0.5  # 压低置信度，表示不确定前后
            info['method'] = 'gcc-phat only (low confidence)'
            ambiguous = True  # 有前后模糊

        # 保存历史用于时间稳定度
        self.gcc_history.append((azimuth, confidence))
        if len(self.gcc_history) > self.gcc_max_len:
            self.gcc_history.pop(0)

        # 时间稳定度：如果最近几帧角度稳定，提高置信度
        if len(self.gcc_history) > 3:
            angles = np.array([a for a, _ in self.gcc_history])
            # 处理 0/360 环绕
            angles_wrapped = np.where(angles > 180, angles - 360, angles)
            angle_std = np.std(angles_wrapped)
            stability = 1.0 / (1.0 + angle_std / 30.0)  # 30° 标准差时稳定性 = 0.5
            confidence = confidence * 0.8 + stability * 0.2

        return azimuth, np.clip(confidence, 0.0, 1.0), ambiguous, info


class SpectrumAnalyzer:
    """频谱分析"""

    def __init__(self, sr=16000, freq_max=8000, n_bins=128):
        self.sr = sr
        self.freq_max = freq_max
        self.n_bins = n_bins
        self.window = signal.windows.hann(512)
        self._avg = None  # 跨帧平均状态

    def compute_spectrum(self, audio, freq_max=None):
        """计算频谱幅度（0Hz 到 freq_max，正规化到 0..1）

        返回: numpy array [n_bins]
        """
        if freq_max is None:
            freq_max = self.freq_max

        # 窗函数处理（如果音频长度足够）
        if len(audio) >= len(self.window):
            audio_windowed = audio[:len(self.window)] * self.window
        else:
            audio_windowed = audio

        # FFT
        spec = np.abs(fft(audio_windowed))
        freqs = fftfreq(len(audio_windowed), 1/self.sr)

        # 只取正频率，截至 freq_max
        valid_freq = freqs <= freq_max
        spec = spec[valid_freq]

        # 重采样到 n_bins
        if len(spec) > self.n_bins:
            indices = np.linspace(0, len(spec)-1, self.n_bins, dtype=int)
            spec = spec[indices]
        elif len(spec) < self.n_bins:
            spec = np.pad(spec, (0, self.n_bins - len(spec)), mode='constant')

        # 正规化到 0..1
        spec_max = np.max(spec)
        if spec_max > 0:
            spec = spec / spec_max

        # B. 高通滤波：80Hz 以下设 0
        # 计算每个 bin 对应的频率
        bin_freqs = np.linspace(0, freq_max, len(spec))
        spec[bin_freqs < 80] = 0

        # C. 边缘清理：最后 2 个 bin 设 0
        spec[-2:] = 0

        # D. 跨帧平均：avg = 0.6*avg + 0.4*new
        if self._avg is None:
            self._avg = spec.copy()
        else:
            self._avg = 0.6 * self._avg + 0.4 * spec
        spec = self._avg.copy()

        return spec[:self.n_bins]  # 确保长度正确


class SimpleClassifier:
    """简单的声音分类（实验性）"""

    CLASSES = ['語音 Speech', '馬達 Motor', '風噪 Hiss', '敲擊 Impact', '機械 Mech', '靜音 Quiet']

    @staticmethod
    def classify(audio, level_db):
        """简单的规则分类

        返回: (class_idx, confidence)
        """
        # 静音检查
        if level_db < -40:
            return 5, 0.9  # 靜音

        # 频谱重心分析
        spec = np.abs(fft(audio))
        freqs = fftfreq(len(audio), 1/16000)[:len(audio)//2]
        spec = spec[:len(audio)//2]

        if np.sum(spec) > 0:
            centroid = np.sum(freqs * spec) / np.sum(spec)
        else:
            centroid = 0

        # 简单规则
        if centroid < 1000:
            return 1, 0.4  # 馬達（低频）
        elif centroid < 3000:
            return 0, 0.5  # 語音（中低频）
        elif centroid < 6000:
            return 0, 0.6  # 語音
        else:
            return 2, 0.3  # 風噪（高频）


def compute_frame(audio_2ch, sr=16000, doa_estimator=None, spectrum_analyzer=None, timestamp_ns=None):
    """計算一個完整的 FRAME_CONTRACT 幀

    參數:
      audio_2ch: shape (N, 2) 浮點音訊
      sr: 採樣率
      doa_estimator: DOAEstimator 實例
      spectrum_analyzer: SpectrumAnalyzer 實例
      timestamp_ns: 納秒時間戳（若為 None 則自動生成）

    傳回: dict 符合 FRAME_CONTRACT
    """
    t_start = time.perf_counter()

    if timestamp_ns is None:
        timestamp_ns = int(time.time_ns())

    if audio_2ch.shape[0] == 0:
        return None

    ch0 = audio_2ch[:, 0]
    ch1 = audio_2ch[:, 1]

    # 1. 音量 (相對 dB)
    rms = np.sqrt(np.mean(ch0**2))
    level_db = 20 * np.log10(rms + 1e-10)

    # 2. 頻譜（高通、邊緣清理、時間平均已在 SpectrumAnalyzer 中處理）
    t_spectrum_start = time.perf_counter()
    if spectrum_analyzer is None:
        spectrum_analyzer = SpectrumAnalyzer(sr)
    spectrum = spectrum_analyzer.compute_spectrum(ch0).tolist()
    spectrum_ms = (time.perf_counter() - t_spectrum_start) * 1000

    # 3. 方位角 + 置信度 + 消歧標誌
    t_gcc_start = time.perf_counter()
    if doa_estimator is None:
        doa_estimator = DOAEstimator(sr)
    azimuth, confidence, ambiguous, _info = doa_estimator.estimate_doa(ch0, ch1)
    gcc_ms = (time.perf_counter() - t_gcc_start) * 1000

    # 4. 分類
    class_idx, _class_conf = SimpleClassifier.classify(ch0, level_db)

    # 5. 組裝 FRAME_CONTRACT 並清洗 NaN/inf
    # 安全值設定
    if np.isnan(azimuth) or np.isinf(azimuth):
        azimuth = 0
    if np.isnan(confidence) or np.isinf(confidence):
        confidence = 0.0
    if np.isnan(level_db) or np.isinf(level_db):
        level_db = -120.0

    # 清洗頻譜中的 NaN/inf
    spectrum = np.nan_to_num(np.array(spectrum), nan=0.0, posinf=1.0, neginf=0.0).tolist()

    frame = {
        't': timestamp_ns,
        'azimuth': int(azimuth),
        'confidence': float(confidence),
        'level': float(level_db),
        'spectrum': spectrum,
        'class': class_idx,
        'ambiguous': bool(ambiguous),  # true = 前後模糊（只用 GCC-PHAT）
        '_timing': {
            'gcc_ms': gcc_ms,
            'spectrum_ms': spectrum_ms
        }
    }

    return frame
