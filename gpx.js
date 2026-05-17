/** Client-side GPX parsing and route metrics (mirrors build_route.py). */
(function (global) {
  const SMOOTH_WINDOW_M = 75;
  const GAIN_THRESHOLD_M = 6;

  function parseGpxDocument(doc) {
    const trkpts = [...doc.getElementsByTagName("*")].filter(
      (el) => el.localName === "trkpt"
    );
    const pts = [];
    for (const trkpt of trkpts) {
      const lat = parseFloat(trkpt.getAttribute("lat"));
      const lon = parseFloat(trkpt.getAttribute("lon"));
      const eleEl = [...trkpt.children].find((c) => c.localName === "ele");
      if (!eleEl?.textContent) continue;
      const ele = parseFloat(eleEl.textContent);
      if (Number.isFinite(lat) && Number.isFinite(lon) && Number.isFinite(ele)) {
        pts.push({ lat, lon, ele });
      }
    }
    if (!pts.length) throw new Error("No track points with elevation found in GPX.");

    const deduped = [pts[0]];
    for (let i = 1; i < pts.length; i++) {
      const p = pts[i];
      const last = deduped[deduped.length - 1];
      if (p.lat !== last.lat || p.lon !== last.lon || p.ele !== last.ele) {
        deduped.push(p);
      }
    }
    return deduped;
  }

  function gpxName(doc, fallback) {
    const nameEl = [...doc.getElementsByTagName("*")].find(
      (el) => el.localName === "name" && el.textContent?.trim()
    );
    return nameEl?.textContent.trim() || fallback;
  }

  function haversineM(lat1, lon1, lat2, lon2) {
    const R = 6371000;
    const p1 = (lat1 * Math.PI) / 180;
    const p2 = (lat2 * Math.PI) / 180;
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(p1) * Math.cos(p2) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
  }

  function cumulativeDistance(pts) {
    const dist = [0];
    for (let i = 1; i < pts.length; i++) {
      dist.push(
        dist[i - 1] +
          haversineM(pts[i - 1].lat, pts[i - 1].lon, pts[i].lat, pts[i].lon)
      );
    }
    return dist;
  }

  function smoothElevationDistance(eles, distM, windowM) {
    const out = [];
    for (let i = 0; i < eles.length; i++) {
      const target = distM[i] - windowM;
      let j = i;
      while (j > 0 && distM[j] > target) j--;
      let sum = 0;
      for (let k = j; k <= i; k++) sum += eles[k];
      out.push(sum / (i - j + 1));
    }
    return out;
  }

  function thresholdGainLoss(smoothed, thresholdM) {
    let gain = 0;
    let loss = 0;
    let runningMin = smoothed[0];
    let runningMax = smoothed[0];
    for (const e of smoothed) {
      if (e < runningMin) runningMin = e;
      const deltaUp = e - runningMin;
      if (deltaUp >= thresholdM) {
        gain += deltaUp;
        runningMin = e;
      }
      if (e > runningMax) runningMax = e;
      const deltaDown = runningMax - e;
      if (deltaDown >= thresholdM) {
        loss += deltaDown;
        runningMax = e;
      }
    }
    return { gain, loss };
  }

  function gradeAtPoints(smoothed, distM) {
    const grades = [0];
    for (let i = 1; i < smoothed.length; i++) {
      const horiz = distM[i] - distM[i - 1];
      if (horiz < 0.5) grades.push(grades[grades.length - 1]);
      else grades.push(((smoothed[i] - smoothed[i - 1]) / horiz) * 100);
    }
    return grades;
  }

  function downsampleIndices(n, target = 1200) {
    if (n <= target) return Array.from({ length: n }, (_, i) => i);
    const step = (n - 1) / (target - 1);
    return Array.from({ length: target }, (_, i) => Math.round(i * step));
  }

  function buildRouteFromGpx(xmlText, sourceName) {
    const doc = new DOMParser().parseFromString(xmlText, "application/xml");
    if (doc.querySelector("parsererror")) {
      throw new Error("Invalid GPX file (XML parse error).");
    }

    const pts = parseGpxDocument(doc);
    const distM = cumulativeDistance(pts);
    const rawEles = pts.map((p) => p.ele);
    const smoothed = smoothElevationDistance(rawEles, distM, SMOOTH_WINDOW_M);
    const { gain, loss } = thresholdGainLoss(smoothed, GAIN_THRESHOLD_M);
    const grades = gradeAtPoints(smoothed, distM);

    let naiveGain = 0;
    let naiveLoss = 0;
    for (let i = 1; i < rawEles.length; i++) {
      const d = rawEles[i] - rawEles[i - 1];
      if (d > 0) naiveGain += d;
      else naiveLoss += -d;
    }

    const idx = downsampleIndices(pts.length);
    const round = (n, d) => +n.toFixed(d);

    return {
      name: gpxName(doc, sourceName.replace(/\.gpx$/i, "")),
      source_gpx: sourceName,
      method: {
        label: `Filtered D+ (${SMOOTH_WINDOW_M} m smooth, ${GAIN_THRESHOLD_M} m threshold)`,
        smooth_window_m: SMOOTH_WINDOW_M,
        threshold_m: GAIN_THRESHOLD_M,
      },
      summary: {
        distance_km: round(distM[distM.length - 1] / 1000, 2),
        elevation_gain_m: Math.round(gain),
        elevation_loss_m: Math.round(loss),
        naive_gain_m: Math.round(naiveGain),
        naive_loss_m: Math.round(naiveLoss),
        min_elevation_m: round(Math.min(...rawEles), 1),
        max_elevation_m: round(Math.max(...rawEles), 1),
        point_count: pts.length,
      },
      profile: {
        km: idx.map((i) => round(distM[i] / 1000, 4)),
        lat: idx.map((i) => round(pts[i].lat, 6)),
        lon: idx.map((i) => round(pts[i].lon, 6)),
        elevation_m: idx.map((i) => round(smoothed[i], 2)),
        elevation_raw_m: idx.map((i) => round(rawEles[i], 2)),
        grade_pct: idx.map((i) => round(grades[i], 2)),
      },
      full: {
        km: distM.map((d) => round(d / 1000, 5)),
        lat: pts.map((p) => round(p.lat, 6)),
        lon: pts.map((p) => round(p.lon, 6)),
        elevation_m: smoothed.map((e) => round(e, 2)),
        grade_pct: grades.map((g) => round(g, 3)),
      },
    };
  }

  global.GpxAnalyzer = {
    SMOOTH_WINDOW_M,
    GAIN_THRESHOLD_M,
    buildRouteFromGpx,
  };
})(typeof window !== "undefined" ? window : globalThis);
