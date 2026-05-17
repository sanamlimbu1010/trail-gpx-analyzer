#!/usr/bin/env python3
"""Parse GPX and emit route.json (optional; the web app processes GPX in-browser)."""

from __future__ import annotations

import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"gpx": "http://www.topografix.com/GPX/1/1"}

# Distance-smoothed elevation + threshold (tuned to UTMB official ~1600 m D+ on this course;
# Strava reports ~1511 m with DEM correction — raw GPX barometric noise needs heavier filtering).
SMOOTH_WINDOW_M = 75.0
GAIN_THRESHOLD_M = 6.0


def parse_gpx(path: Path) -> list[tuple[float, float, float]]:
    root = ET.parse(path).getroot()
    pts: list[tuple[float, float, float]] = []
    for trkpt in root.findall(".//gpx:trkpt", NS):
        ele_el = trkpt.find("gpx:ele", NS)
        if ele_el is None or not ele_el.text:
            continue
        pts.append(
            (
                float(trkpt.get("lat")),
                float(trkpt.get("lon")),
                float(ele_el.text),
            )
        )
    if not pts:
        raise ValueError(f"No elevation points in {path}")

    deduped = [pts[0]]
    for p in pts[1:]:
        if p != deduped[-1]:
            deduped.append(p)
    return deduped


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def cumulative_distance(pts: list[tuple[float, float, float]]) -> list[float]:
    dist = [0.0]
    for i in range(1, len(pts)):
        d = haversine_m(pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1])
        dist.append(dist[-1] + d)
    return dist


def smooth_elevation_distance(eles: list[float], dist_m: list[float], window_m: float) -> list[float]:
    out: list[float] = []
    for i in range(len(eles)):
        target = dist_m[i] - window_m
        j = i
        while j > 0 and dist_m[j] > target:
            j -= 1
        out.append(sum(eles[j : i + 1]) / (i - j + 1))
    return out


def threshold_gain_loss(
    smoothed: list[float], threshold_m: float
) -> tuple[float, float]:
    gain = 0.0
    loss = 0.0
    running_min = smoothed[0]
    running_max = smoothed[0]
    for e in smoothed:
        if e < running_min:
            running_min = e
        delta_up = e - running_min
        if delta_up >= threshold_m:
            gain += delta_up
            running_min = e

        if e > running_max:
            running_max = e
        delta_down = running_max - e
        if delta_down >= threshold_m:
            loss += delta_down
            running_max = e
    return gain, loss


def segment_metrics(
    dist_m: list[float],
    smoothed: list[float],
    raw_eles: list[float],
    i0: int,
    i1: int,
) -> dict:
    i0 = max(0, min(i0, len(dist_m) - 1))
    i1 = max(i0 + 1, min(i1, len(dist_m) - 1))
    seg_dist = dist_m[i1] - dist_m[i0]
    seg_gain, seg_loss = threshold_gain_loss(smoothed[i0 : i1 + 1], GAIN_THRESHOLD_M)
    grades: list[float] = []
    for i in range(i0 + 1, i1 + 1):
        horiz = dist_m[i] - dist_m[i - 1]
        if horiz < 0.5:
            continue
        g = (smoothed[i] - smoothed[i - 1]) / horiz * 100.0
        grades.append(g)
    max_up = max((g for g in grades if g > 0), default=0.0)
    max_down = min((g for g in grades if g < 0), default=0.0)
    avg_grade = (
        (smoothed[i1] - smoothed[i0]) / seg_dist * 100.0 if seg_dist > 0 else 0.0
    )
    return {
        "start_km": round(dist_m[i0] / 1000, 3),
        "end_km": round(dist_m[i1] / 1000, 3),
        "distance_km": round(seg_dist / 1000, 3),
        "gain_m": round(seg_gain),
        "loss_m": round(seg_loss),
        "elev_start_m": round(smoothed[i0], 1),
        "elev_end_m": round(smoothed[i1], 1),
        "avg_grade_pct": round(avg_grade, 1),
        "max_grade_up_pct": round(max_up, 1),
        "max_grade_down_pct": round(max_down, 1),
    }


def grade_at_points(smoothed: list[float], dist_m: list[float]) -> list[float]:
    grades = [0.0]
    for i in range(1, len(smoothed)):
        horiz = dist_m[i] - dist_m[i - 1]
        if horiz < 0.5:
            grades.append(grades[-1])
        else:
            grades.append((smoothed[i] - smoothed[i - 1]) / horiz * 100.0)
    return grades


def downsample_indices(n: int, target: int = 1200) -> list[int]:
    if n <= target:
        return list(range(n))
    step = (n - 1) / (target - 1)
    return [round(i * step) for i in range(target)]


def build_route(gpx_path: Path) -> dict:
    pts = parse_gpx(gpx_path)
    dist_m = cumulative_distance(pts)
    raw_eles = [p[2] for p in pts]
    smoothed = smooth_elevation_distance(raw_eles, dist_m, SMOOTH_WINDOW_M)
    gain, loss = threshold_gain_loss(smoothed, GAIN_THRESHOLD_M)
    grades = grade_at_points(smoothed, dist_m)

    naive_gain = sum(
        max(0.0, raw_eles[i] - raw_eles[i - 1]) for i in range(1, len(raw_eles))
    )
    naive_loss = sum(
        max(0.0, raw_eles[i - 1] - raw_eles[i]) for i in range(1, len(raw_eles))
    )

    idx = downsample_indices(len(pts))
    lats = [round(pts[i][0], 6) for i in idx]
    lons = [round(pts[i][1], 6) for i in idx]
    km = [round(dist_m[i] / 1000, 4) for i in idx]
    full_lats = [round(p[0], 6) for p in pts]
    full_lons = [round(p[1], 6) for p in pts]
    ele_smooth = [round(smoothed[i], 2) for i in idx]
    ele_raw = [round(raw_eles[i], 2) for i in idx]
    grade_ds = [round(grades[i], 2) for i in idx]

    name = gpx_path.stem
    meta = root_name(gpx_path)

    return {
        "name": meta or name,
        "source_gpx": gpx_path.name,
        "method": {
            "label": f"Filtered D+ ({SMOOTH_WINDOW_M:.0f} m smooth, {GAIN_THRESHOLD_M:.0f} m threshold)",
            "smooth_window_m": SMOOTH_WINDOW_M,
            "threshold_m": GAIN_THRESHOLD_M,
        },
        "summary": {
            "distance_km": round(dist_m[-1] / 1000, 2),
            "elevation_gain_m": round(gain),
            "elevation_loss_m": round(loss),
            "naive_gain_m": round(naive_gain),
            "naive_loss_m": round(naive_loss),
            "min_elevation_m": round(min(raw_eles), 1),
            "max_elevation_m": round(max(raw_eles), 1),
            "point_count": len(pts),
        },
        "profile": {
            "km": km,
            "lat": lats,
            "lon": lons,
            "elevation_m": ele_smooth,
            "elevation_raw_m": ele_raw,
            "grade_pct": grade_ds,
        },
        "full": {
            "km": [round(d / 1000, 5) for d in dist_m],
            "lat": full_lats,
            "lon": full_lons,
            "elevation_m": [round(e, 2) for e in smoothed],
            "grade_pct": [round(g, 3) for g in grades],
        },
    }


def root_name(gpx_path: Path) -> str | None:
    try:
        root = ET.parse(gpx_path).getroot()
        name_el = root.find("gpx:metadata/gpx:name", NS) or root.find(".//gpx:name", NS)
        if name_el is not None and name_el.text:
            return name_el.text.strip()
    except ET.ParseError:
        pass
    return None


def main() -> None:
    gpx = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "mozart100_2026_Marathon_NEW_20260516_f6e6931863.gpx"
    )
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("route.json")
    data = build_route(gpx)
    payload = json.dumps(data, separators=(",", ":"))
    out.write_text(payload)
    js_out = out.with_name("route_data.js")
    js_out.write_text(f"window.ROUTE_DATA = {payload};\n")
    s = data["summary"]
    print(f"Wrote {out}")
    print(f"Wrote {js_out} (for opening index.html directly)")
    print(f"  {data['name']}")
    print(f"  Distance: {s['distance_km']} km")
    print(f"  Gain (filtered): {s['elevation_gain_m']} m")
    print(f"  Loss: {s['elevation_loss_m']} m")
    print(f"  Naive gain (Komoot-like): {s['naive_gain_m']} m")


if __name__ == "__main__":
    main()
