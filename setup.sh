#!/data/data/com.termux/files/usr/bin/bash
# One-time setup in Termux: X11, Debian (proot), Blender, blender-mcp add-on + MCP server.
# The Termux:X11 Android app must be installed separately (APK from termux/termux-x11 releases).
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
ADDON_COMMIT=8f40787fbde8e6d8fe51c5a3553e5635fff40d2b   # ahujasid/blender-mcp (MIT)

yes | pkg install -y x11-repo
yes | pkg install -y termux-x11-nightly proot-distro
[ -d "$PREFIX/var/lib/proot-distro/installed-rootfs/debian" ] || proot-distro install debian
proot-distro login debian -- bash -c 'apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y blender python3-requests mesa-utils curl ca-certificates && (command -v uvx || curl -LsSf https://astral.sh/uv/install.sh | sh)'

curl -fsSL "https://raw.githubusercontent.com/ahujasid/blender-mcp/$ADDON_COMMIT/addon.py" -o "$DIR/addon.py"
mkdir -p "$DIR/models"
echo "Done. Start with: bash $DIR/start-blender.sh"
