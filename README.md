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

## Limits
- Renders on the CPU for now (software OpenGL), so heavy scenes are slow.
- Blender makes meshes. For exact parametric parts for Inventor (STEP), use CAD Agent.
- The add-on's online model services (Hyper3D, Tripo, Sketchfab, …) stay off.

## Troubleshooting
- **X11 app says "Not connected"**: the X server isn't running. Run `bash ~/blender-live/start-blender.sh`.
- **Blender quits with "Illegal instruction"**: the start script already works around this (it hides the
  phone's CPU type from the software renderer). If it comes back, run
  `proot-distro login debian -- rm -rf /root/.cache/mesa_shader_cache /root/.cache/mesa_shader_cache_db`
  and start again.

## Examples
- `examples/astronaut_walk.gif`: the rigged astronaut walking, a 1-second looping isometric animation (480×480, 12 fps).
- `examples/astronaut_moon.gif`: the astronaut on the Moon, with slow low-gravity hops and then a big leap over a cratered surface (4-second loop, 400×400).
- `examples/coffee_mug_colours.gif`: 5-second looping isometric animation of the mug changing through 5 colours.
- `examples/coffee_mug.stl`: a coffee mug made by Claude in Blender. Units are millimetres
  (80 mm wide, 95.5 mm tall, 115 mm including the handle). Download it from GitHub: open the file and tap the download button.
