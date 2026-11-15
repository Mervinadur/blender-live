#!/data/data/com.termux/files/usr/bin/bash
# Render a .blend on rented RunPod GPUs, download the frames, then delete the pods.
#
#   ./render-remote.sh models/knight/knight_v3.blend -a                 # all frames, 1 pod
#   PODS=4 ./render-remote.sh models/knight/knight_v3.blend -a          # frames split over 4 pods at once
#   ./render-remote.sh models/knight/knight_v3.blend -s 1 -e 24 -a      # a frame range
#   ./render-remote.sh models/coffee-mug/coffee_mug.blend -f 1          # one still
#   ./render-remote.sh --list          # show pods on the account (check nothing is left billing)
#   ./render-remote.sh --kill-all      # delete every pod on the account
#
# Frames land in <blend folder>/remote_frames/ (or $OUT_DIR). Other args (e.g. -E CYCLES) go to Blender.
# Pods are deleted when their part is done, on Ctrl-C, and by a timer on each pod ($MAX_MINUTES).
#
# Settings (env): RUNPOD_API_KEY or ~/.config/runpod/api_key; PODS (default 1); GPU (default RTX 4090,
# falls back to 3090/A5000); IMAGE (default the ready-made ghcr.io/mervinadur/blender-render:4.3.2;
# IMAGE=ubuntu:24.04 installs Blender on boot instead); PACK=0 to upload the file as is;
# CLOUD=SECURE to skip Community Cloud; MAX_MINUTES (default 90);
# PRE_PY=script.py runs that script on each pod before rendering (after the GPU setup).
set -euo pipefail
DIR="$HOME/blender-live"
API="https://api.runpod.io/v2"   # REST v2: new scoped keys (Pods R/W) only work here, not on v1
case "${1:-}" in ""|-h|--help) sed -n '2,19p' "$0"; exit;; esac
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
OUT_DIR="$(realpath -m "${OUT_DIR:-$(dirname "$BLEND")/remote_frames}")"
BV="4.3.2"                                        # same Blender as the phone
IMAGE="${IMAGE:-ghcr.io/mervinadur/blender-render:$BV}"
GPU="${GPU:-NVIDIA GeForce RTX 4090}"
PODS="${PODS:-1}"
MAX_MINUTES="${MAX_MINUTES:-90}"
WORK="${TMPDIR:-$PREFIX/tmp}/render-remote-$$"; mkdir -p "$WORK" "$OUT_DIR"

# Frame arguments: -f N (one frame) or [-s A] [-e B] -a (range, split over the pods); the rest go to Blender.
FS=""; FE=""; FRAME=""; ANIM=0; EXTRA=()
while [ $# -gt 0 ]; do
  case "$1" in
    -s) FS="$2"; shift 2;; -e) FE="$2"; shift 2;; -f) FRAME="$2"; shift 2;; -a) ANIM=1; shift;;
    *) EXTRA+=("$1"); shift;;
  esac
done
[ -n "$FRAME" ] || [ "$ANIM" = 1 ] || { echo "Give -f N (one frame) or -a (animation)"; exit 1; }

SSHKEY="$HOME/.ssh/runpod_ed25519"               # SSH key used only for pods
[ -f "$SSHKEY" ] || ssh-keygen -q -t ed25519 -N "" -C runpod -f "$SSHKEY"

# 1. Read the frame range, and pack textures/assets into a copy of the .blend (the original is not changed).
echo "== Preparing the file (local Blender $BV)"
REL="${BLEND#"$DIR/models/"}"
PY="import bpy; s=bpy.context.scene; print('RANGE', s.frame_start, s.frame_end)"
[ "${PACK:-1}" = 1 ] && PY+="; bpy.ops.file.pack_all(); bpy.ops.wm.save_as_mainfile(filepath='/root/models/.packed-$$.blend', copy=True, compress=True)"
proot-distro login debian --shared-tmp --bind "$DIR/models:/root/models" \
  --bind "$DIR/cpuinfo-nosve:/proc/cpuinfo" -- \
  env LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe blender -b "/root/models/$REL" --python-expr "$PY" \
  >"$WORK/pack.log" 2>&1 || { tail -20 "$WORK/pack.log"; exit 1; }
read -r _ SCENE_S SCENE_E < <(grep '^RANGE' "$WORK/pack.log")
UPLOAD="$BLEND"
if [ "${PACK:-1}" = 1 ]; then mv "$DIR/models/.packed-$$.blend" "$WORK/$NAME.blend"; UPLOAD="$WORK/$NAME.blend"; fi
echo "   upload size: $(du -h "$UPLOAD" | cut -f1), scene frames $SCENE_S-$SCENE_E"

# Split the frames into one contiguous chunk per pod.
CHUNKS=()
if [ -n "$FRAME" ]; then
  CHUNKS=("$FRAME $FRAME")
else
  FS="${FS:-$SCENE_S}"; FE="${FE:-$SCENE_E}"; TOTAL=$((FE - FS + 1))
  [ "$PODS" -gt "$TOTAL" ] && PODS="$TOTAL"
  SIZE=$(( (TOTAL + PODS - 1) / PODS ))
  for ((a = FS; a <= FE; a += SIZE)); do b=$((a + SIZE - 1)); [ "$b" -gt "$FE" ] && b="$FE"; CHUNKS+=("$a $b"); done
fi

# 2. Pod settings. The ready-made image boots with Blender installed; a plain image installs it first.
START='set -e; export DEBIAN_FRONTEND=noninteractive; apt-get update -q
apt-get install -yq openssh-server curl xz-utils >/dev/null
mkdir -p /root/.ssh /run/sshd /root/job; echo "$PUBLIC_KEY" > /root/.ssh/authorized_keys; chmod 700 /root/.ssh; chmod 600 /root/.ssh/authorized_keys
/usr/sbin/sshd
apt-get install -yq libx11-6 libxi6 libxxf86vm1 libxfixes3 libxrender1 libxext6 libxkbcommon0 libxkbcommon-x11-0 libsm6 libice6 libgl1 libegl1 libglx0 libwayland-client0 libwayland-cursor0 libwayland-egl1 libdecor-0-0 libxcursor1 libxinerama1 libxrandr2 >/dev/null
mkdir -p /opt/blender; curl -sL "https://download.blender.org/release/Blender${BV%.*}/blender-$BV-linux-x64.tar.xz" | tar -xJ -C /opt/blender --strip-components=1
touch /root/ready; sleep infinity'

create_pod() { # $1 = cloud type, $2 = GPU type id (v2 takes one GPU type per pod)
  jq -n --arg name "render-$NAME" --arg gpu "$2" --arg cloud "$1" --arg start "$START" --arg image "$IMAGE" \
    --arg pk "$(cat "$SSHKEY.pub")" --arg bv "$BV" '{
    name: $name, image: $image, gpu: {id: $gpu, count: 1}, cloud: $cloud,
    disk: 30, ports: ["22/tcp"],
    env: {PUBLIC_KEY: $pk, BV: $bv, NVIDIA_DRIVER_CAPABILITIES: "all"}}
    + (if ($image | startswith("ghcr.io/")) then {} else {cmd: ["bash", "-c", $start]} end)' \
    | api -w '\nHTTP %{http_code}' -X POST "$API/pods" -d @-
}

# GPU setup on the pod: OptiX if it works, else CUDA; every non-CPU device on; Cycles scenes set to GPU.
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
printf '%s\n' "$GPUPY" > "$WORK/gpu.py"

# 3. One pod per chunk: create, wait for SSH, upload, render its frames, download them, delete the pod.
run_chunk() { # $1 = chunk number, $2 = first frame, $3 = last frame
  local n="$1" a="$2" b="$3" RESP CODE TRY_GPU P ST IP="" PORT="" i
  POD=""; T0=""; RATE=""   # not local: the EXIT trap (pod delete) runs after the function returns
  trap '[ -n "$POD" ] && api -X DELETE "$API/pods/$POD" >/dev/null && echo "== Pod $POD deleted"
        [ -n "${T0:-}" ] && echo "COST $(( $(date +%s) - T0 )) ${RATE:-0}"' EXIT
  echo "== Creating pod for frames $a-$b ($GPU)"
  for TRY_GPU in "$GPU" "NVIDIA GeForce RTX 4090" "NVIDIA GeForce RTX 3090" "NVIDIA RTX A5000"; do
    for CLOUD in ${CLOUD:-COMMUNITY SECURE}; do
      RESP="$(create_pod "$CLOUD" "$TRY_GPU")"; CODE="$(tail -1 <<<"$RESP")"; RESP="$(sed '$d' <<<"$RESP")"
      POD="$(jq -r '.id // empty' <<<"$RESP" 2>/dev/null || true)"
      [ -n "$POD" ] && break 2
      echo "   $TRY_GPU / $CLOUD failed ($CODE): $(jq -r '.detail // .title // .' <<<"$RESP" 2>/dev/null | head -c 200)"
      case "$CODE" in *401*) echo "   (API key rejected)"; exit 1;; *403*) echo "   (key lacks Pods Read/Write)"; exit 1;; esac
    done
  done
  [ -n "$POD" ] || { echo "!! No pod created"; exit 1; }
  echo "$POD" >> "$WORK/pods"
  T0=$(date +%s); RATE="$(jq -r '.cost // empty' <<<"$RESP")"
  echo "   pod $POD ($TRY_GPU, $CLOUD, \$${RATE:-?}/h)"
  for i in $(seq 1 120); do
    P="$(api "$API/pods/$POD")"; ST="$(jq -r '.status // empty' <<<"$P")"
    [ "$ST" = ERROR ] && { echo "!! Pod status ERROR"; exit 1; }
    IP="$(jq -r 'if .status == "RUNNING" then .ssh.direct.host // empty else empty end' <<<"$P")"
    PORT="$(jq -r 'if .status == "RUNNING" then .ssh.direct.port // empty else empty end' <<<"$P")"
    [ -n "$IP" ] && [ -n "$PORT" ] && break; sleep 5
  done
  [ -n "$IP" ] && [ -n "$PORT" ] || { echo "!! Pod never got a public SSH port"; exit 1; }
  [ -n "$RATE" ] || RATE="$(jq -r '.cost // empty' <<<"$P")"
  local SSHO=(-i "$SSHKEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=10 -o ServerAliveInterval=30)
  rsh() { ssh "${SSHO[@]}" -p "$PORT" "root@$IP" "$@"; }
  for i in $(seq 1 120); do rsh true 2>/dev/null && break; [ "$i" = 120 ] && { echo "!! SSH never answered"; exit 1; }; sleep 5; done
  echo "   SSH up after $(( $(date +%s) - T0 )) s"
  # Watchdog on the pod: deletes itself after MAX_MINUTES even if this phone loses the connection.
  rsh "nohup bash -c 'sleep $((MAX_MINUTES*60)); curl -s -X DELETE -H \"Authorization: Bearer $KEY\" $API/pods/$POD' >/dev/null 2>&1 &"
  echo "== Uploading"
  timeout 300 scp "${SSHO[@]}" -P "$PORT" "$UPLOAD" "root@$IP:/root/job/scene.blend" \
    || { echo "!! Upload failed or took over 5 min (slow machine); try again for a new one"; exit 1; }
  for i in $(seq 1 120); do rsh test -f /root/ready && break; [ "$i" = 120 ] && { echo "!! Blender not ready after 10 min"; exit 1; }; sleep 5; done
  rsh "cat > /root/job/gpu.py" < "$WORK/gpu.py"
  local PRE=""   # optional extra script (e.g. the denoiser, which the phone's Blender lacks)
  if [ -n "${PRE_PY:-}" ]; then rsh "cat > /root/job/pre.py" < "$PRE_PY"; PRE="--python pre.py"; fi
  local ARGS=""; for x in "${EXTRA[@]}"; do ARGS+=" $(printf '%q' "$x")"; done
  if [ -n "$FRAME" ]; then ARGS+=" -f $a"; else ARGS+=" -s $a -e $b -a"; fi
  echo "== Rendering: blender -b scene.blend$ARGS (ready after $(( $(date +%s) - T0 )) s)"
  rsh "cd /root/job && mkdir -p out && /opt/blender/blender -b scene.blend --python gpu.py $PRE -o /root/job/out/frame_#### $ARGS" 2>&1 \
    | grep --line-buffered -E "GPU devices|Saved:|Error|error|Time:" || true
  local N; N="$(rsh 'ls /root/job/out | wc -l')"
  [ "$N" -gt 0 ] || { echo "!! No frames were rendered"; exit 1; }
  rsh "cd /root/job/out && tar -cf - ." | tar -xf - -C "$OUT_DIR"
  echo "== Downloaded $N frames"
}

cleanup() {
  for pid in $(jobs -p); do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
  if [ -s "$WORK/pods" ]; then           # make sure every pod is gone (already-deleted ones just fail quietly)
    while read -r id; do api -X DELETE "$API/pods/$id" >/dev/null 2>&1 || true; done < "$WORK/pods"
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

echo "== ${#CHUNKS[@]} pod(s), image $IMAGE"
T_START=$(date +%s)
for ((k = 0; k < ${#CHUNKS[@]}; k++)); do
  read -r a b <<<"${CHUNKS[$k]}"
  run_chunk "$((k + 1))" "$a" "$b" > "$WORK/chunk$((k + 1)).log" 2>&1 &
done

# Progress every 30 s until all pods are done.
NFR=0; for c in "${CHUNKS[@]}"; do read -r a b <<<"$c"; NFR=$((NFR + b - a + 1)); done
while [ -n "$(jobs -rp)" ]; do
  sleep 30
  done_n=$(cat "$WORK"/chunk*.log 2>/dev/null | grep -c '^Saved:' || true)
  echo "   $(date +%H:%M:%S)  rendered $done_n/$NFR frames"
done
wait || true

FAIL=0; SECS=0; DOLLARS=0
for ((k = 1; k <= ${#CHUNKS[@]}; k++)); do
  L="$WORK/chunk$k.log"
  echo "--- pod $k (frames ${CHUNKS[$((k - 1))]})"
  grep -vE '^(Saved:|Time:|COST)' "$L" | tail -8 | sed 's/^/   /'
  grep -q '^== Downloaded' "$L" || FAIL=1
  read -r _ s r < <(grep '^COST' "$L" || echo "COST 0 0")
  DOLLARS=$(awk -v d="$DOLLARS" -v s="$s" -v r="$r" 'BEGIN{print d + s/3600*r}')
done
awk -v s=$(( $(date +%s) - T_START )) -v d="$DOLLARS" 'BEGIN{printf "== Total %dm%02ds, about $%.2f\n", s/60, s%60, d}'
[ "$FAIL" = 0 ] || { echo "!! Some pods failed: their frames are missing. Re-run with -s/-e for those frames."; exit 1; }
