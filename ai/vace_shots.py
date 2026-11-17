# Runs ON a RunPod pod. Turns a Blender depth + object-mask feed (rendered on the phone, no shading needed) into photoreal
# shots with Wan 2.1 VACE. Built from the nature-trail lessons:
#  - depth comes straight from Blender's Z pass (exact, no flicker, no Depth Anything);
#  - a shot = its own chunk run (cuts fall on chunk starts), so shots are independent and can go to different pods;
#  - object coherence: one car reference image (generated here, deterministic seed) is given to EVERY chunk via
#    VACE reference_images, and inside a shot each chunk continues from the last OVERLAP generated frames;
#  - colour correction (required since the nature trail went neon): every chunk after a shot's first is matched to that
#    shot's first chunk with a per-chunk Reinhard mean/std transfer in LAB, car (mask) and background separately, so
#    saturation/contrast can't grow chunk after chunk; the car is also pulled towards the reference car's colours so it
#    stays the same car across shots. Strengths --cc / --cc-car (0 = off).
#
#   python vace_shots.py --feed in --out out [--shots S1_Establish,S4_Details] [--steps 16] [--size 960x432] [--budget-min 30]
# in/: depth/d_0001.png.. mask/m_0001.png.. shots.json [{name,f0,f1,prompt}], prompt.txt, negative.txt, ref_frame.txt
import argparse, glob, json, os, time
import numpy as np, torch
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("--feed", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--shots", default="")                       # comma list; empty = all
ap.add_argument("--model", default="1.3B"); ap.add_argument("--steps", type=int, default=16)
ap.add_argument("--cfg", type=float, default=5.0); ap.add_argument("--overlap", type=int, default=8)
ap.add_argument("--seed", type=int, default=42); ap.add_argument("--size", default="960x432")   # 2.2:1 phone shape
ap.add_argument("--cc", type=float, default=0.8); ap.add_argument("--cc-car", type=float, default=0.5)
ap.add_argument("--budget-min", type=float, default=30.0)    # generation-time budget: steps auto-lower to fit it
ap.add_argument("--min-steps", type=int, default=12)
ap.add_argument("--offload", action="store_true")            # needed on 24 GB (4090: all-on-GPU OOMs at 81 frames)
a = ap.parse_args()
W, H = map(int, a.size.split("x")); N = 81
T_START = time.time()
def log(msg): print(f"[{time.strftime('%H:%M:%S')} +{time.time() - T_START:.0f}s] {msg}", flush=True)
rd = lambda f: " ".join(open(os.path.join(a.feed, f)).read().split())
BASE, NEG = rd("prompt.txt"), rd("negative.txt")
SHOTS = json.load(open(os.path.join(a.feed, "shots.json")))
want = [s for s in a.shots.split(",") if s]
todo = [s for s in SHOTS if not want or s["name"] in want]
os.makedirs(a.out, exist_ok=True)
dimg = lambda f: Image.open(os.path.join(a.feed, "depth", f"d_{f:04d}.png")).convert("RGB").resize((W, H), Image.BICUBIC)
mimg = lambda f: np.asarray(Image.open(os.path.join(a.feed, "mask", f"m_{f:04d}.png")).convert("L").resize((W, H))) > 127
opath = lambda f: os.path.join(a.out, f"o_{f:04d}.png")


# ---- colour: sRGB <-> CIELAB (D65) in numpy, Reinhard transfer per region ----
M1 = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]); M2 = np.linalg.inv(M1)
WP = np.array([0.95047, 1.0, 1.08883])
def to_lab(rgb8):
    c = rgb8.astype(np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ M1.T / WP
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)
def to_rgb8(lab):
    fy = (lab[..., 0] + 16) / 116; fx = fy + lab[..., 1] / 500; fz = fy - lab[..., 2] / 200
    f = np.stack([fx, fy, fz], -1)
    xyz = np.where(f ** 3 > 0.008856, f ** 3, (f - 16 / 116) / 7.787) * WP
    c = np.clip(xyz @ M2.T, 0, 1)
    c = np.where(c > 0.0031308, 1.055 * c ** (1 / 2.4) - 0.055, 12.92 * c)
    return (np.clip(c, 0, 1) * 255 + 0.5).astype(np.uint8)
def stats(labs, masks):
    px = np.concatenate([l[m] for l, m in zip(labs, masks)]) if any(m.any() for m in masks) else None
    return None if px is None or len(px) < 500 else (px.mean(0), px.std(0) + 1e-3)
def transfer(labs, masks, src, dst, k):
    """Same transform for every frame of the chunk (no flicker): (x - mu_s) * sd_d/sd_s + mu_d, blended by k."""
    if src is None or dst is None or k <= 0: return labs
    scale = 1 + k * (dst[1] / src[1] - 1); shift = k * (dst[0] - src[0])
    out = []
    for l, m in zip(labs, masks):
        l = l.copy(); l[m] = (l[m] - src[0]) * scale + src[0] + shift; out.append(l)
    return out


# ---- model ----
from diffusers import AutoencoderKLWan, WanVACEPipeline
from diffusers.schedulers.scheduling_unipc_multistep import UniPCMultistepScheduler
mid = f"Wan-AI/Wan2.1-VACE-{a.model}-diffusers"
vae = AutoencoderKLWan.from_pretrained(mid, subfolder="vae", torch_dtype=torch.float32)
pipe = WanVACEPipeline.from_pretrained(mid, vae=vae, torch_dtype=torch.bfloat16)
pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config, flow_shift=3.0)  # 3.0 for 480p
if a.offload: pipe.enable_model_cpu_offload()
else: pipe.to("cuda")
log(f"model loaded ({'offload' if a.offload else 'all on GPU'}), {W}x{H}, {a.steps} steps")
gen = lambda: torch.Generator("cpu").manual_seed(a.seed)
black, white = Image.new("L", (W, H), 0), Image.new("L", (W, H), 255)   # VACE mask: black = keep, white = generate

# ---- 1. car reference: one frame from the depth of a clear side view (same seed on every pod = same car) ----
REF_F = int(rd("ref_frame.txt"))
ref_png = os.path.join(a.out, "ref_car.png")
if not os.path.exists(ref_png):
    t0 = time.time()
    shot_of_ref = next(s for s in SHOTS if s["f0"] <= REF_F <= s["f1"])
    im = pipe(video=[dimg(REF_F)], mask=[white], prompt=BASE + ", " + shot_of_ref["prompt"], negative_prompt=NEG,
              height=H, width=W, num_frames=1, num_inference_steps=max(a.steps, 30), guidance_scale=a.cfg,
              generator=gen(), output_type="pil").frames[0][0]
    m = mimg(REF_F); arr = np.asarray(im).copy(); arr[~m] = 255                  # car on white, as VACE expects
    ys, xs = np.where(m)
    Image.fromarray(arr[ys.min():ys.max() + 1, xs.min():xs.max() + 1]).save(ref_png)
    im.save(os.path.join(a.out, "ref_full.png"))
    log(f"reference car made from frame {REF_F} in {time.time() - t0:.0f} s")
REF = Image.open(ref_png).convert("RGB")
ra = np.asarray(REF); REF_CAR = stats([to_lab(ra)], [~(ra.min(-1) > 245)])    # reference car colours (non-white px)

# ---- 2. shots ----
def chunk_plan(f0, f1):
    """Chunks of a shot as (start, s, n): first fresh, later ones continue from OVERLAP frames."""
    out, start, k = [], f0, 0
    while start <= f1:
        s = start if k == 0 else start - a.overlap; n = N
        if s + n - 1 > f1: n = f1 - s + 1; n += (1 - n) % 4; s = f1 - n + 1
        out.append((start, s, n)); start, k = s + n, k + 1
    return out
left = sum(1 for sh in todo for st, s, n in chunk_plan(sh["f0"], sh["f1"])
           if not all(os.path.exists(opath(f)) for f in range(st, s + n)))
log(f"{left} chunks to generate, budget {a.budget_min:.0f} min")
steps, sec_per_step = a.steps, None
gen_time = 0.0
for sh in todo:
    f0, f1, prompt = sh["f0"], sh["f1"], BASE + ", " + sh["prompt"]
    log(f"shot {sh['name']} frames {f0}-{f1}: {prompt}")
    start, k, ref_bg, ref_car = f0, 0, None, None
    while start <= f1:
        s = start if k == 0 else start - a.overlap
        n = N
        if s + n - 1 > f1:                                   # short last chunk: smallest 4k+1 that fits
            n = f1 - s + 1; n += (1 - n) % 4; s = f1 - n + 1
        keep = 0 if k == 0 else start - s
        e = s + n - 1
        frames_new = list(range(start, e + 1))
        if all(os.path.exists(opath(f)) for f in frames_new):
            log(f"  chunk {k} already done")
        else:
            given = [Image.open(opath(f)).convert("RGB") for f in range(s, s + keep)]
            ctrl = [dimg(f) for f in range(s + keep, e + 1)]
            if sec_per_step:                                 # auto-fit: steps that let the remaining chunks fit the budget
                fit = int((a.budget_min * 60 - gen_time) / max(left, 1) / sec_per_step)
                if fit < steps: steps = max(a.min_steps, fit); log(f"  auto-fit: {steps} steps for the remaining {left} chunks")
            t0 = time.time()
            out = pipe(video=given + ctrl, mask=[black] * keep + [white] * (n - keep), reference_images=[REF],
                       prompt=prompt, negative_prompt=NEG, height=H, width=W, num_frames=n,
                       num_inference_steps=steps, guidance_scale=a.cfg, generator=gen(), output_type="pil").frames[0]
            dt = time.time() - t0; gen_time += dt; left -= 1
            sec_per_step = dt / steps if sec_per_step is None else 0.5 * sec_per_step + 0.5 * dt / steps
            idx = [s + j for j in range(n) if s + j >= start]
            labs = [to_lab(np.asarray(out[f - s])) for f in idx]
            cars = [mimg(f) for f in idx]; bgs = [~c for c in cars]
            if k == 0:                                       # shot's look = its first chunk (car pulled to the reference)
                labs = transfer(labs, cars, stats(labs, cars), REF_CAR, a.cc_car)
                ref_bg, ref_car = stats(labs, bgs), stats(labs, cars)
            else:                                            # later chunks: lock to the shot's first chunk
                labs = transfer(labs, bgs, stats(labs, bgs), ref_bg, a.cc)
                labs = transfer(labs, cars, stats(labs, cars), ref_car or REF_CAR, a.cc)
            for f, l in zip(idx, labs):
                Image.fromarray(to_rgb8(l)).save(opath(f))
            log(f"  chunk {k}: frames {start}-{e} ({n} frames, keep {keep}) in {dt:.0f} s, {steps} steps (gen total {gen_time / 60:.1f} min)")
        if k == 0 and ref_bg is None and os.path.exists(opath(f0)):     # resumed: rebuild the shot's look from disk
            idx = [f for f in range(f0, min(f0 + N, f1 + 1)) if os.path.exists(opath(f))]
            labs = [to_lab(np.asarray(Image.open(opath(f)).convert("RGB"))) for f in idx]
            cars = [mimg(f) for f in idx]
            ref_bg, ref_car = stats(labs, [~c for c in cars]), stats(labs, cars)
        start, k = e + 1, k + 1
log(f"ALL DONE, generation {gen_time / 60:.1f} min")
