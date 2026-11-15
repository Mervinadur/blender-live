# Blender Live: notes for Claude

## What
Blender (Debian trixie package, in `proot-distro` Debian) shown in the Termux:X11 app. The blender-mcp
add-on (`addon.py`, fetched by `setup.sh`, pinned commit, gitignored) runs a socket server on
localhost:9876 (auto-start defaults on). Claude Code talks to it via the `blender` MCP server
(user scope: `proot-distro login debian --shared-tmp -- env DISABLE_TELEMETRY=true … /opt/blender-mcp/bin/blender-mcp`, a venv with
blender-mcp 2.0.0 from PyPI; Termux's `uv` is visible in Debian but is a Termux binary, so not used).

## Files
- `setup.sh`: one-time install (x11-repo, termux-x11-nightly, Debian, blender, python3-requests, blender-mcp venv,
  MCP registration, add-on).
- `start-blender.sh`: starts termux-x11 :0, opens the app, runs Blender with `--python addon.py`.
  Binds `models/` → `/root/models` inside Debian. Uses llvmpipe (software GL).
- `render-remote.sh`: renders a .blend on a RunPod GPU (REST API v2, one GPU type per create call so the script loops 4090/3090/A5000 × COMMUNITY/SECURE, `ubuntu:24.04` image, start command installs sshd +
  official Blender x64 tarball; Cycles set to OptiX/CUDA via `gpu.py`), pulls frames to `<model>/remote_frames/`, deletes the pod
  on exit + a self-delete timer on the pod (MAX_MINUTES=90). Key in `~/.config/runpod/api_key` (user puts it there, never me);
  SSH key `~/.ssh/runpod_ed25519`. Packs assets locally first (4.3), so 5.x files need `PACK=0 BLENDER_VERSION=5.2.2`.
- `models/`: the user's working files (gitignored), **one folder per model** (`models/<model-name>/`: .blend, source files,
  render frames, tests). Currently `coffee-mug/`, `astronaut/`, `man-rigged/`, `knight/`. New model → new folder. Inside Debian: `/root/models/<model-name>/`.
- `examples/`: finished models committed so the user can download them from GitHub (e.g. `coffee_mug.stl`).

## Rules
- The add-on's generation integrations (Hyper3D/Rodin, Tripo, Meshy, World Labs, Sketchfab) stay **off**.
  This follows the spirit of the user's generation ban; ask before enabling any.
- Keep telemetry **off**: the MCP server sends usage events (and can upload screenshots/code) to its author's
  Supabase unless `DISABLE_TELEMETRY` etc. are set; the add-on's `telemetry_consent` pref defaults off. Leave it off.
- `claude mcp ...` must run from `~` (it fails elsewhere with "preload not found ./.local/share/claude/setdns.js").
- I can't see the X11 window. Verify through MCP scene info / dimensions, or render previews to `models/<model-name>/`.

## Status (2026-11-15)
- Done: Debian + Blender 4.3.2 + python3-requests installed; blender-mcp 2.0.0 venv at `/opt/blender-mcp`;
  `blender` MCP server registered in Claude Code (user scope, shows Connected); Termux:X11 app installed.
- 2026-11-14: First live test works. Blender 4.3.2 GUI runs in Termux:X11 on llvmpipe, the add-on opens
  port 9876, and Claude's `blender` MCP tools reach it (get_scene_info returned the default cube scene).
- Fix that made it work: Blender died with SIGILL because llvmpipe's LLVM read "CPU part 0xd81" (Cortex-A720)
  from /proc/cpuinfo and emitted SVE code (`ptrue p0.s`), and this phone has SVE off (no `sve` in Features).
  `start-blender.sh` now writes `cpuinfo-nosve` (CPU part → 0xd41, Cortex-A78; gitignored) and binds it over
  /proc/cpuinfo in Debian. The Mesa shader cache had stored SVE code, so I deleted
  `/root/.cache/mesa_shader_cache*`. Do that again if SIGILL comes back.
- "Not connected" in the X11 app only means no `termux-x11 :0` server is running; start-blender.sh starts it.
- 2026-11-14: The `look` tool needed two fixes. (1) It needs numpy inside Blender's Python, so I installed
  `python3-numpy` in Debian (also added to setup.sh). (2) Blender runs with `--shared-tmp` (Termux /tmp), but the MCP
  server ran without it, so it couldn't find the screenshot in /tmp. I re-registered the MCP server with
  `--shared-tmp` (and changed setup.sh to match). This takes effect from the next Claude session.
- First model: a coffee mug (MugBody + MugHandle, 80 mm body, 95.5 mm tall, 115 mm with handle, blue ceramic).
  Saved as `models/coffee-mug/coffee_mug.blend` + `models/coffee-mug/coffee_mug.stl`, a copy in `~/downloads/coffee_mug.stl`, and committed
  as `examples/coffee_mug.stl` (binary STL in **mm**: exported with global_scale=1000, body+handle joined, 2816 tris).
  Termux can't write to the phone's Downloads (no All-files access), so the user gets files from GitHub.
- STL export recipe: join evaluated meshes (the handle is a curve) into a temp object, then
  `bpy.ops.wm.stl_export(export_selected_objects=True, global_scale=1000)` so the units are mm for Inventor.
- 2026-11-15: `examples/coffee_mug_colours.gif`: 5 s, 12 fps, 480×480, looping isometric view of the mug
  cycling red → yellow → green → blue → purple → red. Recipe: ortho camera at rotation (54.7356°, 0, 45°),
  ortho_scale 0.16, shift (-0.035, 0.056); Workbench render (MATERIAL colours, so `mat.diffuse_color` is keyed
  along with Base Color), 60 PNGs to `models/coffee-mug/mug_gif/` (19 s total), then Termux ffmpeg palettegen/paletteuse → GIF.
  The scene setup is saved in `models/coffee-mug/coffee_mug.blend`.
- 2026-11-15: `models/man-rigged/man-rigged.blend` won't open: it was saved in Blender 5.2 (header `BLENDER17-01v0502`), and 4.3 can't
  read the new format. No official ARM64 Linux builds of 5.x (blender.org is x64 only, Flathub x86_64 only). Debian forky has
  blender 5.2.2 for arm64 but needs libc6 >= 2.43, so the whole container would have to move to forky. Offered: a second Debian
  container upgraded to forky (keeps 4.3 working). **Waiting on the user's decision.**
- 2026-11-15: Imported `models/astronaut/astronaut-in-spacesuit-rigged.glb` (glTF works fine in 4.3): char1 mesh 175k verts, 24-bone
  Armature, actions run_Armature (0-15) and walk_Armature (0-24), stray Icosphere and default Cube deleted. Saved as `models/astronaut/astronaut.blend` (40 MB).
  Open .blend files from MCP via `bpy.app.timers.register(...)` around `wm.open_mainfile` (deferred, not inside the socket call).
- 2026-11-15: `examples/astronaut_walk.gif`: 1 s loop (one walk cycle), 12 fps, 480×480, 405 KB. Recipe: camera `GifCam`
  (ortho, rotation 54.7356°, 0, 45°, aimed at (0,0,0.95), ortho_scale 2.5, shift_y -0.06), Workbench with `color_type='TEXTURE'`,
  walk_Armature frames 0-22 step 2 → `models/astronaut/astronaut_gif/`, then the same ffmpeg palette steps. GifCam + walk as active
  action are in the open scene; not saved to `astronaut.blend`.
- 2026-11-15: `examples/astronaut_moon.gif` (4 s loop, 12 fps, 400×400, 2.6 MB; 480 px was 3.6-7.5 MB because the scrolling
  ground changes every frame). Scene saved as `models/astronaut/astronaut_moon.blend` (copy; the open file is still astronaut.blend).
  Action `moon_Armature` (0-96, fake user): frames 0-48 = walk at half speed + two 0.16 m hops (Armature object Z), 48-96 = one
  0.85 m leap, legs ping-ponging walk frames 0→6→0; travel 1.2 + 1.6 = 2.8 m along −Y (forward is −Y). `MoonGround`: 14×18 m
  numpy grid with craters tiled every 2.8 m along Y so the loop is seamless; GifCam keyed to follow Y (ortho_scale 3.4,
  shift_y 0.10). Workbench shadows don't render here (llvmpipe?), so `BlobShadow` (3 stacked discs) is keyed under him and
  shrinks with height. View transform set to Standard (AgX was too dark). Rendered 48 frames in ~80 s to `models/astronaut/moon_gif/`.
- Lesson: while I render, the user's view in Termux:X11 is live, and a touch rotated/moved selected objects mid-render. Set
  `hide_select=True` on the scene objects during long renders (restore after), and check object transforms before rendering.
- 2026-11-15: The "glitched" astronaut in the X11 viewport was the rig, not a graphics bug: the glTF import gave bones
  display lengths up to 41 m (glTF stores no bone length), drawn OCTAHEDRAL + show_in_front, covering the 1.8 m body.
  Fix: hide the Armature in the viewport (`arm.hide_set(True)`; the mesh still deforms) and viewport Solid + TEXTURE colours.
  Don't shorten the bones (changing tails changes rest orientation and breaks the actions). Saved into both astronaut .blend files.
- 2026-11-15: `models/` sorted into per-model folders (user chose phone-only; `examples/` on GitHub unchanged,
  .blend files not committed). `models/start.log` is the Blender log from my launch command.
- 2026-11-15: Knight turntable **done**: `examples/knight_turntable.gif` (600×600, 24 fps, 120 frames = one 360° turn, seamless,
  11 MB; 480 px was 7.5 MB; Bayer dither saved only ~15%). Two knights side by side (the user's choice): the `chess_set` white knight
  (1.55 m) and an armoured knight built from primitives (steel = flat colour + metal_plate rough/normal maps; the diffuse map made it
  brown), Poly Haven kite_shield and antique_estoc (imports hilt-down, script flips it). Add-on's Poly Haven library is off, so
  `models/knight/fetch_assets.py` uses the Poly Haven public API (79 MB in `models/knight/assets/`). `models/knight/setup_scene.py`
  builds everything (copies committed as `examples/knight_fetch_assets.py` / `knight_setup_scene.py`); scene saved as
  `models/knight/knight_turntable.blend` (open in the live Blender). Render: EEVEE Next 16 samples, 720 px (Cycles here has no denoiser),
  run **headless** in a second Blender (`blender -b ... -a`, same proot binds + DISPLAY=:0) so the MCP socket stays free: ~16 s/frame,
  ~32 min. GIF: lanczos scale 600, palettegen stats_mode=diff, paletteuse sierra2_4a + diff_mode=rectangle. Frames in `models/knight/frames/`.
- 2026-11-15: Knight v2 **done** (GIF pushed; v1 renamed `examples/knight_turntable_v1.gif`): user asked to replace both knights with their STL `models/knight/Knight.stl` (15 MB,
  one solid mesh, 300k tris, 1.015 tall, faces −Y, raised flaming skull hand on +X; not committed, it's the user's file) and colour it.
  `setup_scene.py` `build_stl_knight` + `stl_regions`: per-face regions by position (armour / cape y>0.02 + side flares / base z<0.085
  / bone skulls (held skull = least-squares sphere C(0.1818,-0.1183,0.8603) R 0.06) / flames above it), materials dark steel
  (metal_plate maps), red velvet, stone base, bone (all with an AO node), emissive flames + orange point light + compositor fog glow
  (threshold 4). Scaled to 1.9 m, pedestal shrunk (0.86/0.98), lens 80. fetch_assets no longer downloads the v1 glTF models.
  v1 frames kept in `frames_v1/`. 96/120 frames rendered before a session died, 97-120 re-rendered (`-s 97 -e 120`).
  `examples/knight_turntable.gif` 600 px, 11 MB; scripts copied to `examples/`. Known flaw: the lowered left forearm/gauntlet
  (|x|>0.18, z<0.62 rule) gets a red cape patch in side views; told the user, fix = exclude that arm box from `cape` and re-render (~35 min).
  Note: one headless run ran at 64 s/frame (55 s before sampling), a re-run alone was 17 s; don't render in the live Blender at the same time.
- 2026-11-15: RunPod remote rendering **works** (`render-remote.sh`). First real run: `coffee_mug.blend -f 1`, 1m29s total,
  ~$0.02, RTX 4090 SECURE at $0.89/h (COMMUNITY had no 4090s), pod deleted, `--list` empty after. Blender 4.3.2 on the pod sees the
  4090 as CUDA + OPTIX. Not yet tested: a Cycles or EEVEE render there (the mug scene is Workbench), and a long multi-frame job.
  Lessons: new scoped RunPod keys only work on **REST v2** (`https://api.runpod.io/v2`); v1 (`rest.runpod.io/v1`) returns 401 for
  them. Scopes are fixed when a key is created (ticking boxes later in "Edit" does nothing). The key needs REST API → Pods R/W.
  The user saves the key with nano in a second Termux session; I check it by fingerprint/mtime, never print it.
- 2026-11-15: Knight turntable on RunPod: `./render-remote.sh models/knight/knight_turntable.blend -a`, 120 frames EEVEE 720 px,
  **1m54s total, ~$0.03** (phone: ~32 min). Packed upload 32 MB. Frame 1 took 27 s (EEVEE shader compile), then ~0.2 s/frame.
  Headless EEVEE works on the pod (no EGL errors). Frames in `models/knight/remote_frames/`, match the phone's `frames/`
  (side-by-side check of frame 31). Log: `models/knight/remote.log`. COMMUNITY had no 4090 again → SECURE $0.89/h.
  Next (user's plan): build on this once happy, e.g. a pre-built image with Blender baked in, or Serverless.
- 2026-11-15: **Knight v3 in progress** (user: Cycles, best resolution/aspect, fix colours, show as V3 in examples).
  Colours: `setup_scene.py` `stl_regions` rewritten: crease patches (faces split at >12 deg, the cape is one 98k-face patch),
  base = big low patches, feet kept armour (BOOT_BOXES), base skulls by position (SKULL_BOXES, from a top-down view), held skull
  + flames as before. Helmet is all steel (no separate hood in the mesh). Armour = procedural `steel_material()` (the metal_plate
  maps showed a diamond tread pattern at 1440 px). Render: Cycles, 1440x1800 (4:5), 1024 max samples adaptive 0.008, lens 76,
  target z 1.08, motion blur; denoiser set on the pod by `models/knight/v3/pod_render.py` (phone Blender has no denoisers;
  `render-remote.sh` got `PRE_PY=`). Scene: `models/knight/knight_v3.blend` (built by `models/knight/v3/build.py`).
  Test frame: 15 s/frame render + 2.5 min one-time OptiX kernel compile per pod. Full render launched 11:45 →
  `models/knight/frames_v3/`, log `models/knight/v3/full.log`. Still to do: mp4 + gif + still into `examples/` as v3, README.
  Pipeline problems seen (user wants to optimise after seeing v3): some pods install for 10+ min or upload at ~5 KB/s
  (added 5 min scp timeout); ideas: pre-built image with Blender, CUDA instead of OptiX (no kernel compile).
- Not yet known: how usable the UI feels on llvmpipe (I can't see the screen; ask the user).
- Later: GPU rendering (zink + turnip) instead of llvmpipe.
