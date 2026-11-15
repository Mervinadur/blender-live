#!/usr/bin/env python3
"""Download the knight scene's Poly Haven assets (all CC0) into ./assets.
Run in Termux: python3 fetch_assets.py   (re-running skips files already there)."""
import json, os, urllib.request

UA = {"User-Agent": "blender-live-script/1.0"}
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "assets")

MODELS = {}   # was chess_set, kite_shield, antique_estoc (v1); the knight is now the user's STL
HDRI = ("castle_zavelstein_cellar", "2k")
TEXTURES = {"metal_plate": "2k", "velour_velvet": "1k", "marble_01": "2k", "monastery_stone_floor": "2k"}
TEX_MAPS = ["diff", "nor_gl", "rough", "arm", "metal"]   # whichever exist


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA)) as r:
        return json.load(r)


def fetch(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA)) as r, open(dest + ".part", "wb") as f:
        f.write(r.read())
    os.replace(dest + ".part", dest)
    print("  got", os.path.relpath(dest, OUT))


for asset, res in MODELS.items():
    print("model", asset)
    g = get_json(f"https://api.polyhaven.com/files/{asset}")["gltf"][res]["gltf"]
    base = os.path.join(OUT, "models", asset)
    fetch(g["url"], os.path.join(base, os.path.basename(g["url"])))
    for rel, info in g["include"].items():
        fetch(info["url"], os.path.join(base, rel))

name, res = HDRI
print("hdri", name)
h = get_json(f"https://api.polyhaven.com/files/{name}")["hdri"][res]["hdr"]
fetch(h["url"], os.path.join(OUT, "hdri", f"{name}_{res}.hdr"))

for asset, res in TEXTURES.items():
    print("texture", asset)
    files = get_json(f"https://api.polyhaven.com/files/{asset}")
    for m in TEX_MAPS:
        key = {"diff": "Diffuse", "nor_gl": "nor_gl", "rough": "Rough", "arm": "arm", "metal": "Metal"}[m]
        if key in files and res in files[key] and "jpg" in files[key][res]:
            fetch(files[key][res]["jpg"]["url"], os.path.join(OUT, "textures", asset, f"{asset}_{m}_{res}.jpg"))
print("done")
