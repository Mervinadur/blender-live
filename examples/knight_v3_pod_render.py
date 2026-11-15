# Runs on the RunPod machine before rendering (PRE_PY=... ./render-remote.sh).
# The phone's Blender has no denoisers, so the denoiser is chosen here.
import bpy

for s in bpy.data.scenes:
    if s.render.engine != "CYCLES":
        continue
    cy = s.cycles
    cy.use_denoising = True
    for den in ("OPENIMAGEDENOISE", "OPTIX"):
        try:
            cy.denoiser = den
            break
        except TypeError:
            continue
    for attr, val in (("denoising_use_gpu", True), ("denoising_input_passes", "RGB_ALBEDO_NORMAL"),
                      ("denoising_prefilter", "ACCURATE"), ("denoising_quality", "HIGH")):
        try:
            setattr(cy, attr, val)
        except (AttributeError, TypeError) as e:
            print("denoise setting skipped:", attr, e)
    print("Cycles:", s.name, s.render.resolution_x, "x", s.render.resolution_y, "samples", cy.samples,
          "denoiser", cy.denoiser, "gpu denoise", getattr(cy, "denoising_use_gpu", None))
