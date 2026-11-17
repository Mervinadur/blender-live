#!/data/data/com.termux/files/usr/bin/bash
# Stitch the final video: AI frames for the hand-picked shots, Blender render frames for the rest.
#   ai/stitch.sh models/robot-scene [PREFIX o_] [FINAL 2780x1264]
# Takes <model>/ai_out/<PREFIX>####.png where present, else <model>/ai_in/render/frame_####.jpg, frames 1..last of shots.json.
set -euo pipefail
M="$(realpath "$1")"; PRE="${2:-o_}"; FINAL="${3:-2780x1264}"; S="$M/.stitch"; rm -rf "$S"; mkdir -p "$S"
LAST=$(jq '.[-1].f1' "$M/ai_in/shots.json"); FIRST=$(jq '.[0].f0' "$M/ai_in/shots.json"); ai=0; bl=0
for f in $(seq "$FIRST" "$LAST"); do
  a=$(printf "%s/ai_out/%s%04d.png" "$M" "$PRE" "$f"); r=$(printf "%s/ai_in/render/frame_%04d.jpg" "$M" "$f")
  if [ -f "$a" ]; then ln -s "$a" "$(printf "%s/f_%04d.png" "$S" "$f")"; ai=$((ai + 1))
  else ffmpeg -v error -y -i "$r" -vf scale=960:432 "$(printf "%s/f_%04d.png" "$S" "$f")"; bl=$((bl + 1)); fi
done
OUTF="$M/final_${FINAL}.mp4"
ffmpeg -v error -y -start_number "$FIRST" -framerate 16 -i "$S/f_%04d.png" -vf "scale=${FINAL/x/:}:flags=lanczos" \
  -c:v libx264 -crf 18 -preset medium -pix_fmt yuv420p "$OUTF"
rm -rf "$S"; echo "== $OUTF  ($ai AI frames, $bl Blender frames)"
