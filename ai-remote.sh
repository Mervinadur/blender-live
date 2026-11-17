#!/data/data/com.termux/files/usr/bin/bash
# Make a Blender walk-through photoreal with a self-hosted Wan 2.1 VACE model on one RunPod GPU (no Replicate).
#
#   ./ai-remote.sh models/nature-trail                 # all chunks (uses <model>/ai_in/f_*.jpg + anchor.jpg)
#   CHUNKS=2 ./ai-remote.sh models/nature-trail        # test: first 2 chunks only (~10 s of video)
#   MODEL=14B ./ai-remote.sh models/nature-trail       # bigger model (needs a 48 GB+ GPU, slower, costs more)
#
# Inputs: <model>/ai_in/f_0001.jpg… (832x480, 16 fps) and optional ai_in/anchor.jpg (photoreal still of frame 1).
# Output: <model>/ai_out/o_*.png (+ ai_out_depth/), then ai_out.mp4. Re-run resumes (frames already there are uploaded back).
# Env: SCRIPT (vace_trail.py; vace_shots.py = shot feed, see ai-shots.sh), ARGS (extra script args), ENCODE (1), TAG (pod name suffix).
# Env: MODEL (1.3B), CHUNKS (0 = all), STEPS (30), MAX_MINUTES (150), GPUS (comma list), CLOUD ("COMMUNITY SECURE").
# The pod runs the job in the background and deletes itself after MAX_MINUTES even if the phone drops off.
set -euo pipefail
API="https://api.runpod.io/v2"
DIR="$HOME/blender-live"
case "${1:-}" in ""|-h|--help) sed -n '2,14p' "$0"; exit;; esac
KEY="$(cat "$HOME/.config/runpod/api_key")"
api() { curl -sS -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" "$@"; }
M="$(realpath "$1")"; IN="$M/ai_in"; OUT="$M/ai_out"
[ -n "$(ls -A "$IN" 2>/dev/null)" ] || { echo "No input in $IN"; exit 1; }
SCRIPT="${SCRIPT:-vace_trail.py}"; ARGS="${ARGS:-}"; ENCODE="${ENCODE:-1}"; TAG="${TAG:-}"
MODEL="${MODEL:-1.3B}"; CHUNKS="${CHUNKS:-0}"; STEPS="${STEPS:-30}"; MAX_MINUTES="${MAX_MINUTES:-150}"
if [ "$MODEL" = 14B ]; then DEF="NVIDIA L40S,NVIDIA RTX A6000,NVIDIA A100 80GB PCIe,NVIDIA H100 80GB HBM3"; DISK=150
else DEF="NVIDIA GeForce RTX 4090,NVIDIA L40S,NVIDIA RTX A6000,NVIDIA GeForce RTX 3090,NVIDIA RTX A5000"; DISK=80; fi
IFS=, read -ra GPUS <<<"${GPUS:-$DEF}"
IMAGE="runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04"
SSHKEY="$HOME/.ssh/runpod_ed25519"
SSHO=(-i "$SSHKEY" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=10 -o ServerAliveInterval=30)
mkdir -p "$OUT"
POD=""; T0=""; RATE=""
el() { echo "[$(date +%H:%M:%S) +$(( $(date +%s) - ${T0:-$(date +%s)} ))s]"; }   # stage timestamps (since pod created)
bye() { [ -n "$POD" ] && api -X DELETE "$API/pods/$POD" >/dev/null && echo "== Pod $POD deleted"
        [ -n "$T0" ] && awk -v s=$(( $(date +%s) - T0 )) -v r="${RATE:-0}" 'BEGIN{printf "== Pod time %dm%02ds, about $%.2f\n", s/60, s%60, s/3600*r}'; }
trap bye EXIT; trap 'exit 130' INT TERM

# 1. Get a pod with a public SSH port (same approach as render-remote.sh).
for G in "${GPUS[@]}"; do for CL in ${CLOUD:-COMMUNITY SECURE}; do
  R="$(jq -n --arg g "$G" --arg c "$CL" --arg i "$IMAGE" --arg pk "$(cat "$SSHKEY.pub")" --arg t "$TAG" --argjson d "$DISK" \
      '{name:("ai-vace"+$t), image:$i, gpu:{id:$g,count:1}, cloud:$c, disk:$d, ports:["22/tcp"], env:{PUBLIC_KEY:$pk}}' \
      | api -X POST "$API/pods" -d @-)"
  POD="$(jq -r '.id // empty' <<<"$R" 2>/dev/null || true)"
  [ -n "$POD" ] || { echo "   $G / $CL: $(jq -r '.detail // .title // .' <<<"$R" 2>/dev/null | head -c 120)"; continue; }
  T0=$(date +%s); RATE="$(jq -r '.cost // empty' <<<"$R")"; echo "== Pod $POD ($G, $CL, \$${RATE:-?}/h)"
  IP=""; PORT=""; RUN_T=""
  for i in $(seq 1 120); do
    P="$(api "$API/pods/$POD")"; ST="$(jq -r '.status // empty' <<<"$P")"
    IP="$(jq -r 'if .status=="RUNNING" then .ssh.direct.host // empty else empty end' <<<"$P")"
    PORT="$(jq -r 'if .status=="RUNNING" then .ssh.direct.port // empty else empty end' <<<"$P")"
    [ -n "$IP" ] && [ -n "$PORT" ] && break 3
    [ "$ST" = ERROR ] && break
    if [ "$ST" = RUNNING ]; then [ -n "$RUN_T" ] || RUN_T=$(date +%s); [ $(( $(date +%s) - RUN_T )) -gt 60 ] && break; fi
    sleep 5
  done
  echo "   no public SSH, trying the next one"; api -X DELETE "$API/pods/$POD" >/dev/null; POD=""; T0=""
done; done
[ -n "$POD" ] || { echo "!! No GPU free right now"; exit 2; }
[ -n "$RATE" ] || RATE="$(jq -r '.cost // empty' <<<"$P")"
rsh() { ssh "${SSHO[@]}" -p "$PORT" "root@$IP" "$@"; }
for i in $(seq 1 60); do rsh true 2>/dev/null && break; [ "$i" = 60 ] && { echo "!! SSH never answered"; exit 1; }; sleep 5; done
echo "$(el) SSH up"
rsh "nohup bash -c 'sleep $((MAX_MINUTES*60)); curl -s -X DELETE -H \"Authorization: Bearer $KEY\" $API/pods/$POD' >/dev/null 2>&1 &"

# 2. Upload frames, earlier results (resume) and the script; start the job in the background.
echo "$(el) == Uploading ($(du -sh "$IN" | cut -f1))"
rsh "mkdir -p /workspace/job/out /workspace/job/out_depth"
tar -cf - -C "$M" ai_in | rsh "tar -xf - -C /workspace/job"
[ -n "$(ls "$OUT")" ] && tar -cf - -C "$OUT" . | rsh "tar -xf - -C /workspace/job/out"
[ -d "${OUT}_depth" ] && tar -cf - -C "${OUT}_depth" . | rsh "tar -xf - -C /workspace/job/out_depth"
ANCH=""; [ -f "$IN/anchor.jpg" ] && ANCH="--anchor ai_in/anchor.jpg"
rsh "cat > /workspace/job/$SCRIPT" < "$DIR/ai/$SCRIPT"
if [ "$SCRIPT" = vace_trail.py ]; then RUN="python vace_trail.py --frames ai_in $ANCH --out out --model $MODEL --chunks $CHUNKS --steps $STEPS"
else RUN="python $SCRIPT --feed ai_in --out out --model $MODEL --steps $STEPS $ARGS"; fi
rsh "cd /workspace/job && nohup bash -c 'export HF_HUB_ENABLE_HF_TRANSFER=1 HF_HOME=/workspace/hf; echo pip start \$(date +%T)
  pip install -q torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124 &&
  pip install -q diffusers==0.35.1 transformers==4.56.1 accelerate==1.10.1 ftfy sentencepiece hf_transfer imageio-ffmpeg && echo pip done \$(date +%T) &&
  $RUN; echo EXIT \$?' > log.txt 2>&1 < /dev/null &"  </dev/null

# 3. Follow the log every minute until the job finishes, then pull the frames.
pull() { rsh "cd /workspace/job && tar -cf - out out_depth 2>/dev/null" | tar -xf - -C "$M/.ai_tmp_$$" 2>/dev/null || true
         cp -n "$M"/.ai_tmp_$$/out/* "$OUT"/ 2>/dev/null || true; mkdir -p "${OUT}_depth"; cp -n "$M"/.ai_tmp_$$/out_depth/* "${OUT}_depth"/ 2>/dev/null || true; }
mkdir -p "$M/.ai_tmp_$$"; SEEN=0
while :; do
  sleep 60
  L="$(rsh 'cat /workspace/job/log.txt' 2>/dev/null || true)"
  N=$(wc -l <<<"$L"); [ "$N" -gt "$SEEN" ] && { tail -n +$((SEEN + 1)) <<<"$L" | grep -vE '%\||it/s\]|s/it\]' | tail -20; SEEN=$N; }
  grep -q '^EXIT' <<<"$L" && break
  [ $(( $(date +%s) - T0 )) -gt $((MAX_MINUTES*60)) ] && { echo "!! Out of time"; break; }
done
echo "$(el) == Downloading"; pull; echo "$(el) downloaded"; rm -rf "$M/.ai_tmp_$$"
grep -q '^EXIT 0' <<<"$L" || { echo "!! The job failed (log above). Frames so far are in $OUT; re-run resumes."; exit 1; }

# 4. Encode (16 fps, upscaled to 1280x720). ENCODE=0 skips it (ai-shots.sh encodes once at the end).
[ "$ENCODE" = 1 ] || { echo "$(el) == Done (frames in $OUT)"; exit 0; }
ffmpeg -v error -y -framerate 16 -i "$OUT/o_%04d.png" -vf "scale=1280:-2:flags=lanczos" -c:v libx264 -crf 20 -pix_fmt yuv420p "$M/ai_out.mp4"
echo "$(el) == Done: $M/ai_out.mp4 ($(ls "$OUT" | wc -l) frames)"
