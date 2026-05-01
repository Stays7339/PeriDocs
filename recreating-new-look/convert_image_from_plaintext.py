# ==========================================
# PeriDocs/convert_image_from_plaintext.py
# save-state 2026-05-01T12:45:10 -04:00
# ==========================================


import base64
import re
import subprocess
from datetime import datetime

def detect_filetype(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    if data.lstrip().startswith(b"<svg"):
        return "svg"
    return "bin"

def extract_svgs_and_map(raw: str):
    """
    Extracts SVG blocks from HTML fragments and writes them as standalone files.
    Returns a list of (original_text, filename) mappings for manual replacement.
    """

    svgs = re.findall(r"(<svg\b[^>]*>.*?</svg>)", raw, re.DOTALL)

    mappings = []

    for i, svg in enumerate(svgs):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"svg_{timestamp}_{i}.svg"

        with open(filename, "w", encoding="utf-8") as f:
            f.write(svg)

        print(f"Saved → {filename}")

        mappings.append((svg, filename))

    return mappings


def main():

    raw = subprocess.check_output("pbpaste").decode().strip()

    # --- SVG FIRST PASS (EXTRACTION + FILE OUTPUT) ---
    svg_mappings = extract_svgs_and_map(raw)

    # --- BASE64 / IMAGE PIPELINE ---
    match = re.match(r"data:(image/\w+);base64,(.+)", raw, re.DOTALL)

    if match:
        base64_data = match.group(2)
    else:
        base64_data = raw

    # --- SAFETY GUARD: SKIP INVALID BASE64 FOR SVG/HTML FRAGMENTS ---
    binary = None

    if "<svg" not in raw and "data-svg-wrapper" not in raw:
        try:
            binary = base64.b64decode(base64_data)
        except Exception as e:
            print("Base64 decode failed:", e)
            return

    # --- OUTPUT REPLACEMENT MAP (SVG) ---
    if svg_mappings:
        print("\n--- REPLACEMENT MAP (SVG) ---")
        for original, filename in svg_mappings:
            print("\nFILENAME:", filename)
            print("REPLACE WITH:")
            print(f'src="./{filename}"')

    # --- EXIT EARLY IF NO BINARY IMAGE FOUND ---
    if binary is None:
        return

    # --- FILE TYPE DETECTION + WRITE ---
    ext = detect_filetype(binary)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    filename = f"img_{timestamp}.{ext}"

    with open(filename, "wb") as f:
        f.write(binary)

    print(f"Saved → {filename}")

if __name__ == "__main__":
    main()