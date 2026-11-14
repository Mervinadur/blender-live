#!/data/data/com.termux/files/usr/bin/bash
# One-time setup in Termux: X11, Debian (proot), Blender, blender-mcp add-on + MCP server.
# The Termux:X11 Android app must be installed separately (APK from termux/termux-x11 releases).
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
ADDON_COMMIT=8f40787fbde8e6d8fe51c5a3553e5635fff40d2b   # ahujasid/blender-mcp (MIT)

yes | pkg install -y x11-repo
yes | pkg install -y termux-x11-nightly proot-distro
[ -d "$PREFIX/var/lib/proot-distro/installed-rootfs/debian" ] || proot-distro install debian
proot-distro login debian -- bash -c 'apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y blender python3-requests python3-venv mesa-utils curl ca-certificates && ([ -x /opt/blender-mcp/bin/blender-mcp ] || (python3 -m venv /opt/blender-mcp && /opt/blender-mcp/bin/pip install -q blender-mcp))'
# Register the MCP server with Claude Code (venv inside Debian; Termux's uvx can't run there)
# Telemetry off: blender-mcp otherwise sends usage events to its author's Supabase.
(cd ~ && { claude mcp get blender >/dev/null 2>&1 || claude mcp add blender -s user -- proot-distro login debian -- env DISABLE_TELEMETRY=true BLENDER_MCP_DISABLE_TELEMETRY=true MCP_DISABLE_TELEMETRY=true /opt/blender-mcp/bin/blender-mcp; })

curl -fsSL "https://raw.githubusercontent.com/ahujasid/blender-mcp/$ADDON_COMMIT/addon.py" -o "$DIR/addon.py"
mkdir -p "$DIR/models"
echo "Done. Start with: bash $DIR/start-blender.sh"
