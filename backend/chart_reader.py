"""
chart_reader.py
----------------
Reads an uploaded screenshot of a price chart and extracts an
approximate trend line using basic computer vision (no OCR/ML model,
just color-based line tracing -- works on most clean app/website chart
screenshots with a single colored line on a plain background).

Important scope note: this CANNOT identify the ticker, the real price
scale, or the time axis from a screenshot alone -- that information
generally isn't recoverable from pixels with any reliability. What it
CAN do is tell you the visible trend shape (rising / falling / choppy)
and a normalized momentum reading over the visible window. It does not
output a buy/sell instruction.
"""

import numpy as np
from PIL import Image


def _to_array(image_path: str) -> np.ndarray:
    img = Image.open(image_path).convert("RGB")
    return np.array(img)


def extract_trend_line(image_path: str, line_color_hint: str = "auto") -> dict:
    """
    Very lightweight trend extraction:
    1. Find the most saturated/colorful non-background pixel column-by-column
       (assumes chart line stands out from a mostly white/dark flat background).
    2. Build a 1D series of the line's vertical position per column.
    3. Smooth it and compute overall slope + recent momentum.
    """
    arr = _to_array(image_path)
    h, w, _ = arr.shape

    # crop out likely axis/label margins (rough heuristic: middle 90% width, 85% height)
    x0, x1 = int(w * 0.05), int(w * 0.95)
    y0, y1 = int(h * 0.05), int(h * 0.90)
    crop = arr[y0:y1, x0:x1].astype(np.int16)

    # "colorfulness" per pixel = how far the pixel is from gray (R≈G≈B)
    r, g, b = crop[:, :, 0], crop[:, :, 1], crop[:, :, 2]
    colorfulness = (np.abs(r - g) + np.abs(g - b) + np.abs(r - b)).astype(np.float32)

    line_y = np.full(crop.shape[1], np.nan)
    for col in range(crop.shape[1]):
        col_colorfulness = colorfulness[:, col]
        if col_colorfulness.max() < 15:
            continue  # no distinct line pixel in this column
        line_y[col] = np.argmax(col_colorfulness)

    valid = ~np.isnan(line_y)
    if valid.sum() < crop.shape[1] * 0.3:
        return {
            "ok": False,
            "reason": "Could not confidently trace a line in this image. "
                      "Try a cleaner screenshot with a single colored line on a plain background.",
        }

    series = line_y.copy()
    # forward/backward fill small gaps
    idx = np.where(valid)[0]
    series = np.interp(np.arange(len(series)), idx, series[idx])

    # remember: pixel y increases DOWNWARD, so invert for "price-like" direction
    price_like = -series

    # simple smoothing
    window = max(3, len(price_like) // 30)
    kernel = np.ones(window) / window
    smoothed = np.convolve(price_like, kernel, mode="valid")

    overall_slope = float(np.polyfit(np.arange(len(smoothed)), smoothed, 1)[0])
    recent_n = max(5, len(smoothed) // 5)
    recent_slope = float(np.polyfit(np.arange(recent_n), smoothed[-recent_n:], 1)[0])

    total_range = smoothed.max() - smoothed.min() or 1.0
    normalized_overall = overall_slope / total_range
    normalized_recent = recent_slope / total_range

    if normalized_recent > 0.01:
        trend_label = "rising"
    elif normalized_recent < -0.01:
        trend_label = "falling"
    else:
        trend_label = "flat / choppy"

    return {
        "ok": True,
        "trend_label": trend_label,
        "overall_slope_normalized": round(normalized_overall, 4),
        "recent_slope_normalized": round(normalized_recent, 4),
        "points_traced": int(valid.sum()),
        "note": "Trend shape only -- price scale and ticker cannot be reliably "
                "read from a screenshot, and this is not a trading recommendation.",
    }
