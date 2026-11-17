#!/usr/bin/env python3
"""Download the car-street scene's Poly Haven assets (all CC0) into ./assets.
Run in Termux: python3 fetch_assets.py   (re-running skips files already there).
Poly Haven has no real cars, so the hero car is built in code (build.py); these are the street set."""
import json, os, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "blender-live-script/1.0"}
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets")
MODELS = ["street_lamp_01", "street_lamp_02", "fire_hydrant", "concrete_road_barrier", "utility_box_01",
          "water_manhole_cover", "rollershutter_door", "modular_chainlink_fence", "modular_electricity_poles",
          "old_tyre", "covered_car", "modular_street_seating", "Barrel_01", "cardboard_box_01", "trashbag"]
RES = "1k"
HDRI = ("rooftop_night", "2k")        # blue-hour / early night city sky
TEXTURES = {"asphalt_02": "2k", "concrete_pavement": "1k", "brick_wall_02": "1k", "concrete_wall_008": "1k"}


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA)) as r:
        return json.load(r)


def fetch(job):
    url, dest = job
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return 0
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA)) as r, open(dest + ".part", "wb") as f:
        f.write(r.read())
    os.replace(dest + ".part", dest)
    return os.path.getsize(dest)


t0 = time.time()
jobs = []
for asset in MODELS:
    g = get_json(f"https://api.polyhaven.com/files/{asset}")["gltf"][RES]["gltf"]
    base = os.path.join(OUT, "models", asset)
    jobs.append((g["url"], os.path.join(base, os.path.basename(g["url"]))))
    for rel, info in g["include"].items():
        jobs.append((info["url"], os.path.join(base, rel)))
name, res = HDRI
jobs.append((get_json(f"https://api.polyhaven.com/files/{name}")["hdri"][res]["hdr"]["url"],
             os.path.join(OUT, "hdri", f"{name}_{res}.hdr")))
for asset, res in TEXTURES.items():
    files = get_json(f"https://api.polyhaven.com/files/{asset}")
    for key, m in {"Diffuse": "diff", "nor_gl": "nor_gl", "Rough": "rough", "Displacement": "disp"}.items():
        if key in files and res in files[key]:
            fmt = "jpg" if "jpg" in files[key][res] else "png"
            jobs.append((files[key][res][fmt]["url"], os.path.join(OUT, "textures", asset, f"{asset}_{m}_{res}.{fmt}")))
t1 = time.time()
with ThreadPoolExecutor(8) as ex:
    got = sum(ex.map(fetch, jobs))
print(f"done: {len(jobs)} files, {got/1e6:.0f} MB new, index {t1-t0:.0f}s, download {time.time()-t1:.0f}s")
