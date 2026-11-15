# Runs ON the RunPod pod. Turns a Blender walk-through (frames) into one continuous photoreal video with Wan 2.1 VACE.
# Coherence comes from the 3D scene: every frame is conditioned on its depth map (Depth Anything V2 on the Blender
# frames), and every chunk after the first starts from the last OVERLAP frames already generated (VACE extension),
# so there are no cuts. Chunk 0 starts from ANCHOR (a photoreal still of frame 1) to set the look.
#
#   python vace_trail.py --frames in --anchor in/anchor.jpg --out out [--model 1.3B|14B] [--chunks N]
import argparse, glob, os, time
import numpy as np, torch
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("--frames", required=True); ap.add_argument("--anchor"); ap.add_argument("--out", required=True)
ap.add_argument("--model", default="1.3B"); ap.add_argument("--chunks", type=int, default=0)  # 0 = all
ap.add_argument("--steps", type=int, default=30); ap.add_argument("--cfg", type=float, default=5.0)
ap.add_argument("--overlap", type=int, default=8); ap.add_argument("--seed", type=int, default=42)
a = ap.parse_args()
W, H, N = 832, 480, 81  # Wan 480p; frames per chunk must be 4k+1
PROMPT = ("Real footage, first-person smooth steady walk forward along a winding dirt hiking trail through a sunny "
          "meadow with olive trees, green grass, ferns and wildflowers, rocky cliffs in the distance, gentle breeze "
          "moving leaves and grass, natural afternoon sunlight turning to golden hour, photorealistic, highly detailed, "
          "sharp focus, 35mm film look")
NEG = ("people, person, hands, arms, legs, feet, shoes, phone, camera, gimbal, selfie stick, text, watermark, logo, "
       "cartoon, CGI, 3D render, video game, painting, illustration, blurry, low quality, jpeg artifacts, distorted, "
       "deformed, flicker, static image, cuts")

for fn, var in (("prompt.txt", "PROMPT"), ("negative.txt", "NEG")):
    fp = os.path.join(a.frames, fn)
    if os.path.exists(fp): globals()[var] = " ".join(open(fp).read().split())
T_START = time.time()
def log(msg): print(f"[{time.strftime('%H:%M:%S')} +{time.time() - T_START:.0f}s] {msg}", flush=True)
log(f"prompt: {PROMPT}")
src = sorted(glob.glob(os.path.join(a.frames, "f_*.jpg")))
os.makedirs(a.out, exist_ok=True); os.makedirs(a.out + "_depth", exist_ok=True)
T = len(src); log(f"{T} input frames")

# 1. Depth maps (near = bright, like VACE's depth annotator), one global range so they don't flicker frame to frame.
dpath = lambda i: os.path.join(a.out + "_depth", f"d_{i:04d}.png")
if not os.path.exists(dpath(T - 1)):
    from transformers import pipeline
    est = pipeline("depth-estimation", model="depth-anything/Depth-Anything-V2-Large-hf", device=0)
    raw = []
    for i in range(0, T, 16):
        for r in est([Image.open(p).convert("RGB") for p in src[i:i + 16]]):
            raw.append(r["predicted_depth"].squeeze().float().cpu().numpy())
    lo, hi = np.percentile(np.stack(raw), [1, 99])
    for i, d in enumerate(raw):
        d = np.clip((d - lo) / (hi - lo), 0, 1)
        Image.fromarray((d * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC).convert("RGB").save(dpath(i))
    del est, raw; torch.cuda.empty_cache()
    log("depth done")
depth = [Image.open(dpath(i)).convert("RGB") for i in range(T)]

# 2. Wan 2.1 VACE.
from diffusers import AutoencoderKLWan, WanVACEPipeline
from diffusers.schedulers.scheduling_unipc_multistep import UniPCMultistepScheduler
mid = f"Wan-AI/Wan2.1-VACE-{a.model}-diffusers"
vae = AutoencoderKLWan.from_pretrained(mid, subfolder="vae", torch_dtype=torch.float32)
pipe = WanVACEPipeline.from_pretrained(mid, vae=vae, torch_dtype=torch.bfloat16)
pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config, flow_shift=3.0)  # 3.0 for 480p
pipe.enable_model_cpu_offload()
log("model loaded")

opath = lambda i: os.path.join(a.out, f"o_{i:04d}.png")
black, white = Image.new("L", (W, H), 0), Image.new("L", (W, H), 255)  # mask: black = keep, white = generate
start, k = 0, 0
while start < T:
    s = start if k == 0 else start - a.overlap          # chunk covers frames s .. s+N-1
    n = N
    if s + n > T:                                        # short last chunk: smallest 4k+1 that fits
        n = T - s; n += (1 - n) % 4; s = T - n
    keep = (start - s) if k else (1 if a.anchor else 0)  # frames given as-is at the chunk start
    e = s + n
    if all(os.path.exists(opath(i)) for i in range(start, min(e, T))):
        log(f"chunk {k} already done")
    else:
        if k == 0 and a.anchor:
            given = [Image.open(a.anchor).convert("RGB").resize((W, H))]
        else:
            given = [Image.open(opath(i)).convert("RGB") for i in range(s, s + keep)]
        ctrl = [depth[min(i, T - 1)] for i in range(s + keep, e)]
        t0 = time.time()
        frames = pipe(video=given + ctrl, mask=[black] * keep + [white] * (n - keep), prompt=PROMPT,
                      negative_prompt=NEG, height=H, width=W, num_frames=n, num_inference_steps=a.steps,
                      guidance_scale=a.cfg, generator=torch.Generator("cpu").manual_seed(a.seed),
                      output_type="pil").frames[0]
        for j, im in enumerate(frames):
            i = s + j
            if start <= i < T:
                im.save(opath(i))
        log(f"chunk {k}: frames {start}-{min(e, T) - 1} ({n} frames, keep {keep}) in {time.time() - t0:.0f} s")
    start, k = e, k + 1
    if a.chunks and k >= a.chunks: break
log("ALL DONE")
