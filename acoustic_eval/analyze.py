#!/usr/bin/env python3
"""
XVF3800 Raw Microphone Channel Feasibility Analysis
分析 XVF3800 是否能提供 4 個獨立、未經 AGC 的 raw 麥克風通道
"""
import numpy as np
import scipy.signal as signal
import scipy.io.wavfile as wavfile
from pathlib import Path
import sys

def analyze_wav(filepath):
    """主分析函數"""
    print(f"\n{'='*70}")
    print(f"分析檔案: {filepath}")
    print(f"{'='*70}\n")

    # 讀取 WAV
    rate, data = wavfile.read(filepath)
    print(f"採樣率: {rate} Hz")
    print(f"資料型態: {data.dtype}")
    print(f"形狀: {data.shape}")

    if len(data.shape) == 1:
        num_channels = 1
        duration_s = len(data) / rate
    else:
        num_channels = data.shape[1]
        duration_s = data.shape[0] / rate

    print(f"通道數: {num_channels}")
    print(f"持續時間: {duration_s:.1f} 秒\n")

    # 確保 stereo
    if num_channels != 2:
        print(f"警告: 預期 2 通道，但得到 {num_channels}")

    # 提取各通道
    if len(data.shape) == 1:
        ch = [data]
    else:
        ch = [data[:, i] for i in range(num_channels)]

    # ===== A. 每個通道的 RMS 和零檢查 =====
    print("A. RMS 和零檢查")
    print("-" * 70)
    rms_vals = []
    for i, channel in enumerate(ch):
        rms = np.sqrt(np.mean(channel.astype(np.float32)**2))
        is_zero = np.allclose(channel, 0)
        rms_vals.append(rms)
        status = "✗ 全為 0" if is_zero else f"✓ RMS={rms:.2f}"
        print(f"  Ch {i}: {status}")

    # ===== B. 通道相關係數 =====
    print("\nB. 通道相關係數（獨立性檢查）")
    print("-" * 70)
    if len(ch) >= 2:
        corr = np.corrcoef(ch[0].astype(np.float32), ch[1].astype(np.float32))[0, 1]
        print(f"  Ch0 vs Ch1: {corr:.4f}")
        if abs(corr) > 0.9:
            print(f"    ⚠️  高度相關 (>0.9) → 可能是複製或同一路信號")
        elif abs(corr) < 0.3:
            print(f"    ✓ 低相關 (<0.3) → 獨立性良好")
        else:
            print(f"    ≈ 中等相關 (0.3-0.9) → 可能部分處理過")

    # ===== C. AGC 痕跡檢測 =====
    print("\nC. AGC/自動增益控制痕跡")
    print("-" * 70)
    # 計算短時間 RMS 包絡（500ms 窗口）
    window_size = int(0.5 * rate)  # 500ms
    hop_size = window_size // 2

    for i, channel in enumerate(ch):
        rms_env = []
        for j in range(0, len(channel) - window_size, hop_size):
            win_rms = np.sqrt(np.mean(channel[j:j+window_size].astype(np.float32)**2))
            rms_env.append(win_rms)

        rms_env = np.array(rms_env)
        if len(rms_env) > 0:
            rms_std = np.std(rms_env)
            rms_mean = np.mean(rms_env)
            cv = rms_std / rms_mean if rms_mean > 0 else 0

            print(f"  Ch {i}:")
            print(f"    RMS 包絡均值: {rms_mean:.2f}")
            print(f"    RMS 包絡標準差: {rms_std:.2f}")
            print(f"    變異係數 (CV): {cv:.4f}")

            if cv < 0.05:
                print(f"    ⚠️  極低變異 (<0.05) → 強烈 AGC/NS 痕跡（被自動拉平）")
            elif cv < 0.15:
                print(f"    ⚠️  低變異 (0.05-0.15) → 輕度 AGC 痕跡")
            else:
                print(f"    ✓ 正常變異 (>0.15) → 無明顯 AGC")

    # ===== D. 實際頻寬（FFT/PSD） =====
    print("\nD. 實際頻寬和光譜內容")
    print("-" * 70)
    for i, channel in enumerate(ch):
        # 計算 PSD (Welch 方法)
        freqs, psd = signal.welch(channel.astype(np.float32), rate,
                                   nperseg=4096, noverlap=2048)

        # 找頻率帶能量
        psd_db = 10 * np.log10(psd + 1e-10)

        # 檢查幾個關鍵頻率
        idx_8k = np.argmin(np.abs(freqs - 8000))
        idx_16k = np.argmin(np.abs(freqs - 16000)) if rate >= 16000 else -1
        idx_max = np.argmax(psd_db)

        print(f"  Ch {i}:")
        print(f"    峰值頻率: {freqs[idx_max]:.1f} Hz (PSD={psd_db[idx_max]:.1f} dB)")
        print(f"    @ 8 kHz: {psd_db[idx_8k]:.1f} dB")
        if idx_16k >= 0 and freqs[idx_16k] <= rate/2:
            print(f"    @ 16 kHz: {psd_db[idx_16k]:.1f} dB (Nyquist 邊界)")

        # 計算頻帶能量
        band_100_3k = np.mean(psd_db[(freqs >= 100) & (freqs <= 3000)])
        band_3k_8k = np.mean(psd_db[(freqs > 3000) & (freqs <= 8000)])
        band_above_8k = np.mean(psd_db[freqs > 8000])

        print(f"    能量分佈:")
        print(f"      100-3k Hz: {band_100_3k:.1f} dB")
        print(f"      3k-8k Hz:  {band_3k_8k:.1f} dB")
        print(f"      >8k Hz:    {band_above_8k:.1f} dB")

        if band_above_8k < (band_100_3k - 20):
            print(f"    ℹ️  高頻內容稀疏（>20 dB 衰減）")

    # ===== 結論 =====
    print("\n" + "="*70)
    print("初步判定")
    print("="*70)

    raw_channels = sum(1 for r in rms_vals if r > 100)
    all_zero = sum(1 for r in rms_vals if r <= 100)

    print(f"\n實際可用通道: {raw_channels} 個 (非零)")
    print(f"空/靜默通道: {all_zero} 個")

    if raw_channels >= 4:
        print("\n✓ 能取得 4 個通道")
    elif raw_channels == 2:
        print("\n✗ 只能取得 2 個通道（XVF3800 ALSA 限制）")
    else:
        print("\n✗ 可用通道不足")

    # 檢查相關性
    if len(ch) >= 2:
        corr = np.corrcoef(ch[0].astype(np.float32), ch[1].astype(np.float32))[0, 1]
        if abs(corr) > 0.9:
            print("✗ 兩通道高度相關 → 不獨立")
        else:
            print("✓ 通道相關性低 → 相對獨立")

    return {
        'rate': rate,
        'channels': num_channels,
        'duration': duration_s,
        'rms': rms_vals,
        'raw_count': raw_channels
    }

if __name__ == '__main__':
    analyze_wav('ambient_60s.wav')
