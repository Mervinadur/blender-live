#!/data/data/com.termux/files/usr/bin/bash
# Shot feed -> photoreal video on several RunPod GPUs at once (Wan 2.1 VACE, ai/vace_shots.py). Shots are independent
# (each starts fresh with the same car reference), so each group of shots goes to its own pod, in parallel.
#
#   ./ai-shots.sh models/car-street "S1_Establish,S2_Tracking,S3_Orbit,S4_Details,S4b_Tail,S5_Drive_off"   # one pod
#   ./ai-shots.sh models/car-street "S2_Tracking" "S3_Orbit" "S5_Drive_off,S4b_Tail" "S1_Establish,S4_Details"  # 4 pods
#
# Input: <model>/ai_in/ (depth/, mask/, shots.json, prompt.txt, negative.txt, ref_frame.txt; made by feed.py + Claude).
# Output: <model>/ai_out/o_*.png, per-pod logs <model>/ai_logs/pod*.log, then <model>/ai_out_<WxH>.mp4.
# Env: STEPS (16, auto-lowered to fit), BUDGET (30 = minutes of generation per pod), SIZE (960x432 = 2.2:1),
#      FINAL (2780x1264 = OnePlus 13R full screen), MAX_MINUTES (55, pod self-delete), GPUS / CLOUD as in ai-remote.sh,
#      EXTRA_ARGS (more script args; "--offload" is needed on 24 GB cards: the full model OOMs on a 4090),
#      SCRIPT (vace_shots.py = depth-only VACE; v2v_shots.py = video-to-video from the Blender colour render in ai_in/render/).
set -uo pipefail
case "${1:-}" in ""|-h|--help) sed -n '2,11p' "$0"; exit;; esac
DIR="$HOME/blender-live"; M="$(realpath "$1")"; shift
STEPS="${STEPS:-16}"; BUDGET="${BUDGET:-30}"; SIZE="${SIZE:-960x432}"; FINAL="${FINAL:-2780x1264}"
export MAX_MINUTES="${MAX_MINUTES:-55}"
mkdir -p "$M/ai_logs" "$M/ai_out"; T0=$(date +%s); PIDS=(); i=0
for g in "$@"; do
  i=$((i + 1))
  SCRIPT="${SCRIPT:-vace_shots.py}" ENCODE=0 TAG="-$i" STEPS="$STEPS" ARGS="--shots $g --size $SIZE --budget-min $BUDGET ${EXTRA_ARGS:-}" \
    "$DIR/ai-remote.sh" "$M" > "$M/ai_logs/pod$i.log" 2>&1 &
  PIDS+=($!); echo "pod$i: $g (log ai_logs/pod$i.log)"; sleep 5
done
while :; do
  sleep 60; alive=0
  for p in "${PIDS[@]}"; do kill -0 "$p" 2>/dev/null && alive=$((alive + 1)); done
  echo "[$(date +%H:%M:%S) +$(( ($(date +%s) - T0) / 60 ))m] running $alive/${#PIDS[@]}, frames $(ls "$M/ai_out" | grep -c '^o_' || true)"
  for j in $(seq 1 $i); do echo "   pod$j: $(grep -vE '%\||it/s\]|s/it\]' "$M/ai_logs/pod$j.log" | tail -1 | cut -c1-150)"; done
  [ "$alive" = 0 ] && break
done
FAIL=0; for p in "${PIDS[@]}"; do wait "$p" || FAIL=$((FAIL + 1)); done
grep -h "Pod time" "$M"/ai_logs/pod*.log
awk '/Pod time/{gsub(/\$/,"",$NF); s+=$NF} END{printf "== Total pod cost about $%.2f\n", s}' "$M"/ai_logs/pod*.log
N=$(ls "$M/ai_out" | grep -c '^o_' || true); echo "== $N frames, $FAIL pod(s) failed"
[ "$N" -gt 0 ] || { echo "!! No frames generated, nothing to encode"; exit 1; }
# encode: Lanczos upscale to the phone's full screen, 16 fps (gaps stop ffmpeg, so fill missing frames by repeating the last)
last=""; for f in $(seq 1 "$(jq '.[-1].f1' "$M/ai_in/shots.json")"); do
  p=$(printf "%s/ai_out/o_%04d.png" "$M" "$f"); [ -f "$p" ] && last="$p" || { [ -n "$last" ] && cp "$last" "$p" && echo "   filled missing frame $f"; }
done
ffmpeg -v error -y -framerate 16 -i "$M/ai_out/o_%04d.png" -vf "scale=${FINAL/x/:}:flags=lanczos" \
  -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p "$M/ai_out_${FINAL}.mp4"
echo "== Done in $(( ($(date +%s) - T0) / 60 )) min: $M/ai_out_${FINAL}.mp4"
