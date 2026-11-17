"""Step 2b: render the Wan VACE feed from car_street_anim.blend, 832x480 @16 fps (Wan 480p), with Workbench (fast on the phone):
  feed/depth/d_####.png  exact Blender depth as disparity (near = bright, like VACE's depth annotator), fixed range per shot
                         (no per-frame normalising = no flicker; shots are separate Wan chunks so ranges may differ per shot)
  feed/mask/m_####.png   car silhouette (white) on black: object coherence (car-only colour lock, reference crop)
One Workbench render per frame: Combined = mask (flat object colours), Z pass -> depth via the compositor.
FS=1 FE=960 ./run_headless.sh feed.py"""
import bpy, os

HERE = "/root/models/car-street"
OUT = HERE + "/feed"
bpy.ops.wm.open_mainfile(filepath=HERE + "/car_street_anim.blend")
sc = bpy.context.scene
FS, FE = int(os.environ.get("FS", 1)), int(os.environ.get("FE", 960))
STEP, PCT = int(os.environ.get("STEP", 1)), int(os.environ.get("PCT", 100))   # rough preview: STEP=4 PCT=50
OUT = os.environ.get("OUT", OUT)
RANGES = {"S1_Establish": (3.0, 150.0), "S2_Tracking": (2.0, 120.0), "S3_Orbit": (2.0, 100.0),
          "S4_Details": (0.5, 40.0), "S4b_Tail": (0.8, 40.0), "S5_Drive_off": (3.0, 140.0)}

# ENGINE=WORKBENCH (default, fast) needs the X display running (start-blender.sh): headless without X it hangs on EGL.
# ENGINE=CYCLES runs on the CPU with no display (slower). Only data passes matter: Z -> depth, car -> mask.
ENGINE = os.environ.get("ENGINE", "WORKBENCH")
for o in bpy.data.objects: o.pass_index = 0; o.color = (0, 0, 0, 1)
bpy.data.objects["CarSTL"].pass_index = 1; bpy.data.objects["CarSTL"].color = (1, 1, 1, 1)
sc.world.use_nodes = False; sc.world.color = (0, 0, 0)
if ENGINE == "CYCLES":
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"
    sc.cycles.samples = int(os.environ.get("SAMPLES", 1)); sc.cycles.use_denoising = False
    sc.cycles.use_adaptive_sampling = False; sc.cycles.max_bounces = 0
    sc.render.use_persistent_data = True
    bpy.context.view_layer.layer_collection.children["Lights"].exclude = True
    flat = bpy.data.materials.new("FeedFlat"); flat.use_nodes = True
    bpy.context.view_layer.material_override = flat
    sc.view_layers[0].use_pass_object_index = True
else:                                   # flat object colours: Combined = the mask (car white, rest black)
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading; sh.light = "FLAT"; sh.color_type = "OBJECT"
    for k in ("show_shadows", "show_cavity", "show_object_outline", "show_specular_highlight", "show_xray"):
        if hasattr(sh, k): setattr(sh, k, False)
    sc.display.render_aa = "8"
sc.view_settings.view_transform = "Standard"; sc.view_settings.look = "None"
RX, RY = map(int, os.environ.get("SIZE", "1056x480").split("x"))   # 2.2:1 = OnePlus 13R screen shape
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = RX, RY, PCT
sc.render.use_motion_blur = False
sc.view_layers[0].use_pass_z = True
sc.frame_start, sc.frame_end, sc.frame_step = FS, FE, STEP

sc.use_nodes = True
nt = sc.node_tree; nt.nodes.clear()
rl = nt.nodes.new("CompositorNodeRLayers")
comp = nt.nodes.new("CompositorNodeComposite")
inv = nt.nodes.new("CompositorNodeMath"); inv.operation = "DIVIDE"; inv.inputs[0].default_value = 1.0
mr = nt.nodes.new("CompositorNodeMapRange"); mr.use_clamp = True
mr.inputs["To Min"].default_value = 0.0; mr.inputs["To Max"].default_value = 1.0
nt.links.new(rl.outputs["Depth"], inv.inputs[1]); nt.links.new(inv.outputs[0], mr.inputs["Value"])


def fout(base, prefix, src):
    n = nt.nodes.new("CompositorNodeOutputFile"); n.base_path = base
    n.format.file_format = "PNG"; n.format.color_mode = "BW"; n.format.color_depth = "8"
    n.file_slots[0].path = prefix
    nt.links.new(src, n.inputs[0])
    return n


fout(OUT + "/depth/", "d_", mr.outputs[0])
if ENGINE == "CYCLES":
    idm = nt.nodes.new("CompositorNodeIDMask"); idm.index = 1; idm.use_antialiasing = True
    nt.links.new(rl.outputs["IndexOB"], idm.inputs[0]); fout(OUT + "/mask/", "m_", idm.outputs[0])
else:
    fout(OUT + "/mask/", "m_", rl.outputs["Image"])
nt.links.new(rl.outputs["Image"], comp.inputs["Image"])
# fixed disparity range per shot, keyed with constant interpolation at each marker
for m in sorted(sc.timeline_markers, key=lambda m: m.frame):
    near, far = RANGES[m.name]
    mr.inputs["From Min"].default_value = 1.0 / far; mr.inputs["From Max"].default_value = 1.0 / near
    mr.inputs["From Min"].keyframe_insert("default_value", frame=m.frame)
    mr.inputs["From Max"].keyframe_insert("default_value", frame=m.frame)
for fc in nt.animation_data.action.fcurves:
    for kp in fc.keyframe_points: kp.interpolation = "CONSTANT"
sc.render.filepath = OUT + "/_composite/c_"
sc.render.image_settings.file_format = "JPEG"
bpy.ops.render.render(animation=True)
print("FEED done", FS, FE)
