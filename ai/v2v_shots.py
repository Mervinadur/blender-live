# Runs ON a RunPod pod. Video-to-video: makes the Blender colour render of an animation look real with Wan 2.1 T2V
# (WanVideoToVideoPipeline), keeping the animation: every chunk STARTS FROM the rendered frames (SDEdit, --strength
# ~0.5), so layout, car model, colours, lights and camera moves come from Blender; Wan only adds realism.
# (car-street v1 used VACE from depth only: the user said it looked "too AI" and too dark, and the Blender model was lost.)
#  - shots are separate (cuts on chunk starts); inside a shot chunks overlap by OVERLAP frames and are cross-faded;
#  - colour: each chunk is pulled towards the Blender render's look (--cc-render, car mask and background separately, so
#    it can't go dark/neon), then matched to the previous chunk on the overlap frames (--cc) so joins don't jump;
#  - budget: steps auto-lower (never below --min-steps effective) so generation fits --budget-min.
#
#   python v2v_shots.py --feed in --out out [--shots S1,S2] [--steps 28] [--strength 0.5] [--size 960x432] [--budget-min 30]
# in/: render/frame_0001.jpg.. (Blender colour render), mask/m_0001.png.. (car), shots.json, prompt.txt, negative.txt
import argparse, json, os, time
import numpy as np, torch
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("--feed", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--shots", default=""); ap.add_argument("--model", default="1.3B")
ap.add_argument("--steps", type=int, default=28); ap.add_argument("--strength", type=float, default=0.5)
ap.add_argument("--cfg", type=float, default=5.0); ap.add_argument("--overlap", type=int, default=8)
ap.add_argument("--seed", type=int, default=42); ap.add_argument("--size", default="960x432")
ap.add_argument("--cc", type=float, default=0.8); ap.add_argument("--cc-render", type=float, default=0.6)
ap.add_argument("--budget-min", type=float, default=30.0); ap.add_argument("--min-steps", type=int, default=10)
ap.add_argument("--offload", action="store_true")
ap.add_argument("--sweep", default="")   # "0.5:0.5,0.65:0.35" = strength:cc_render variants, model loaded once -> o_s050_####.png
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
rimg = lambda f: Image.open(os.path.join(a.feed, "render", f"frame_{f:04d}.jpg")).convert("RGB").resize((W, H), Image.LANCZOS)
def mimg(f):   # subject mask; missing mask (e.g. robot-scene) = no subject region, whole frame matched as background
    p = os.path.join(a.feed, "mask", f"m_{f:04d}.png")
    return np.asarray(Image.open(p).convert("L").resize((W, H))) > 127 if os.path.exists(p) else np.zeros((H, W), bool)
PREFIX = "o_"
opath = lambda f: os.path.join(a.out, f"{PREFIX}{f:04d}.png")

# ---- colour: sRGB <-> CIELAB (D65), Reinhard mean/std transfer per region (same transform for a whole chunk) ----
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
    if not any(m.any() for m in masks): return None
    px = np.concatenate([l[m] for l, m in zip(labs, masks)])
    return None if len(px) < 500 else (px.mean(0), px.std(0) + 1e-3)
def transfer(labs, masks, src, dst, k):
    if src is None or dst is None or k <= 0: return labs
    scale = 1 + k * (dst[1] / src[1] - 1); shift = k * (dst[0] - src[0])
    out = []
    for l, m in zip(labs, masks):
        l = l.copy(); l[m] = (l[m] - src[0]) * scale + src[0] + shift; out.append(l)
    return out
def match(labs, cars, ref_labs, ref_cars, k, sel=None):
    """Match labs (car and background separately) to the stats of ref_labs; stats measured on frames `sel` only."""
    sel = sel if sel is not None else range(len(labs))
    L = [labs[i] for i in sel]; C = [cars[i] for i in sel]
    for region in (lambda c: c, lambda c: ~c):
        src = stats(L, [region(c) for c in C]); dst = stats(ref_labs, [region(c) for c in ref_cars])
        labs = transfer(labs, [region(c) for c in cars], src, dst, k)
        L = [labs[i] for i in sel]
    return labs

# ---- model ----
from diffusers import AutoencoderKLWan, WanVideoToVideoPipeline
from diffusers.schedulers.scheduling_unipc_multistep import UniPCMultistepScheduler
mid = f"Wan-AI/Wan2.1-T2V-{a.model}-Diffusers"
vae = AutoencoderKLWan.from_pretrained(mid, subfolder="vae", torch_dtype=torch.float32)
pipe = WanVideoToVideoPipeline.from_pretrained(mid, vae=vae, torch_dtype=torch.bfloat16)
pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config, flow_shift=3.0)
if a.offload: pipe.enable_model_cpu_offload()
else: pipe.to("cuda")
log(f"model loaded ({'offload' if a.offload else 'all on GPU'}), {W}x{H}, {a.steps} steps x strength {a.strength}")


def chunk_plan(f0, f1):
    out, start, k = [], f0, 0
    while start <= f1:
        s = start if k == 0 else start - a.overlap; n = N
        if s + n - 1 > f1:
            n = f1 - s + 1
            if k == 0: n -= (n - 1) % 4               # first chunk must not reach into the previous shot: shrink to 4k+1
            else: n += (1 - n) % 4; s = f1 - n + 1    # later chunks grow back into their own shot (more overlap)
        out.append((k, start, s, n)); start, k = s + n, k + 1
    return out


VARIANTS = [tuple(map(float, v.split(":"))) for v in a.sweep.split(",") if v] or [(a.strength, a.cc_render)]
BUDGET_ALL = a.budget_min
for a.strength, a.cc_render in VARIANTS:
    if a.sweep: PREFIX = f"o_s{round(a.strength * 100):03d}_"; a.budget_min = BUDGET_ALL / len(VARIANTS)
    log(f"== variant strength {a.strength} cc_render {a.cc_render} -> {PREFIX}####.png")
    plan = [(sh, c) for sh in todo for c in chunk_plan(sh["f0"], sh["f1"])]
    left = sum(1 for sh, (k, st, s, n) in plan if not all(os.path.exists(opath(f)) for f in range(st, s + n)))
    log(f"{left} chunks to generate, budget {a.budget_min:.0f} min")
    steps, sec_per_step, gen_time = a.steps, None, 0.0
    for sh, (k, start, s, n) in plan:
        e = s + n - 1
        if k == 0: log(f"shot {sh['name']} frames {sh['f0']}-{sh['f1']}")
        if all(os.path.exists(opath(f)) for f in range(start, e + 1)):
            log(f"  chunk {k} already done"); continue
        if sec_per_step:                                     # auto-fit the remaining chunks into the budget
            fit = int((a.budget_min * 60 - gen_time) / max(left, 1) / sec_per_step / a.strength)
            if fit < steps:
                steps = max(int(a.min_steps / a.strength + 0.5), fit); log(f"  auto-fit: {steps} steps for {left} chunks")
        frames = list(range(s, e + 1))
        src = [rimg(f) for f in frames]
        t0 = time.time()
        out = pipe(video=src, prompt=BASE + ", " + sh["prompt"], negative_prompt=NEG, height=H, width=W,
                   num_inference_steps=steps, strength=a.strength, guidance_scale=a.cfg,
                   generator=torch.Generator("cpu").manual_seed(a.seed), output_type="pil").frames[0]
        dt = time.time() - t0; gen_time += dt; left -= 1
        eff = max(1, int(steps * a.strength))
        sec_per_step = dt / eff if sec_per_step is None else 0.5 * sec_per_step + 0.5 * dt / eff
        labs = [to_lab(np.asarray(im)) for im in out[:n]]
        cars = [mimg(f) for f in frames]
        # 1. keep the Blender look (brightness/colour) per chunk: car and background separately
        labs = match(labs, cars, [to_lab(np.asarray(im)) for im in src], cars, a.cc_render)
        keep = start - s
        if keep > 0:
            # 2. match the previous chunk on the shared frames, then cross-fade them
            prev = [to_lab(np.asarray(Image.open(opath(f)).convert("RGB"))) for f in frames[:keep]]
            labs = match(labs, cars, prev, cars[:keep], a.cc, sel=range(keep))
            for i in range(keep):
                w = (i + 1) / (keep + 1)
                labs[i] = prev[i] * (1 - w) + labs[i] * w
        for i, f in enumerate(frames):
            Image.fromarray(to_rgb8(labs[i])).save(opath(f))
        log(f"  chunk {k}: frames {start}-{e} ({n} frames, overlap {keep}) in {dt:.0f} s, {steps} steps x {a.strength} "
            f"(gen total {gen_time / 60:.1f} min)")
    log(f"ALL DONE, generation {gen_time / 60:.1f} min")
