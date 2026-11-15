"""Nature trail: a 60 s walk along a meadow trail through trees, ending in a crane-up reveal of a cliff.
All assets are Poly Haven CC0 (fetch_assets.py). Run headless:
  blender -b --factory-startup --python /root/models/nature-trail/build.py
Saves /root/models/nature-trail/nature_trail.blend (EEVEE, 1280x720 phone-friendly, 24 fps, frames 1-1440, JPEG)."""
import bpy, math, os, random, glob
import numpy as np
import mathutils
from mathutils import Vector

HERE = "/root/models/nature-trail"
A = HERE + "/assets"
FPS, FRAMES = 24, 1440
rng = np.random.default_rng(7)
random.seed(7)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


# ---------- terrain + trail ----------
def path_x(y):
    return 4.0 * np.sin(y / 9.0) + 1.8 * np.sin(y / 4.3 + 1.0)


def height(x, y):
    h = 0.6 * np.sin(x / 11.0) * np.cos(y / 13.0) + 0.35 * np.sin(x / 5.3 + y / 7.1) + 0.15 * np.cos(x / 2.9 - y / 3.7)
    h += 0.04 * (x ** 2) / 40.0          # gentle valley: sides rise
    return h


PY = np.linspace(-45, 60, 3000)
PX = path_x(PY)


def trail_dist(x, y):
    x = np.atleast_1d(x); y = np.atleast_1d(y)
    d = np.sqrt((x[:, None] - PX[None, :]) ** 2 + (y[:, None] - PY[None, :]) ** 2)
    return d.min(axis=1)


def ground_z(x, y):
    return float(height(np.array([x]), np.array([y]))[0])


N, SIZE = 220, 150.0
xs = np.linspace(-SIZE / 2, SIZE / 2, N); ys = np.linspace(-SIZE / 2 + 10, SIZE / 2 + 10, N)
gx, gy = np.meshgrid(xs, ys)
gz = height(gx, gy)
verts = np.stack([gx, gy, gz], -1).reshape(-1, 3)
faces = [(j * N + i, j * N + i + 1, (j + 1) * N + i + 1, (j + 1) * N + i) for j in range(N - 1) for i in range(N - 1)]
me = bpy.data.meshes.new("Ground")
me.from_pydata(verts.tolist(), [], faces)
for p in me.polygons:
    p.use_smooth = True
ground = bpy.data.objects.new("Ground", me)
scene.collection.objects.link(ground)
# trail mask as a colour attribute (1 = dirt trail)
dist = np.concatenate([trail_dist(verts[k:k + 4000, 0], verts[k:k + 4000, 1]) for k in range(0, len(verts), 4000)])
mask = np.clip(1.0 - (dist - 0.7) / 0.9, 0, 1)
ca = me.color_attributes.new("trail", "FLOAT_COLOR", "POINT")
ca.data.foreach_set("color", np.repeat(mask, 4).astype(np.float32))
uv = me.uv_layers.new(name="UVMap")
loop_v = np.zeros(len(me.loops), dtype=np.int32); me.loops.foreach_get("vertex_index", loop_v)
uvs = (verts[loop_v, :2] / 3.0).astype(np.float32)          # texture repeats every 3 m
uv.data.foreach_set("uv", uvs.ravel())

gm = bpy.data.materials.new("GroundMat"); gm.use_nodes = True
nt = gm.node_tree; bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
T = A + "/textures/forest_ground_04/forest_ground_04_"
def img(path, data=False):
    n = nt.nodes.new("ShaderNodeTexImage"); n.image = bpy.data.images.load(path)
    if data: n.image.colorspace_settings.name = "Non-Color"
    return n
dif = img(T + "diff_1k.jpg"); rough = img(T + "rough_1k.jpg", True); nor = img(T + "nor_gl_1k.jpg", True)
attr = nt.nodes.new("ShaderNodeAttribute"); attr.attribute_name = "trail"
green = nt.nodes.new("ShaderNodeMix"); green.data_type = "RGBA"; green.blend_type = "MULTIPLY"
green.inputs["Factor"].default_value = 1.0; green.inputs[7].default_value = (0.32, 0.55, 0.12, 1)
nt.links.new(dif.outputs["Color"], green.inputs[6])
mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
nt.links.new(attr.outputs["Fac"], mix.inputs["Factor"])
nt.links.new(green.outputs[2], mix.inputs[6]); nt.links.new(dif.outputs["Color"], mix.inputs[7])
nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
nt.links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])
nm = nt.nodes.new("ShaderNodeNormalMap"); nt.links.new(nor.outputs["Color"], nm.inputs["Color"])
nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
me.materials.append(gm)


# ---------- assets ----------
lib = bpy.data.collections.new("AssetLib"); scene.collection.children.link(lib)
bpy.context.view_layer.layer_collection.children["AssetLib"].exclude = True
ASSETS = {}
for f in sorted(glob.glob(A + "/models/*/*.gltf")):
    name = os.path.basename(os.path.dirname(f))
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=f)
    new = [o for o in bpy.data.objects if o not in before]
    parts = []
    for o in new:
        for c in o.users_collection: c.objects.unlink(o)
        if o.type != "MESH":
            continue
        o.parent = None
        # each part becomes its own collection with the part centred at the origin (x,y) and base at z=0
        co = np.array([o.matrix_world @ Vector(c) for c in o.bound_box])
        col = bpy.data.collections.new(o.name); lib.children.link(col); col.objects.link(o)
        col.instance_offset = (co[:, 0].mean(), co[:, 1].mean(), co[:, 2].min() + 0.01)
        parts.append(col)
    for o in new:
        if o.type != "MESH": bpy.data.objects.remove(o)
    ASSETS[name] = parts
print("ASSETS", {k: len(v) for k, v in ASSETS.items()})
# phone-friendly: thin out the heaviest scanned meshes (smaller upload, faster render)
DECIMATE = {"island_tree_01": 0.4, "island_tree_02": 0.5, "pine_sapling_small": 0.3, "coast_rocks_05": 0.1, "boulder_01": 0.4}
for n, r in DECIMATE.items():
    for col in ASSETS[n]:
        for o in col.objects:
            m = o.modifiers.new("dec", "DECIMATE"); m.ratio = r
            scene.collection.objects.link(o)          # excluded collections aren't evaluated
            dg = bpy.context.evaluated_depsgraph_get(); dg.update()
            new = bpy.data.meshes.new_from_object(o.evaluated_get(dg)); old = o.data
            o.modifiers.clear(); o.data = new; bpy.data.meshes.remove(old)
            scene.collection.objects.unlink(o)
            print("DECIMATED", o.name, len(new.polygons))

world_col = bpy.data.collections.new("Nature"); scene.collection.children.link(world_col)


def place(col, x, y, scale, rotz, sink=0.0, wind=0.0):
    e = bpy.data.objects.new(col.name + "_i", None)
    e.instance_type = "COLLECTION"; e.instance_collection = col
    e.location = (x, y, ground_z(x, y) - sink)
    e.rotation_euler = (0, 0, rotz); e.scale = (scale,) * 3
    e.hide_select = True
    world_col.objects.link(e)
    if wind > 0:   # slow sway from the base
        for axis in (0, 1):
            fc = e.driver_add("rotation_euler", axis) if False else None
            e.keyframe_insert("rotation_euler", index=axis, frame=1)
            fcu = e.animation_data.action.fcurves.find("rotation_euler", index=axis)
            m = fcu.modifiers.new("NOISE"); m.scale = 70 + 30 * random.random(); m.strength = wind
            m.phase = random.random() * 100; m.blend_type = "ADD"
    return e


def scatter(names, count, dmin, dmax, smin, smax, ymin=-50, ymax=70, xmax=60, spacing=0.0, wind=0.0, taken=None):
    cols = [c for n in names for c in ASSETS[n]]
    pts = []
    tries = 0
    while len(pts) < count and tries < count * 60:
        tries += 1
        x = rng.uniform(-xmax, xmax); y = rng.uniform(ymin, ymax)
        d = trail_dist(x, y)[0]
        if not (dmin <= d <= dmax): continue
        if taken is not None and spacing > 0 and any((x - a) ** 2 + (y - b) ** 2 < spacing ** 2 for a, b in taken): continue
        if taken is not None: taken.append((x, y))
        pts.append((x, y))
        place(random.choice(cols), x, y, rng.uniform(smin, smax), rng.uniform(0, 2 * math.pi), wind=wind)
    return pts


trees = []
scatter(["island_tree_01", "island_tree_02"], 70, 3.5, 40, 1.4, 2.4, spacing=4.5, wind=0.012, taken=trees)
scatter(["pine_sapling_small"], 40, 2.2, 25, 1.0, 1.8, spacing=2.5, taken=trees)
scatter(["boulder_01"], 18, 2.0, 30, 0.6, 1.6, spacing=3.0, taken=trees)
scatter(["coast_rocks_05"], 5, 6, 30, 0.6, 1.0, spacing=6, taken=trees)
scatter(["grass_medium_02"], 1800, 0.9, 30, 0.8, 1.6, ymin=-40, ymax=58, xmax=32)
scatter(["fern_02"], 500, 1.6, 25, 0.6, 1.2, ymin=-40, ymax=58, xmax=30)
scatter(["celandine_01", "dandelion_01", "periwinkle_plant"], 900, 1.0, 18, 0.9, 1.5, ymin=-40, ymax=58, xmax=25)
# a fallen trunk beside the trail, and the cliff at the end
yt = -8.0; place(ASSETS["dead_tree_trunk_02"][0], float(path_x(yt)) + 2.4, yt, 1.3, 0.4, sink=0.15)
CLIFF = (float(path_x(52.0)), 58.0)
for k, (dx, dy, s, r) in enumerate([(0, 0, 2.6, 0.0), (-14, -3, 2.0, 1.2), (13, -2, 2.2, -1.0)]):
    place(ASSETS["mountainside"][0], CLIFF[0] + dx, CLIFF[1] + dy, s, r, sink=0.6)


# ---------- light: sun from late afternoon to golden hour, forest HDRI ----------
world = bpy.data.worlds.new("World"); scene.world = world; world.use_nodes = True
wn = world.node_tree; bg = next(n for n in wn.nodes if n.type == "BACKGROUND")
env = wn.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(A + "/hdri/forest_slope_2k.hdr")
wn.links.new(env.outputs["Color"], bg.inputs["Color"])
bg.inputs["Strength"].default_value = 0.8
bg.inputs["Strength"].keyframe_insert("default_value", frame=1)
bg.inputs["Strength"].default_value = 0.45
bg.inputs["Strength"].keyframe_insert("default_value", frame=FRAMES)

sd = bpy.data.lights.new("Sun", "SUN"); sd.angle = math.radians(1.5)
sun = bpy.data.objects.new("Sun", sd); scene.collection.objects.link(sun)
for f, elev, az, power, col in [(1, 48, 200, 4.5, (1.0, 0.96, 0.9)), (FRAMES, 14, 230, 3.2, (1.0, 0.72, 0.45))]:
    sun.rotation_euler = (math.radians(90 - elev), 0, math.radians(az)); sun.keyframe_insert("rotation_euler", frame=f)
    sd.energy = power; sd.keyframe_insert("energy", frame=f)
    sd.color = col; sd.keyframe_insert("color", frame=f)


# ---------- camera: walk the trail (0-50 s), then crane up to reveal the cliff (50-60 s) ----------
cd = bpy.data.cameras.new("Cam"); cd.lens = 28; cd.dof.use_dof = False
cam = bpy.data.objects.new("Cam", cd); scene.collection.objects.link(cam); scene.camera = cam
target = bpy.data.objects.new("CamTarget", None); scene.collection.objects.link(target)
tc = cam.constraints.new("TRACK_TO"); tc.target = target; tc.track_axis = "TRACK_NEGATIVE_Z"; tc.up_axis = "UP_Y"
WALK_END = 1200
Y0, Y1 = -34.0, 30.0
for f in range(1, FRAMES + 1, 12):
    if f <= WALK_END:
        u = (f - 1) / (WALK_END - 1)
        u = u * u * (3 - 2 * u) * 0.15 + u * 0.85          # ease in/out a little
        y = Y0 + (Y1 - Y0) * u
        x = float(path_x(y)); z = ground_z(x, y) + 1.65 + 0.03 * math.sin(f / 9.0)
        ya = y + 5.0; xa = float(path_x(ya)); za = ground_z(xa, ya) + 1.35
    else:
        u = (f - WALK_END) / (FRAMES - WALK_END); s = u * u * (3 - 2 * u)
        y = Y1 + 6.0 * s; x = float(path_x(y)); z = ground_z(x, y) + 1.65 + 8.0 * s
        ya0 = Y1 + 5.0; a0 = Vector((float(path_x(ya0)), ya0, ground_z(float(path_x(ya0)), ya0) + 1.35))
        a1 = Vector((CLIFF[0], CLIFF[1] - 4, 9.0))
        xa, ya, za = a0.lerp(a1, s)
    cam.location = (x, y, z); cam.keyframe_insert("location", frame=f)
    target.location = (xa, ya, za); target.keyframe_insert("location", frame=f)


# ---------- render settings ----------
for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try:
        scene.render.engine = eng; break
    except TypeError:
        pass
ee = scene.eevee
ee.taa_render_samples = 16
for k, v in {"use_shadows": True, "use_raytracing": False, "use_gtao": True, "use_volumetric_shadows": True,
             "shadow_ray_count": 2, "shadow_step_count": 8, "fast_gi_method": "GLOBAL_ILLUMINATION"}.items():
    try: setattr(ee, k, v)
    except Exception as ex: print("eevee setting", k, ex)
scene.render.fps = FPS; scene.frame_start = 1; scene.frame_end = FRAMES
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1280, 720, 100
scene.render.image_settings.file_format = "JPEG"; scene.render.image_settings.quality = 90
scene.view_settings.view_transform = "AgX"
try: scene.view_settings.look = "AgX - Medium High Contrast"
except TypeError: pass
# (no world-volume haze: in an open world it absorbs all sky/sun light and renders black)

# leaf materials: make sure alpha cards render as cutouts/hashed in EEVEE
for m in bpy.data.materials:
    if hasattr(m, "surface_render_method"): m.surface_render_method = "DITHERED"

bpy.ops.wm.save_as_mainfile(filepath=HERE + "/nature_trail.blend", compress=True)
print("SAVED objects", len(bpy.data.objects))
