# Blender Live: notes for Claude

## What
Blender (Debian trixie package, in `proot-distro` Debian) shown in the Termux:X11 app. The blender-mcp
add-on (`addon.py`, fetched by `setup.sh`, pinned commit, gitignored) runs a socket server on
localhost:9876 (auto-start defaults on). Claude Code talks to it via the `blender` MCP server
(`uvx blender-mcp`, run inside Debian).

## Files
- `setup.sh`: one-time install (x11-repo, termux-x11-nightly, Debian, blender, python3-requests, uv, add-on).
- `start-blender.sh`: starts termux-x11 :0, opens the app, runs Blender with `--python addon.py`.
  Binds `models/` → `/root/models` inside Debian. Uses llvmpipe (software GL).
- `models/`: the user's working files (gitignored).

## Rules
- The add-on's generation integrations (Hyper3D/Rodin, Tripo, Meshy, World Labs, Sketchfab) stay **off**.
  This follows the spirit of the user's generation ban; ask before enabling any.
- I can't see the X11 window. Verify through MCP scene info / dimensions, or render previews to `models/`.

## Status (2026-11-14)
- Done: Debian installed; Blender install running; scripts + docs written; Termux:X11 APK downloaded
  to `~/downloads/termux-x11/` and installer opened (user to confirm install).
- To do: install python3-requests + uv in Debian, register MCP server in Claude Code, first live test.
- Later: GPU rendering (zink + turnip) instead of llvmpipe.
