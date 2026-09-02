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
from scipy.fft import fft, fftfreq
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

    def try_read_onboard_doa(self):
        """尝试从 xvf_host 读板载 DoA

        返回: (angle_deg, confidence) 或 (None, 0.0) 如果不可得
        """
        try:
            # 尝试运行 xvf_host（若存在）
            result = subprocess.run(
                ["xvf_host", "--query-doa"],
                capture_output=True,
                text=True,
                timeout=1.0
            )
            if result.returncode == 0:
                # 假设输出格式为 "angle:XXX confidence:Y.Y"
                parts = result.stdout.strip().split()
                for part in parts:
                    if part.startswith("angle:"):
                        angle = float(part.split(":")[1])
                        return angle % 360, 0.8  # 有板载 DoA 时置信度较高
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            # xvf_host 不可用
            pass
        return None, 0.0

    def gcc_phat(self, ch0, ch1, max_delay=None):
        """GCC-PHAT 方法估计两个通道的时间差

        返回: (delay_samples, peak_strength_0_to_1)
        """
        if max_delay is None:
            max_delay = int(self.sr * self.mic_distance / self.sound_speed)

        # 计算交叉相关
        cc = signal.correlate(ch0, ch1, mode='full')
        lags = signal.correlation_lags(len(ch0), len(ch1), mode='full')

        # 限制在合理范围内
        valid = np.abs(lags) <= max_delay
        cc_valid = cc[valid]
        lags_valid = lags[valid]

        # 找峰值
        peak_idx = np.argmax(np.abs(cc_valid))
        delay = lags_valid[peak_idx]
        peak_strength = np.abs(cc_valid[peak_idx]) / (np.max(np.abs(cc_valid)) + 1e-10)

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

        返回: (azimuth_deg_0_359, confidence_0_1, info_dict)
        """
        info = {'method': 'none', 'gcc_delay': None, 'gcc_strength': None, 'onboard': None}

        # 1. 尝试读板载 DoA
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
        else:
            # 无板载 DoA：只用 GCC-PHAT，但置信度要压低
            # 因为 GCC-PHAT 无法消歧前后
            gcc_angle_360 = gcc_angle + 90 if gcc_angle >= 0 else gcc_angle + 270
            azimuth = gcc_angle_360 % 360
            confidence = peak_strength * 0.5  # 压低置信度，表示不确定前后
            info['method'] = 'gcc-phat only (low confidence)'

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

        return azimuth, np.clip(confidence, 0.0, 1.0), info


class SpectrumAnalyzer:
    """频谱分析"""

    def __init__(self, sr=16000, freq_max=8000, n_bins=128):
        self.sr = sr
        self.freq_max = freq_max
        self.n_bins = n_bins
        self.window = signal.windows.hann(512)

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
    """计算一个完整的 FRAME_CONTRACT 帧

    参数:
      audio_2ch: shape (N, 2) 浮点音频
      sr: 采样率
      doa_estimator: DOAEstimator 实例
      spectrum_analyzer: SpectrumAnalyzer 实例
      timestamp_ns: 纳秒时间戳（若为 None 则自动生成）

    返回: dict 符合 FRAME_CONTRACT
    """
    if timestamp_ns is None:
        timestamp_ns = int(time.time_ns())

    if audio_2ch.shape[0] == 0:
        return None

    ch0 = audio_2ch[:, 0]
    ch1 = audio_2ch[:, 1]

    # 1. 音量 (相对 dB)
    rms = np.sqrt(np.mean(ch0**2))
    level_db = 20 * np.log10(rms + 1e-10)

    # 2. 频谱
    if spectrum_analyzer is None:
        spectrum_analyzer = SpectrumAnalyzer(sr)
    spectrum = spectrum_analyzer.compute_spectrum(ch0).tolist()

    # 3. 方位角 + 置信度
    if doa_estimator is None:
        doa_estimator = DOAEstimator(sr)
    azimuth, confidence, _info = doa_estimator.estimate_doa(ch0, ch1)

    # 4. 分类
    class_idx, _class_conf = SimpleClassifier.classify(ch0, level_db)

    # 5. 组装 FRAME_CONTRACT
    frame = {
        't': timestamp_ns,
        'azimuth': int(azimuth),
        'confidence': float(confidence),
        'level': float(level_db),
        'spectrum': spectrum,
        'class': class_idx
    }

    return frame
