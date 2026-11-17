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
- `render-remote.sh`: renders a .blend on RunPod GPUs (`PODS=N` in parallel, ready-made image, see Status; REST API v2, one GPU type per create call so the script loops 4090/3090/A5000 × COMMUNITY/SECURE, `ubuntu:24.04` image, start command installs sshd +
  official Blender x64 tarball; Cycles set to OptiX/CUDA via `gpu.py`), pulls frames to `<model>/remote_frames/`, deletes the pod
  on exit + a self-delete timer on the pod (MAX_MINUTES=90). Key in `~/.config/runpod/api_key` (user puts it there, never me);
  SSH key `~/.ssh/runpod_ed25519`. Packs assets locally first (4.3), so 5.x files need `PACK=0 BLENDER_VERSION=5.2.2`.
- `ai-remote.sh` + `ai/vace_trail.py`: self-hosted AI "make it real" pass on one RunPod GPU (image `runpod/pytorch:2.4.0-…`,
  torch upgraded to 2.5.1 on the pod because diffusers 0.35 needs `enable_gqa`). Wan 2.1 VACE (1.3B default, `MODEL=14B`),
  depth control from Depth Anything V2 **Large (CC-BY-NC, non-commercial; switch to Small if the user goes commercial)**.
  Inputs `<model>/ai_in/` (f_*.jpg 832x480 16 fps, anchor.jpg, prompt.txt, negative.txt); outputs `ai_out/`, `ai_out_depth/`
  (re-uploaded on the next run = resume), `ai_out.mp4`. Job runs under nohup on the pod; log has timestamps.
  **Colour correction between chunks is required (user, 2026-11-15).** Built into `ai/vace_shots.py` and `ai/v2v_shots.py`
  (2026-11-17); `vace_trail.py` still lacks it. Without it, saturation/contrast grow every chunk (nature trail went neon after ~25 s).
  Method: before each chunk k>0, colour-match the 8 overlap frames to the reference look (anchor.jpg, or chunk 0's frames) with
  per-channel mean/std transfer in LAB (Reinhard), then feed them to VACE; apply the same match to every saved output frame.
  Add a strength setting (0.5-1.0) so deliberate lighting changes (e.g. a sunset scene) aren't flattened. Test on 2-3 chunks first.
- `ai-shots.sh`: shot-based AI video on 1..N pods (one group of shots per pod, in parallel), via `ai-remote.sh` with
  `SCRIPT`/`ARGS`/`ENCODE=0`/`TAG`; fills missing frames, encodes to `FINAL` (default 2780x1264 = OnePlus 13R full screen).
  Env: SCRIPT (vace_shots.py | v2v_shots.py), STEPS, BUDGET (min of generation), SIZE (960x432), EXTRA_ARGS (`--offload`
  required on a 4090, `--strength`), MAX_MINUTES (55).
- `ai/v2v_shots.py`: **current route.** Wan 2.1 T2V 1.3B video-to-video from the Blender colour render (`ai_in/render/`),
  `--strength` (0.5 = close to Blender), colour locked to the render per chunk (`--cc-render`, car mask/background apart),
  matched + cross-faded on chunk overlaps (`--cc`), auto-fit steps to `--budget-min`.
- `ai/vace_shots.py`: depth-only route (Blender Z feed + car mask, one generated car reference via VACE `reference_images`,
  masked colour correction, auto-fit). v1 of car-street: user found it too dark and "too AI".
- `pod-image/`: Dockerfile + start.sh for the RunPod image (Blender 4.3.2, libs, sshd, ffmpeg); built by `.github/workflows/pod-image.yml`.
- `models/`: the user's working files (gitignored), **one folder per model** (`models/<model-name>/`: .blend, source files,
  render frames, tests). Currently `coffee-mug/`, `astronaut/`, `man-rigged/`, `knight/`, `nature-trail/`, `car-street/`, `robot-scene/` (car-street: `ai_in/` feed + prompts, `remote_frames/` raw EEVEE render, `ai_out/` v2 frames, `ai_out_2780x1264.mp4` v2, `ai_out_v1_2780x1264.mp4` v1, `ai_logs/`). New model → new folder. Inside Debian: `/root/models/<model-name>/`.
- `examples/`: finished models committed so the user can download them from GitHub (e.g. `coffee_mug.stl`).

## AI video runs: recipe and lessons (read before the next video)
Learned on nature-trail and car-street (2026-11-15..17). `models/car-street/` is the reference implementation.
1. **Steps, reported to the user after each:** (a) assets + scene (`fetch_assets.py`, `build.py`, headless via
   `run_headless.sh`); (b) motion (`animate.py`, keyed straight at 16 fps = Wan rate, shots ending on chunk starts);
   (c) **the user checks motion by pressing Space in the live X11 Blender** (timeline set, `sync_mode=FRAME_DROP`,
   overlays off); roughest preview first, never a long render to "show" motion; (d) colour render on a pod; (e) Wan on a pod;
   (f) encode on the phone.
2. **Route = video-to-video from the Blender colour render** (`v2v_shots.py`). The user: "the animation model should not be
   disregarded". Depth-only VACE invents too much (v1: dark, black-void background, "too AI"). Strength 0.5 + render lock 0.6
   stayed CGI-looking; next try 0.65-0.7 and `--cc-render 0.3`.
3. **Render settings for the AI feed:** EEVEE **16 samples** (user's choice; 64 = ~1 frame/s on a 4090), 960x432 (= Wan
   size; 2.2:1 = OnePlus 13R 2780x1264 shape; larger is wasted, smaller loses detail). Final encode Lanczos to 2780x1264, 16 fps.
4. **Render on the pod, not the phone** (user, 2026-11-17): the phone feed took 59 min; next time render on the same pod as Wan
   (not built yet). EEVEE on the pod is **much brighter** than the phone's Cycles preview: check one frame per shot before Wan;
   grade with ffmpeg if needed (car-street v2 dusk grade is in its Status entry).
5. **Shots = chunk boundaries;** a shot's first chunk must never reach into the previous shot (fixed in v2v_shots.py).
6. **Colour correction stays on** even with depth/render input: drift comes from chunks continuing from generated overlap frames.
7. **GPU:** 4090 needs `--offload` (all-on-GPU OOMs at 81 frames, $0.09 lost). Speeds with offload, 960x432, 81 frames:
   v2v 28 steps x 0.5 = ~103 s/chunk; VACE 12 steps = ~131 s/chunk. 60 s = 15 chunks. Setup ~5-10 min (pip + model download).
   COMMUNITY 4090 $0.34/h vs SECURE $0.89/h. RunPod "high memory 86%" = page cache (harmless); disk 80 GB = $0.011/h (normal).
8. **Budget:** the user caps AI generation at ~30 min on **one pod**; the scripts auto-lower steps to fit (`--budget-min`).
9. **Costs so far (car-street):** v1 VACE $0.32 (incl. OOM try); v2 colour render $0.30 + Wan $0.53.
10. **Token economy (user asked, 2026-11-17):** don't watch runs chunk by chunk (each wake-up re-reads the whole session).
    Plan: one `make-video.sh` end-to-end script + `termux-notification` at the end; at most one completion notification;
    fresh Claude session per video (this file has the state); Sonnet for routine runs. **Not built yet.**
11. **Live Blender:** long blocking MCP calls time out ("No data received") -> render with a `bpy.app.timers` loop (one frame per
    tick). Headless Workbench/EEVEE hangs on EGL unless X11 runs; headless scene building (no GL) is fine.
12. Known bug: the ssh that starts the pod job still hangs, so local progress shows nothing until the job ends (the job runs
    fine; read `/workspace/job/log.txt` on the pod).

## Rules
- The add-on's generation integrations (Hyper3D/Rodin, Tripo, Meshy, World Labs, Sketchfab) stay **off**.
  This follows the spirit of the user's generation ban; ask before enabling any.
- Keep telemetry **off**: the MCP server sends usage events (and can upload screenshots/code) to its author's
  Supabase unless `DISABLE_TELEMETRY` etc. are set; the add-on's `telemetry_consent` pref defaults off. Leave it off.
- `claude mcp ...` must run from `~` (it fails elsewhere with "preload not found ./.local/share/claude/setdns.js").
- I can't see the X11 window. Verify through MCP scene info / dimensions, or render previews to `models/<model-name>/`.

## Status (2026-11-17)
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
- 2026-11-15: **Knight v3 done** (user asked: Cycles, best resolution/aspect, fixed colours, V3 in examples, production quality).
  `examples/knight_turntable_v3.mp4` (1440x1800, 24 fps, 120 frames, x264 crf 17, 5 MB), `knight_turntable_v3.gif` (480x600, 12 MB),
  `knight_v3_still.png` (frame 1). Frames in `models/knight/frames_v3/` (433 MB, phone only). Rendered on RTX 3090 SECURE
  (4090s sold out): 24 s/frame after a 3 min first frame (OptiX kernel compile), 54.5 min, ~$0.45.
  Colours: `setup_scene.py` `stl_regions` = crease patches (faces split at >12 deg; the cape is one 98k-face patch), base = big low
  patches, feet kept armour (BOOT_BOXES), base skulls by position (SKULL_BOXES, from a top-down view), held skull + flames as v2.
  Helmet all steel (the mesh has no separate hood). Armour = procedural `steel_material()` (metal_plate maps showed a diamond tread
  pattern at 1440 px). Render: Cycles 1024 max samples, adaptive 0.008, clamp indirect 10, motion blur, lens 76, target z 1.08;
  denoiser (OIDN, GPU) set on the pod by `examples/knight_v3_pod_render.py` via `PRE_PY` (phone Blender has no denoisers).
  Scene `models/knight/knight_v3.blend`, built by `models/knight/v3/build.py`; debug scripts/renders in `models/knight/v3/`.
- 2026-11-15: **render-remote.sh v2** (user: split jobs over pods + ready-made image; machine choice and tuning stay with Claude
  per session, no auto-picker; Blender stays 4.3.2 = phone version; man-rigged/5.x dropped for now).
  `PODS=N` splits `-a` (or `-s/-e -a`) into N contiguous chunks, one pod each, in parallel (per-chunk logs, progress every 30 s,
  total cost summed, failed chunks reported). Default IMAGE `ghcr.io/mervinadur/blender-render:4.3.2` (public; `pod-image/`
  Dockerfile + start.sh, built by `.github/workflows/pod-image.yml` on push). `IMAGE=ubuntu:24.04` = old install-on-boot path.
  Upload timeout 5 min. Dry-run tested only (fake key: 3 chunks 1-20/21-40/41-60, clean failure). **Not yet run for real** with
  the image or with PODS>1; first test planned: coffee mug, PODS=2. Old private package `blender-pod` is unused (user may delete).
  Repo made **PUBLIC** by the user 2026-11-15 (audit: no secrets in history; commit email visible, user OK with it).
  Ideas not done: CUDA instead of OptiX for short jobs (skips ~3 min compile), mp4 encode on the pod, auto-retry of slow pods.
- 2026-11-15: **render-remote.sh v3 = job queue** (user: GPUs are hard to get, render as pods become free). Frames cut into
  `JOB`-frame jobs (default 120) as files in `$WORK/todo/` (named FIRST_LAST); up to `PODS` workers, each loops
  `( run_chunk n )` in a subshell: try every GPU type × cloud (4090/3090/A5000 + `GPU_MORE` list: L40S, A6000, 4080 SUPER,
  A4500, L4), retry every 30 s for `WAIT_MINUTES` (default 60). A pod uploads once, then claims jobs by `mv todo→claimed`
  (atomic) until the queue is empty; the EXIT trap puts the current job back and deletes the pod. Frames already in OUT_DIR are
  skipped when jobs are built (re-run = resume). Exit 3 = key 401/403 → worker stops. Gotcha: with `pipefail`, a `grep | wc`
  that matches nothing killed the script silently; use `grep -c … || true`. Dry-run tested with a fake key, then a real run (nature trail, below).
- 2026-11-15: **Nature trail** (`models/nature-trail/`, user's request: Poly Haven scene, nature theme, 60 s, multi-pod render,
  result in examples). Poly Haven has no downloadable scenes, so `build.py` assembles one from CC0 assets (`fetch_assets.py`,
  190 MB in `assets/`): island_tree_01/02 (pine/fir trees are 0.5-1 GB each, skipped), saplings, boulders, coast rocks,
  mountainside cliffs, grass/fern/flower clumps (~3k collection-instance empties), forest_ground_04 trail texture,
  forest_slope HDRI. Camera walks a winding trail (frames 1-1200), cranes up to the cliffs (1200-1440); trees sway (noise
  F-curve modifiers), sun keyed from afternoon to golden hour (haze removed, see below). User asked to keep it phone-friendly:
  1280x720, EEVEE 16 samples, no raytracing, heavy meshes decimated (decimate needs the object linked to the scene; the
  AssetLib collection is excluded so it isn't evaluated). .blend 112 MB. EEVEE on the phone: 6.5 min/frame and came out black
  (llvmpipe), so don't preview EEVEE here; the user checked the layout in the live X11 Blender instead.
  First pod render came out **black** on the GPU too: cause was a Principled Volume on the World (haze). In an open world it
  absorbs all sky and sun light. Removed. Quick check method: phone Cycles at 12% res, 4 samples, `use_denoising=False` (~30 s).
  **Done**: `examples/nature_trail.mp4` (1280x720, 24 fps, 1440 frames, x264 crf 26, 20 MB), `nature_trail_still.jpg` (frame 600),
  scripts `examples/nature_trail_build.py` / `nature_trail_fetch_assets.py`. Render: `PODS=4 JOB=120 WAIT_MINUTES=40`, 3 pods
  (4090s; several 4090 pods had no public IP and were swapped automatically), **7m32s, ~$0.31**, 0.2-0.4 s/frame EEVEE. First real
  run of the queue + ready-made image: works. Frames in `models/nature-trail/remote_frames/` (phone only).
  Known weakness: the crane-up ending (frames ~1250-1440) ends close on the cliff face rather than an open reveal; fix = aim the
  target higher / stop the camera further back in `build.py` camera section, re-render 1200-1440 only.
  The fixed `nature_trail.blend` is open in the live X11 Blender.
- 2026-11-15: **Realistic nature trail** `examples/nature_trail_realistic.mp4` (60 s, 1280x720, 63 MB), made in the
  image-and-gif-generator repo (user lifted the Replicate ban for this one job): 7 keyframes every 10 s of nature_trail.mp4 →
  FLUX Kontext Pro photoreal (`outputs/nature-trail-real/nt-key-*.jpg`) → 6 × 11 s Seedance 1 Lite i2v (first+last frame mode
  was rejected upstream with a task_type error) → 1 s crossfades in ffmpeg. Known flaws: some segments show a hand with a
  phone gimbal, legs or feet despite "no people" in the prompt; the path layout drifts from the Blender original.
  Cost ≈ $2.7 (Seedance returned 1920x1088 although 720p was asked; if billed as 1080p it is ≈ $5).
  **User verdict 2026-11-15: failure.** 11 clips from 6 keyframes don't feel like one continuous walk, and $2.4+ for 1 min vs
  cents for everything else is too much. Replicate ban is back on. Next: a non-Replicate route (proposed: photoreal Cycles
  re-render of the same scene on RunPod). User picked **self-hosted AI on RunPod** (Wan 2.1 VACE, see Files).
- 2026-11-15: **AI nature trail, first full run** (`models/nature-trail/ai_out.mp4`, 60 s, 960 frames 16 fps, 1280x720 upscaled from
  832x480, 84 MB; `ai_compare.mp4` = Blender on top, AI below; phone only, user views via Material Files, not committed).
  Recipe: frames from `examples/nature_trail.mp4` via `ffmpeg -vf "fps=16,scale=-2:480:flags=lanczos,crop=832:480"`, anchor = earlier
  FLUX still `nt-key-0.jpg` cropped the same way; 14 chunks of 81 frames, 8-frame overlap, 30 steps, cfg 5, last chunk shrunk to 13.
  **Timing (RTX 4090 SECURE $0.89/h): 66m23s, $0.98.** Pod→SSH 38 s; upload + pip ≈ 3 min; model load 2 min; **263 s per chunk**
  (very steady), 58 min generating (87%); download 55 s, encode 35 s. Setup total ≈ 6 min ≈ $0.09. VRAM only 9.6/24 GB (cpu offload on).
  Test runs: 1st failed on torch 2.4 ($0.09); 2nd = 2 chunks ($0.19, `ai_test1/`: sun + lens flare + autumn drift → fixed by prompt.txt
  / negative.txt). Depth maps took ~1 min on the pod (done in the failed run, reused since).
  **Result:** first ~25 s look like real footage, layout matches Blender, chunk joints seamless. Then **cumulative colour drift**:
  more saturation/contrast every chunk (neon grass, crushed shadows), and the cliff crane-up ending (~40-60 s) is unrealistic
  blue/cyan. Fix ideas, not done: colour-match the 8 overlap frames (and outputs) to the anchor before each chunk; or keyframe pass +
  parallel fill-in (user asked about splitting over pods: plan = one pod makes 81 keyframes every 12th frame in one generation,
  then N pods fill chunks between fixed keyframes; ~25-30 min wall, ~30-40% more cost; test on 10 s first). Also: drop cpu offload on
  24 GB cards; try 14B for detail.
  Bug fixed after the run: the ssh that starts the pod job hung (stdin not detached) so progress only showed at the end; now `</dev/null`.
  **User verdict:** everything looks right except the colour drift; colour correction is now a required step (see Files). Nothing pending.
- 2026-11-16: **Car street, step 1 of a stepwise run done (assets + scene set; no animation yet)**. User: car theme, 60 s video,
  "process optimisation" run = work in steps and report after each. `models/car-street/`: `fetch_assets.py` (Poly Haven CC0: 15
  street models from the hidden_alley set, rooftop_night 2k HDRI, asphalt_02 / concrete_pavement / brick_wall_02 / concrete_wall_008),
  `build.py` (headless, 9 s) -> `car_street.blend` (64 MB), `run_headless.sh <script>` (headless Blender with the right binds),
  `preview.py` (Cycles stills of every camera at 30% to `previews/`; clears marker cameras first, or the frame-1 marker overrides
  `scene.camera` and every still is the same shot). Layout: street along +Y (y -60..180), road |x|<4, kerb 0.15, sidewalks to |x| 7,
  random brick/concrete blocks with lit window quads, fenced lot left y 38-58, 25 lamp posts with spot lights, 24 shutter doors +
  wall lamps, poles/hydrants/benches/bins, barriers + crosswalk at the far end, a covered car parked left at y 101. Damp road
  (asphalt roughness x0.35). **Hero car = the user's `car.stl`** (added mid-session; 1960s GT coupe, one solid 300k-tri mesh,
  1.163 long, front at -X, wheels fused): scaled x3.87 to 4.5 m, turned to face +Y, parked on the hero mark (x 1.75, y 92) under a
  lamp, one red paint material for now. Headlight spots + red tail area light are parented to the `Car` empty. My code-built coupe
  (loft body + boolean arches, separate spinning wheels) is kept in the excluded `HeroCar_Procedural` collection as a backup.
  Shots = 5 cameras bound to markers: S1 establish f1, S2 tracking f193, S3 orbit f577, S4 details f961, S5 drive-off f1201
  (first poses only). Render: EEVEE Next 32 samples, raytracing, motion blur, 1920x1080, 24 fps, 1-1440.
  Step timings (wall clock): docs + plan ~1 min; asset search + download 40 s (82 MB in 13 s); size probe 7 s; writing build.py
  ~2.5 min; build 8-9 s; previews 53 s with the code car, 3m20s with the STL car (heavy mesh); STL check ~1.5 min; total ~13 min.
  Step 2 changed by the user (2026-11-17): **AI route, not a polished Blender render** (nature-trail lesson: Wan repaints every
  pixel, so detailed animation/materials are overkill). Only depth + object coherence are needed:
  - `animate.py` -> `car_street_anim.blend`: car drive + 6 camera moves keyed at **16 fps, 1-960** (S1 1-128, S2 129-384,
    S3 385-640, S4 641-720, S4b 721-800, S5 801-960; shots end on chunk starts). Car: y -55 -> stop at 92 (t 24 s) -> 152.
    User checked it by pressing Space in X11: fixed S1 (car too small -> camera y 10-12, 50 mm) and a doubled lamp at the hero mark.
  - `feed.py` -> `ai_in/depth/d_####.png` (Blender Z as disparity, fixed near/far per shot = no flicker; no Depth Anything)
    + `ai_in/mask/m_####.png` (car silhouette), 1056x480. **Workbench needs the live X11 Blender**: headless it hangs on EGL
    (twice). Run it inside the live Blender with a `bpy.app.timers` loop (one frame per tick): a long blocking MCP call times
    out ("No data received"). ~2.1 s/frame, ~33 min for 960. `ENGINE=CYCLES` = CPU fallback without a display (untested).
  - `ai/vace_shots.py` (new): per-shot chunks, one generated car reference (frame 509 side view, fixed seed) passed to every
    chunk via VACE `reference_images`; **colour correction built in** (per-chunk Reinhard in LAB, car mask and background
    separately, later chunks locked to the shot's first chunk, car pulled to the reference; unit-tested locally); budget
    `--budget-min 30` with auto-fit (lowers steps, min 12, after measuring chunk speed); model on GPU (no cpu offload).
    `ai-remote.sh` got `SCRIPT`/`ARGS`/`ENCODE`/`TAG` and per-run temp dirs; `ai-shots.sh` (new) runs shot groups on 1..N pods,
    fills gaps and encodes to **2780x1264 (OnePlus 13R full screen)**. User chose **one pod**: 960x432 gen (2.2:1), 16 steps.
  - `ai_in/` also holds shots.json (per-shot prompts), prompt.txt, negative.txt, ref_frame.txt.
  **Next run (user agreed 2026-11-17): render the feed ON the Wan pod** (install Blender 4.3.2 there, upload the .blend,
  render depth + mask headless on the GPU in ~1-3 min, then Wan) instead of ~33 min on the phone. Phone = scene build +
  the user's X11 motion check only. Untested: output paths (feed.py writes to /root/models/...; make OUT an argument).
  **Run done 2026-11-17:** `models/car-street/ai_out_2780x1264.mp4` (60 s, 960 frames, 16 fps, 2780x1264, 76 MB, phone only;
  frames `ai_out/o_*.png`, car reference `ai_out/ref_car.png` / `ref_full.png`, logs `ai_logs/`).
  Timings: feed on the phone 59 min (2.1-7 s/frame, the wide S5 shots slowest). Pod try 1: **OOM** with the model all on the
  4090 (24 GB) at the first 81-frame chunk, after the reference was made: 5m51s, $0.09. Try 2 with `--offload`: 4090 COMMUNITY
  $0.34/h, 40m29s, $0.23 (setup ~10 min, generation 28.5 min, auto-fit went to the 12-step minimum: 131 s per 81-frame chunk,
  download 43 s); encode ~2 min. Total pod cost $0.32.
  Bugs found: the ssh that starts the pod job still hangs (`</dev/null` didn't fix it), so local progress shows nothing until
  the job ends (the job itself runs fine; read the pod log directly). ai-shots.sh encoded with 0 frames (now exits).
  First look (contact sheet): the car is consistent across shots (deep red classic coupe, chrome, wire wheels), but the video is
  **much darker** than the reference, and in the tracking shot the background is a black void (car floating). Likely causes:
  dark disparity range for the street behind the car, the night prompt, 12 steps. **User verdict: too dark, "too much AI",
  and the Blender animation model must not be disregarded.** v1 kept as `ai_out_v1/`, `ai_out_v1_2780x1264.mp4`.
- 2026-11-17: **Car street v2 = video-to-video** (`ai/v2v_shots.py`, Wan 2.1 T2V 1.3B `WanVideoToVideoPipeline`): each chunk
  starts from the Blender **colour render** (SDEdit `--strength 0.5`), so the model/layout/colours stay; per chunk colour
  locked to the render (`--cc-render 0.6`, car/background separately) and matched + cross-faded to the previous chunk on the
  overlap. STL car now has material regions (`build.py` `car_regions`: glass, chrome bumpers + wire wheels, tyres, head/tail
  lights, underbody, by face position; measured with `probe_regions.py`). Scene brighter (HDRI 1.2, exposure +1, headlights 6).
  Colour render on RunPod via `render-remote.sh` (EEVEE 64 samples, raytracing, 960x432): 21m40s, $0.30, ~1 frame/s.
  EEVEE came out much brighter than the Cycles phone preview (overcast-day look), so the frames were graded on the phone to dusk
  (ffmpeg `eq=gamma=0.78:brightness=-0.04:saturation=0.92,colorbalance=bs=0.10:bm=0.05:rs=-0.04:rm=-0.02:rh=0.03`) into
  `ai_in/render/`. Wan pod: 4090 SECURE $0.89/h, 36 min, $0.53, generation 22.2 min at full 28 steps x 0.5 (~103 s per
  81-frame chunk with offload). RunPod showed "high memory 86%": that's page cache (124 GB pod, job used 32 GB), harmless.
  Output `ai_out_2780x1264.mp4` (87 MB). First look (contact sheet): very close to the Blender render, still CGI-looking
  (strength 0.5 + render lock 0.6 kept too much). Next if the user wants more realism: strength 0.65-0.7, `--cc-render 0.3`.
  Bug fixed after the run: a short shot's first chunk (80 frames -> 81) reached 1 frame into the previous shot and was matched
  to it (S4, S4b). ssh job-start still hangs (remote `< /dev/null` added, not enough); the job runs fine.
  **Agreed for the next run:** feed/colour render ON the Wan pod; EEVEE 16 samples (`animate.py` already set); one
  `make-video.sh` end-to-end script + `termux-notification` at the end, so Claude isn't woken per chunk (token cost);
  fresh session per video. **Waiting on the user's verdict of v2.**
- 2026-11-17: Housekeeping (user): deleted stale feed tests (`feed/`, `feed_rough/`), empty `ai_out_depth/`, `.blend1` backups,
  one-off probes (probe.py, probe_stl.py, look_stl.py) and v1's PNG frames (505 MB); kept v1 refs in `ai_in/ref_v1/` and both mp4s.
  Scripts copied to `examples/car_street_*.py` + `car_street_still.jpg` (mp4s not pushed, user's choice). README updated.
- 2026-11-17: **Robot scene v2: built, waiting on the user's X11 check** (`models/robot-scene/`, `build.py` headless ~25 s ->
  `robot_scene.blend` 92 MB; `preview.py` = headless Cycles stills for my own check, 8 shots in ~25 s -> `previews/`, `sheet.jpg`).
  User GLBs (Pixellabs, static, ~1 unit tall, 50k tris, 4K PBR, front -Y): robots 3347 (yellow, Robot_1), robot-3332 (Robot_2),
  3393 (Robot_3); abandoned houses 3642 (A), 3643 (B). **v1 (one continuous shot, robots in a row) was rejected**: X11 Blender was
  killed for memory (15x 4K textures + heavy props + 160 grass), user wants each robot as its own subject in a different part of
  town, and the brick looked weird (Solid view ignores box-projection mapping and stretched one image per wall).
  v2: textures shrunk (robots 2K, houses 1K) + packed; houses decimated 0.3 and reused as ~45 linked instances; props >12k tris
  decimated; UVs in metres on every box (`metric_uvs`), so Solid view = render. City: main street (|x|<5), cross street, alley
  y=-40 (Robot_1 at -18,-40), crossroads (Robot_2 at 1.5,1.5), overgrown dirt lot x 8..34, y 30..54 (Robot_3 at 18,42); props from
  ../car-street + ../nature-trail assets, sunset_jhbcentral HDRI. Plain skyline blocks removed (looked like flat beige walls);
  the HDRI's skyline shows instead. Gotcha: the electricity-pole kit has many loose parts; unused ones must be deleted (they sat
  at the crossroads and blocked S3). Shots (one camera each, bound to markers, 16 fps): S1 city 1-128, S2 Robot_1 alley 129-384,
  S3 Robot_2 half-orbit 385-640, S4 Robot_3 lot push-in 641-832, S5 crane up the street 833-960. Known: empty pavement at the far
  edges of S1/S5 (fix = a second row of houses, costs viewport speed). User rule: **start X11 Blender whenever working on scenes.**
  v3 (user: building variations, must not feel like 2 buildings): each house GLB is bisected into ground / middle / roof bands
  (A cut at 0.30/0.62 h, B at 0.33/0.66 h) and re-stacked: base, tall (A +2 middles = 14 m, B +1 = 10.7 m), short (no middle).
  Every instance: random variant (tall_bias), mirror, width x0.85-1.2, height x0.92-1.18, and a per-instance tint (Object Info
  Random -> Hue/Sat/Value on the house material; render only, Solid view shows plain textures). Second row of houses at |x| ~20
  (mostly tall) fills the empty pavement; ~85 house instances. S5 camera centred on the street. Previews: `previews/sheet.jpg`.
  v4 (user): shots renamed with numbers, now 6: 1_City 1-128, **2_Robot1_CloseUp 129-256 = locked camera on the eyes**
  (user: stationary close-up for curiosity; also fixes the S1->S2 jerk; Robot_1's face points more south than its body, so
  the camera sits at (-16.45,-42.1,1.5), lens 65), 3_Robot1_Alley 257-384 (old dolly, 8 s), 4_Robot2_Crossroads, 5_Robot3_Lot,
  6_Finale. X11 set-up for the user (the user can't scroll the timeline sideways): timeline `action.view_all` via temp_override so all 6 markers
  fit; 3D overlays on with only `show_text` (shows the shot/camera name), everything else off.
  v5: 2_Robot1_CloseUp no longer locked (user: too static): slow pan across the face (truck 0.4 m, aim 0.24 m) + ~2 cm
  handheld sway (layered sines). User approved the timeline set-up ("looks perfect").
  Not done: colour render + Wan (steps d-f).
- Not yet known: how usable the UI feels on llvmpipe (I can't see the screen; ask the user).
- Later: GPU rendering (zink + turnip) instead of llvmpipe.
