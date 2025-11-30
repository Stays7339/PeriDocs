"""
test_mps.py

REPL-style multi-device embedding benchmark for CPU, MPS, and any available GPU.
Reports timing, memory usage, NaNs, and speed ratios across batch sizes.

Usage:
    python test_mps.py
"""

import torch
import time
import numpy as np
from core.nlp.embeddings import get_embedding

# -------------------------------
# Detect available devices
# -------------------------------
def detect_devices():
    devices = ['cpu']
    if torch.backends.mps.is_available() and torch.backends.mps.is_built():
        devices.append('mps')
    if torch.cuda.is_available():
        devices.append('cuda')
    print("Detected devices:", devices)
    return devices

# -------------------------------
# Device tensor sanity check
# -------------------------------
def check_device(device):
    try:
        t = torch.tensor([1.0, 2.0]).to(device)
        print(f"Tensor moved to {device} successfully.")
    except Exception as e:
        print(f"Device {device} check failed:", e)

# -------------------------------
# Benchmark helper
# -------------------------------
def benchmark_embedding(texts, device='cpu'):
    print(f"\n[{device.upper()}] Benchmarking {len(texts)} embeddings...")
    start = time.time()
    vectors = []
    nan_count = 0
    empty_count = 0
    for t in texts:
        vec = get_embedding(t)  # model_name handled internally by embeddings module
        vectors.append(vec)
        if vec is None or len(vec) == 0:
            empty_count += 1
        if np.isnan(vec).any():
            nan_count += 1
    end = time.time()
    elapsed = end - start
    total_mem = sum(v.nbytes for v in vectors)
    print(f"[{device.upper()}] Time: {elapsed:.4f}s | Total memory: {total_mem/1024**2:.2f} MB")
    if empty_count > 0:
        print(f"WARNING: {empty_count} empty embeddings detected")
    if nan_count > 0:
        print(f"WARNING: {nan_count} embeddings contain NaNs")
    return elapsed, vectors

# -------------------------------
# Run benchmarks across devices
# -------------------------------
def compare_devices(texts, devices):
    results = {}
    for device in devices:
        check_device(device)
        elapsed, _ = benchmark_embedding(texts, device=device)
        results[device] = elapsed
    return results

# -------------------------------
# Print aligned summary table
# -------------------------------
def print_summary(all_results):
    devices = list(next(iter(all_results.values())).keys())
    header = f"{'Batch Size':>12}" + "".join([f"{dev.upper():>15}" for dev in devices])
    print("\n=== Summary Table ===")
    print(header)

    for batch_size, res in all_results.items():
        line = f"{batch_size:12}"
        for dev in devices:
            line += f"{res[dev]:15.4f}s"
        # Optional: add speed ratio vs CPU
        if 'cpu' in res:
            for dev in devices[1:]:
                ratio = res['cpu'] / max(res[dev], 1e-6)
                line += f" ({ratio:6.2f}×)"
        print(line)

# -------------------------------
# Test sentences & batch sizes
# -------------------------------
sentences = [
    "The quick brown fox jumps over the lazy dog.",
    "I am thrilled with the new update!",
    "This is a terrible mistake, I'm so angry.",
    "Life is beautiful and full of surprises.",
    "I feel anxious about tomorrow's meeting."
]

batch_multipliers = [1, 5, 10, 25, 50, 500, 1000]  # scales of 5, 25, 50, etc.

# -------------------------------
# Main REPL execution
# -------------------------------
if __name__ == "__main__":
    print("=== Multi-Device Embedding Benchmark ===")
    devices = detect_devices()
    all_results = {}

    for mult in batch_multipliers:
        batch_size = len(sentences) * mult
        texts = sentences * mult
        print(f"\n--- Batch size: {batch_size} ({mult}×) ---")
        results = compare_devices(texts, devices)
        all_results[batch_size] = results

    print_summary(all_results)
