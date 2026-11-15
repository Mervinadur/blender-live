#!/usr/bin/env python3
"""Download the nature-trail scene's Poly Haven assets (all CC0) into ./assets.
Run in Termux: python3 fetch_assets.py   (re-running skips files already there)."""
import json, os, urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "blender-live-script/1.0"}
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets")
MODELS = ["island_tree_01", "island_tree_02", "dead_tree_trunk_02", "boulder_01", "mountainside",
          "grass_medium_02", "fern_02", "celandine_01", "dandelion_01", "periwinkle_plant",
          "pine_sapling_small", "coast_rocks_05"]
RES = "1k"
HDRI = ("forest_slope", "2k")
TEXTURES = {"forest_ground_04": "1k"}   # trail ground (falls back to any found)


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA)) as r:
        return json.load(r)


def fetch(job):
    url, dest = job
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA)) as r, open(dest + ".part", "wb") as f:
        f.write(r.read())
    os.replace(dest + ".part", dest)
    print("  got", os.path.relpath(dest, OUT), flush=True)


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
with ThreadPoolExecutor(8) as ex:
    list(ex.map(fetch, jobs))
print("done")
