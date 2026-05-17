# Trail GPX Analyzer

**[Open the app →](https://sanamlimbu1010.github.io/trail-gpx-analyzer/)**

Plan your trail race or long run pacing from a GPX file — distance, elevation gain, and grade — in your browser. No account, no install, nothing uploaded to a server.

Built for **trail runners** preparing for races like UTMB qualifiers, skyrunning events, or long mountain routes.

---

## Quick start (no coding)

1. Open **[trail-gpx-analyzer](https://sanamlimbu1010.github.io/trail-gpx-analyzer/)**
2. Click **Import GPX** and choose your route file (from Strava export, Komoot, AllTrails, race organiser, etc.)
3. Read the **sidebar**: total distance, elevation gain/loss, min/max altitude
4. Use the **map** and **charts at the bottom**:
   - Move your mouse over the elevation profile → see your position on the map (and the other way around)
   - **Drag** on the elevation chart to select a section → sidebar shows stats for that climb or descent only
   - Click the **faded** parts outside your selection (or **Reset section**) to go back to the full route

### Grade colours (for pacing)

| Colour | Grade | How you might use it |
|--------|-------|----------------------|
| Grey | 0–8% | Runnable |
| Green | 8–15% | Mix run + hike |
| Orange | 15–25% | Hike |
| Red | >25% | Steep hike |

These thresholds are a starting point — adjust your effort to fitness and terrain.

### Elevation gain number

The app uses **filtered elevation gain** (smoothing + noise threshold) so totals are closer to **race organiser / Strava route** figures than raw GPS sums (which often inflate vert). A short note in the sidebar explains the method; you don’t need to change any settings.

---

## Where to get a GPX

- **Strava:** activity or route → ⋯ → Export GPX  
- **Komoot / AllTrails:** export or download route as GPX  
- **Race website:** often provides the official course GPX  

The file must include **elevation** data (`<ele>` tags). Phone-only GPS tracks without elevation may be less accurate.

---

## Privacy

Processing happens **entirely in your browser**. Your GPX is not sent to this site’s server (only map tiles are loaded from the internet).

---

## For developers

Static site: `index.html`, `gpx.js`, deployed via GitHub Pages (`.github/workflows/pages.yml`).

```bash
# optional local preview
python3 -m http.server 8080
# open http://localhost:8080
```

`build_route.py` mirrors the in-browser logic and can export `route.json` for offline experiments; the live app does not require Python.

To change elevation filtering defaults, edit `SMOOTH_WINDOW_M` and `GAIN_THRESHOLD_M` in `gpx.js` (and `build_route.py` if you use the script).

---

## License

Use and share freely. Map tiles © [Mapy.cz](https://api.mapy.cz/copyright) / OpenTopoMap fallback.
