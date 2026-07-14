# ==========================================
# PeriDocs/list_the_table_of_contents_for_this_npz_file.py
# Save-state: 2026-04-29T01:50:40-04:00
# ==========================================

import sys
import os
import numpy as np

EXPECTED_DIM = 1024

if len(sys.argv) < 2:
    raise RuntimeError("Usage: python list_the_table_of_contents_for_this_npz_file.py <full filepath> ")

raw_path = sys.argv[1]
path = os.path.abspath(raw_path)

if not os.path.exists(path):
    raise RuntimeError(f"File not found: {path}")

data = np.load(path)

bad = []

print("FILE:", path)
print("TOTAL KEYS:", len(data.files))
print("===================================")

for k in data.files:
    v = data[k]

    if v.shape != (EXPECTED_DIM,):
        bad.append((k, "bad_shape", v.shape))

    elif getattr(v, "size", 0) == 0:
        bad.append((k, "empty", v.shape))

    elif (v == 0).all():
        bad.append((k, "zero_vector", v.shape))

    print(k, "shape=", v.shape)

print("===================================")
print("BAD ENTRIES:", len(bad))

for item in bad[:20]:
    print(item)