#!/data/data/com.termux/files/usr/bin/bash
# Opens Blender (Debian in proot) in the Termux:X11 app, with the blender-mcp
# add-on loaded. The add-on listens on localhost:9876 for Claude Code.
# Models live in ~/blender-live/models (seen as /root/models inside Debian).
set -e
DIR="$HOME/blender-live"
mkdir -p "$DIR/models"

pkill -f "termux.x11" 2>/dev/null || true
termux-x11 :0 >/dev/null 2>&1 &
sleep 2
am start --user 0 -n com.termux.x11/com.termux.x11.MainActivity >/dev/null 2>&1 || true

# Software OpenGL (llvmpipe) for now: slower, but works in proot. GPU (zink/turnip) is a later step.
exec proot-distro login debian --shared-tmp \
  --bind "$DIR/models:/root/models" \
  --bind "$DIR/addon.py:/root/blender-mcp-addon.py" \
  -- env DISPLAY=:0 LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe MESA_GL_VERSION_OVERRIDE=4.5 \
  blender --python /root/blender-mcp-addon.py "$@"
