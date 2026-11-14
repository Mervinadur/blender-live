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

## Status (2026-11-14)
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
- Not yet known: how usable the UI feels on llvmpipe (I can't see the screen; ask the user).
- Later: GPU rendering (zink + turnip) instead of llvmpipe.
