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
- `models/`: the user's working files (gitignored).
- `examples/`: finished models committed so the user can download them from GitHub (e.g. `coffee_mug.stl`).

## Rules
- The add-on's generation integrations (Hyper3D/Rodin, Tripo, Meshy, World Labs, Sketchfab) stay **off**.
  This follows the spirit of the user's generation ban; ask before enabling any.
- Keep telemetry **off**: the MCP server sends usage events (and can upload screenshots/code) to its author's
  Supabase unless `DISABLE_TELEMETRY` etc. are set; the add-on's `telemetry_consent` pref defaults off. Leave it off.
- `claude mcp ...` must run from `~` (it fails elsewhere with "preload not found ./.local/share/claude/setdns.js").
- I can't see the X11 window. Verify through MCP scene info / dimensions, or render previews to `models/`.

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
  Saved as `models/coffee_mug.blend` + `models/coffee_mug.stl`, a copy in `~/downloads/coffee_mug.stl`, and committed
  as `examples/coffee_mug.stl` (binary STL in **mm**: exported with global_scale=1000, body+handle joined, 2816 tris).
  Termux can't write to the phone's Downloads (no All-files access), so the user gets files from GitHub.
- STL export recipe: join evaluated meshes (the handle is a curve) into a temp object, then
  `bpy.ops.wm.stl_export(export_selected_objects=True, global_scale=1000)` so the units are mm for Inventor.
- 2026-11-15: `examples/coffee_mug_colours.gif`: 5 s, 12 fps, 480×480, looping isometric view of the mug
  cycling red → yellow → green → blue → purple → red. Recipe: ortho camera at rotation (54.7356°, 0, 45°),
  ortho_scale 0.16, shift (-0.035, 0.056); Workbench render (MATERIAL colours, so `mat.diffuse_color` is keyed
  along with Base Color), 60 PNGs to `models/mug_gif/` (19 s total), then Termux ffmpeg palettegen/paletteuse → GIF.
  The scene setup is saved in `models/coffee_mug.blend`.
- 2026-11-15: `models/man-rigged.blend` won't open: it was saved in Blender 5.2 (header `BLENDER17-01v0502`), and 4.3 can't
  read the new format. No official ARM64 Linux builds of 5.x (blender.org is x64 only, Flathub x86_64 only). Debian forky has
  blender 5.2.2 for arm64 but needs libc6 >= 2.43, so the whole container would have to move to forky. Offered: a second Debian
  container upgraded to forky (keeps 4.3 working). **Waiting on the user's decision.**
- 2026-11-15: Imported `models/astronaut-in-spacesuit-rigged.glb` (glTF works fine in 4.3): char1 mesh 175k verts, 24-bone
  Armature, actions run_Armature (0-15) and walk_Armature (0-24), stray Icosphere and default Cube deleted. Saved as `models/astronaut.blend` (40 MB).
  Open .blend files from MCP via `bpy.app.timers.register(...)` around `wm.open_mainfile` (deferred, not inside the socket call).
- 2026-11-15: `examples/astronaut_walk.gif`: 1 s loop (one walk cycle), 12 fps, 480×480, 405 KB. Recipe: camera `GifCam`
  (ortho, rotation 54.7356°, 0, 45°, aimed at (0,0,0.95), ortho_scale 2.5, shift_y -0.06), Workbench with `color_type='TEXTURE'`,
  walk_Armature frames 0-22 step 2 → `models/astronaut_gif/`, then the same ffmpeg palette steps. GifCam + walk as active
  action are in the open scene; not saved to `astronaut.blend`.
- 2026-11-15: `examples/astronaut_moon.gif` (4 s loop, 12 fps, 400×400, 2.6 MB; 480 px was 3.6-7.5 MB because the scrolling
  ground changes every frame). Scene saved as `models/astronaut_moon.blend` (copy; the open file is still astronaut.blend).
  Action `moon_Armature` (0-96, fake user): frames 0-48 = walk at half speed + two 0.16 m hops (Armature object Z), 48-96 = one
  0.85 m leap, legs ping-ponging walk frames 0→6→0; travel 1.2 + 1.6 = 2.8 m along −Y (forward is −Y). `MoonGround`: 14×18 m
  numpy grid with craters tiled every 2.8 m along Y so the loop is seamless; GifCam keyed to follow Y (ortho_scale 3.4,
  shift_y 0.10). Workbench shadows don't render here (llvmpipe?), so `BlobShadow` (3 stacked discs) is keyed under him and
  shrinks with height. View transform set to Standard (AgX was too dark). Rendered 48 frames in ~80 s to `models/moon_gif/`.
- Lesson: while I render, the user's view in Termux:X11 is live, and a touch rotated/moved selected objects mid-render. Set
  `hide_select=True` on the scene objects during long renders (restore after), and check object transforms before rendering.
- Not yet known: how usable the UI feels on llvmpipe (I can't see the screen; ask the user).
- Later: GPU rendering (zink + turnip) instead of llvmpipe.
