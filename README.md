# Blender Live

Blender running on the phone (Termux → Debian proot), shown live in the **Termux:X11** app,
and driven by Claude Code through the [blender-mcp](https://github.com/ahujasid/blender-mcp) add-on.
You say what to change ("make the handle 20% thicker"), Claude edits the model, and you watch it happen.

## Setup (once)
1. Install the **Termux:X11** app (APK: `termux-x11-universal-debug.apk` from the termux/termux-x11 GitHub nightly release).
2. In Termux: `bash ~/blender-live/setup.sh`

## Use
1. `bash ~/blender-live/start-blender.sh`, which opens Termux:X11 with Blender.
2. Put models in `~/blender-live/models/`, one folder per model (e.g. `models/astronaut/`). Share them into Termux, then ask Claude to move them.
3. Ask Claude Code for edits. Exports go back into that model's folder.

## Fast renders on a rented GPU (RunPod)
The phone renders on its CPU, so big renders are slow. `render-remote.sh` rents an RTX 4090 on RunPod by the second,
renders there, downloads the frames, and deletes the machine again.

One-time setup:
1. Make an account on runpod.io and add some credit (e.g. $10).
2. Settings → API Keys → **Create API Key**, and tick REST API → **Pods: Read + Write** before tapping Create
   (permissions can't be changed afterwards).
3. In Termux: `mkdir -p ~/.config/runpod && nano ~/.config/runpod/api_key` (paste the key, save), then
   `chmod 600 ~/.config/runpod/api_key`.

Use (or just ask Claude): `./render-remote.sh models/knight/knight_turntable.blend -a` renders all frames into
`models/knight/remote_frames/`. `PODS=4 ./render-remote.sh … -a` uses up to 4 GPUs at once (about 4× faster,
about the same total cost). The frames are cut into small jobs (`JOB=120` frames each), and each machine takes the next job
as soon as it's free. GPUs are often sold out, so the script keeps trying every GPU type for up to `WAIT_MINUTES` (default 60):
one machine can finish everything on its own, and more just speed it up as they become free. If anything fails, run the same
command again: frames already downloaded are skipped. The machines boot from a ready-made image with Blender 4.3.2 inside
(`ghcr.io/mervinadur/blender-render:4.3.2`, built from `pod-image/` by GitHub Actions), so nothing is installed per job. Anything after the file goes to Blender (e.g. `-E CYCLES -s 1 -e 24 -a`, or `-f 1` for one still).
It prints the time and rough cost at the end (the knight turntable, 120 frames, took under 2 minutes and about $0.03, against about 32 minutes on the phone). `./render-remote.sh --list` shows any machines still running,
`--kill-all` deletes them. As a safety net, each machine deletes itself after 90 minutes.
Your .blend (with its textures packed in) is uploaded to RunPod for the render.

## Making a render look real (self-hosted AI, no Replicate)
`./ai-remote.sh models/<name>` rents one RTX 4090 on RunPod and runs the open-source **Wan 2.1 VACE** video model
(Apache 2.0) on your Blender walk-through. Each frame follows the scene's depth (Depth Anything V2), so the layout stays
the same as in Blender, and each ~5 s chunk carries on from the end of the one before, so there are no cuts.
Inputs: `models/<name>/ai_in/f_0001.jpg…` (832x480, 16 fps), plus optional `anchor.jpg` (a photoreal still of frame 1),
`prompt.txt` and `negative.txt`. Output: `models/<name>/ai_out.mp4` (1280x720). `CHUNKS=2` makes a ~10 s test.
First full run (nature trail, 60 s): 66 min, about $0.98. Known issue: colours get stronger chunk after chunk (see CLAUDE.md).

## Limits
- Renders on the phone use the CPU (software OpenGL), so heavy scenes are slow; see RunPod above.
- Blender makes meshes. For exact parametric parts for Inventor (STEP), use CAD Agent.
- The add-on's online model services (Hyper3D, Tripo, Sketchfab, …) stay off.

## Troubleshooting
- **X11 app says "Not connected"**: the X server isn't running. Run `bash ~/blender-live/start-blender.sh`.
- **Blender quits with "Illegal instruction"**: the start script already works around this (it hides the
  phone's CPU type from the software renderer). If it comes back, run
  `proot-distro login debian -- rm -rf /root/.cache/mesa_shader_cache /root/.cache/mesa_shader_cache_db`
  and start again.

## Examples
- **`examples/nature_trail.mp4`**: a 1-minute walk along a dirt trail through a meadow with trees, ending at rock cliffs
  (1280×720, 24 fps, 20 MB). The trees sway in the wind and the sun sinks towards golden hour. All models, textures and lighting
  are CC0 from [Poly Haven](https://polyhaven.com). Rendered on 3 rented GPUs at once in 7.5 minutes for about $0.31.
  `nature_trail_still.jpg` is one frame. Rebuild: `nature_trail_fetch_assets.py` downloads the assets, `nature_trail_build.py` builds the scene.
- **`examples/knight_turntable_v3.mp4`** (best quality): your knight rendered in Cycles (realistic light) at 1440×1800 (4:5 portrait),
  one smooth 5-second turn at 24 fps. Fixed colours (clean red cape, steel boots and helmet, white skulls on the base, no red patch
  on the arm) and smooth polished steel. `knight_turntable_v3.gif` is a smaller preview, `knight_v3_still.png` a full-size still.
  Rendered on a rented RTX 3090 in 55 minutes for about $0.45. Rebuild: `knight_setup_scene.py` (now the v3 scene),
  render with `render-remote.sh` and `PRE_PY=knight_v3_pod_render.py` (turns on the denoiser).
- `examples/knight_turntable.gif`: a smooth 360° turntable of your knight model (from your STL), coloured in Blender: steel armour,
  red velvet cape, stone base, bone skulls and glowing flames, on a marble pedestal in a castle cellar (5-second loop, 600×600, 24 fps).
  Textures and lighting are CC0 from [Poly Haven](https://polyhaven.com). To rebuild it: `knight_fetch_assets.py` downloads the
  textures, `knight_setup_scene.py` builds the scene in Blender (needs the STL at `/root/models/knight/Knight.stl`, or set `KNIGHT_STL`).
- `examples/knight_turntable_v1.gif`: the first version, with Poly Haven's marble chess knight next to a knight built in code.
- `examples/astronaut_walk.gif`: the rigged astronaut walking, a 1-second looping isometric animation (480×480, 12 fps).
- `examples/astronaut_moon.gif`: the astronaut on the Moon, with slow low-gravity hops and then a big leap over a cratered surface (4-second loop, 400×400).
- `examples/coffee_mug_colours.gif`: 5-second looping isometric animation of the mug changing through 5 colours.
- `examples/coffee_mug.stl`: a coffee mug made by Claude in Blender. Units are millimetres
  (80 mm wide, 95.5 mm tall, 115 mm including the handle). Download it from GitHub: open the file and tap the download button.
