#!/data/data/com.termux/files/usr/bin/bash
# Render a .blend on a rented RunPod GPU, download the frames, then delete the pod.
#
#   ./render-remote.sh models/knight/knight_turntable.blend -a                  # all frames, scene's engine
#   ./render-remote.sh models/knight/knight_turntable.blend -E CYCLES -s 1 -e 24 -a
#   ./render-remote.sh models/coffee-mug/coffee_mug.blend -f 1                  # one still
#   ./render-remote.sh --list          # show pods on the account (check nothing is left billing)
#   ./render-remote.sh --kill-all      # delete every pod on the account
#
# Everything after the .blend goes straight to Blender (after -b file). Frames land in
# <blend folder>/remote_frames/ (or $OUT_DIR). The pod is deleted when the script ends, on
# Ctrl-C, and by a timer on the pod itself ($MAX_MINUTES, default 90) in case the phone drops.
#
# Settings (env): RUNPOD_API_KEY or ~/.config/runpod/api_key; GPU (default RTX 4090, falls back);
# BLENDER_VERSION (default 4.3.2, matches the phone; 5.x works but can't be packed here, so PACK=0);
# PACK=0 to upload the file as is; CLOUD=SECURE to skip Community Cloud; MAX_MINUTES.
set -euo pipefail
DIR="$HOME/blender-live"
API="https://api.runpod.io/v2"   # REST v2: new scoped keys (Pods R/W) only work here, not on v1
case "${1:-}" in ""|-h|--help) sed -n '2,17p' "$0"; exit;; esac
KEY="${RUNPOD_API_KEY:-$(cat "$HOME/.config/runpod/api_key" 2>/dev/null || true)}"
[ -n "$KEY" ] || { echo "No API key. Put it in ~/.config/runpod/api_key (chmod 600)."; exit 1; }
api() { curl -sS -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" "$@"; }

case "${1:-}" in
  --list) api "$API/pods" | jq -r '.pods[] | "\(.id)  \(.name)  \(.status)  $\(.cost)/h"'; exit;;
  --kill-all) for id in $(api "$API/pods" | jq -r '.pods[].id'); do api -X DELETE "$API/pods/$id" >/dev/null; echo "deleted $id"; done; exit;;
esac

BLEND="$(realpath "$1")"; shift
case "$BLEND" in "$DIR/models/"*.blend) ;; *) echo "The .blend must be inside $DIR/models/"; exit 1;; esac
NAME="$(basename "$BLEND" .blend)"
OUT_DIR="${OUT_DIR:-$(dirname "$BLEND")/remote_frames}"
BV="${BLENDER_VERSION:-4.3.2}"
GPU="${GPU:-NVIDIA GeForce RTX 4090}"
MAX_MINUTES="${MAX_MINUTES:-90}"
WORK="${TMPDIR:-$PREFIX/tmp}/render-remote-$$"; mkdir -p "$WORK" "$OUT_DIR"

# SSH key used only for pods.
SSHKEY="$HOME/.ssh/runpod_ed25519"
[ -f "$SSHKEY" ] || ssh-keygen -q -t ed25519 -N "" -C runpod -f "$SSHKEY"

# 1. Pack textures/assets into a copy of the .blend (the original is not changed).
UPLOAD="$BLEND"
if [ "${PACK:-1}" = 1 ]; then
  echo "== Packing assets into a copy (local Blender 4.3)"
  REL="${BLEND#"$DIR/models/"}"
  proot-distro login debian --shared-tmp --bind "$DIR/models:/root/models" \
    --bind "$DIR/cpuinfo-nosve:/proc/cpuinfo" -- \
    env LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe blender -b "/root/models/$REL" --python-expr \
    "import bpy; bpy.ops.file.pack_all(); bpy.ops.wm.save_as_mainfile(filepath='/root/models/.packed-$$.blend', copy=True, compress=True)" \
    >"$WORK/pack.log" 2>&1 || { tail -20 "$WORK/pack.log"; exit 1; }
  mv "$DIR/models/.packed-$$.blend" "$WORK/$NAME.blend"; UPLOAD="$WORK/$NAME.blend"
fi
echo "   upload size: $(du -h "$UPLOAD" | cut -f1)"

# 2. Pod start command: sshd first (so the upload can start), then Blender + its libraries.
BMAJ="${BV%.*}"
START='set -e; export DEBIAN_FRONTEND=noninteractive; apt-get update -q
apt-get install -yq openssh-server curl xz-utils >/dev/null
mkdir -p /root/.ssh /run/sshd /root/job; echo "$PUBLIC_KEY" > /root/.ssh/authorized_keys; chmod 700 /root/.ssh; chmod 600 /root/.ssh/authorized_keys
/usr/sbin/sshd
apt-get install -yq libx11-6 libxi6 libxxf86vm1 libxfixes3 libxrender1 libxext6 libxkbcommon0 libxkbcommon-x11-0 libsm6 libice6 libgl1 libegl1 libglx0 libwayland-client0 libwayland-cursor0 libwayland-egl1 libdecor-0-0 libxcursor1 libxinerama1 libxrandr2 >/dev/null
mkdir -p /opt/blender; curl -sL "https://download.blender.org/release/Blender$BMAJ/blender-$BV-linux-x64.tar.xz" | tar -xJ -C /opt/blender --strip-components=1
touch /root/ready; sleep infinity'

create_pod() { # $1 = cloud type, $2 = GPU type id (v2 takes one GPU type per pod)
  jq -n --arg name "render-$NAME" --arg gpu "$2" --arg cloud "$1" --arg start "$START" \
    --arg pk "$(cat "$SSHKEY.pub")" --arg bv "$BV" --arg bmaj "$BMAJ" '{
    name: $name, image: "ubuntu:24.04", gpu: {id: $gpu, count: 1}, cloud: $cloud,
    disk: 30, ports: ["22/tcp"],
    env: {PUBLIC_KEY: $pk, BV: $bv, BMAJ: $bmaj, NVIDIA_DRIVER_CAPABILITIES: "all"},
    cmd: ["bash", "-c", $start]}' | api -w '\nHTTP %{http_code}' -X POST "$API/pods" -d @-
}

POD=""
cleanup() {
  if [ -n "$POD" ]; then
    api -X DELETE "$API/pods/$POD" >/dev/null && echo "== Pod $POD deleted" \
      || echo "!! Could not delete pod $POD: run ./render-remote.sh --kill-all or delete it on runpod.io"
    if [ -n "${T0:-}" ] && [ -n "${RATE:-}" ]; then
      awk -v s=$(( $(date +%s) - T0 )) -v r="$RATE" 'BEGIN{printf "   time %dm%02ds, about $%.2f\n", s/60, s%60, s/3600*r}'
    fi
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

echo "== Creating pod ($GPU, Blender $BV)"
for TRY_GPU in "$GPU" "NVIDIA GeForce RTX 4090" "NVIDIA GeForce RTX 3090" "NVIDIA RTX A5000"; do
  for CLOUD in ${CLOUD:-COMMUNITY SECURE}; do
    RESP="$(create_pod "$CLOUD" "$TRY_GPU")"; CODE="$(tail -1 <<<"$RESP")"; RESP="$(sed '$d' <<<"$RESP")"
    POD="$(jq -r '.id // empty' <<<"$RESP" 2>/dev/null || true)"
    [ -n "$POD" ] && break 2
    echo "   $TRY_GPU / $CLOUD failed ($CODE): $(jq -r '.detail // .title // .' <<<"$RESP" 2>/dev/null | head -c 300)"
    case "$CODE" in *401*) echo "   (API key rejected)"; exit 1;; *403*) echo "   (key lacks Pods Read/Write)"; exit 1;; esac
  done
done
[ -n "$POD" ] || { echo "!! No pod created"; exit 1; }
T0=$(date +%s); RATE="$(jq -r '.cost // empty' <<<"$RESP")"
echo "   pod $POD ($TRY_GPU, $CLOUD, \$${RATE:-?}/h)"

echo "== Waiting for SSH"
for i in $(seq 1 120); do
  P="$(api "$API/pods/$POD")"; ST="$(jq -r '.status // empty' <<<"$P")"
  [ "$ST" = ERROR ] && { echo "!! Pod status ERROR"; exit 1; }
  IP="$(jq -r 'if .status == "RUNNING" then .ssh.direct.host // empty else empty end' <<<"$P")"
  PORT="$(jq -r 'if .status == "RUNNING" then .ssh.direct.port // empty else empty end' <<<"$P")"
  [ -n "$IP" ] && [ -n "$PORT" ] && break; sleep 5
done
[ -n "${IP:-}" ] && [ -n "${PORT:-}" ] || { echo "!! Pod never got a public SSH port"; exit 1; }
[ -n "$RATE" ] || RATE="$(jq -r '.cost // empty' <<<"$P")"
SSHO=(-i "$SSHKEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=10 -o ServerAliveInterval=30)
rsh() { ssh "${SSHO[@]}" -p "$PORT" "root@$IP" "$@"; }
for i in $(seq 1 120); do rsh true 2>/dev/null && break; [ "$i" = 120 ] && { echo "!! SSH never answered"; exit 1; }; sleep 5; done

# Watchdog on the pod: deletes itself after MAX_MINUTES even if this phone loses the connection.
rsh "nohup bash -c 'sleep $((MAX_MINUTES*60)); curl -s -X DELETE -H \"Authorization: Bearer $KEY\" $API/pods/$POD' >/dev/null 2>&1 &"

echo "== Uploading"
scp "${SSHO[@]}" -P "$PORT" "$UPLOAD" "root@$IP:/root/job/scene.blend"
echo "== Waiting for Blender install"
for i in $(seq 1 120); do rsh test -f /root/ready && break; [ "$i" = 120 ] && { echo "!! Blender install took over 10 min"; exit 1; }; sleep 5; done

# GPU setup: OptiX if it works, else CUDA; every non-CPU device on; Cycles scenes set to GPU.
GPUPY='import bpy
p = bpy.context.preferences.addons["cycles"].preferences
for t in ("OPTIX", "CUDA"):
    try:
        p.compute_device_type = t; p.get_devices()
    except TypeError:
        continue
    if any(d.type == t for d in p.devices): break
for d in p.devices: d.use = d.type != "CPU"
for s in bpy.data.scenes: s.cycles.device = "GPU"
print("GPU devices:", [(d.name, d.type) for d in p.devices if d.use])'
printf '%s\n' "$GPUPY" | rsh "cat > /root/job/gpu.py"

ARGS=""; for a in "$@"; do ARGS+=" $(printf '%q' "$a")"; done
echo "== Rendering: blender -b scene.blend$ARGS"
rsh "cd /root/job && mkdir -p out && /opt/blender/blender -b scene.blend --python gpu.py -o /root/job/out/frame_#### $ARGS" 2>&1 \
  | grep --line-buffered -E "GPU devices|Saved:|Error|error|Fra:[0-9]+ .*(Rendering|Sample) [0-9]+ / |Time:" || true

echo "== Downloading frames to $OUT_DIR"
N="$(rsh 'ls /root/job/out | wc -l')"
[ "$N" -gt 0 ] || { echo "!! No frames were rendered"; exit 1; }
rsh "cd /root/job/out && tar -cf - ." | tar -xf - -C "$OUT_DIR"
echo "   $N files"
