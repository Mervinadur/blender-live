"""Car street: a 60 s night-street car video. Step 1 = scene set-up (this file): street set, hero car, lights,
shot cameras + markers, render settings. Animation is the next step.
Street set = Poly Haven CC0 assets (fetch_assets.py); the hero car is built here from code (Poly Haven has no cars).
Run headless:  ./run_headless.sh build.py   (Termux)  ->  saves /root/models/car-street/car_street.blend
Layout: street runs along +Y (y -60..180), road x -4..4, sidewalks to |x| 7, buildings beyond. Car drives +Y in the
right lane (x = +1.75). Car forward = +Y, origin on the ground between the axles."""
import bpy, math, os, random
import numpy as np
from mathutils import Vector

HERE = "/root/models/car-street"
A = HERE + "/assets"
FPS, FRAMES = 24, 1440
Y0, Y1 = -60.0, 180.0              # street extent
ROAD, WALK = 4.0, 7.0              # road half-width, sidewalk outer edge
KERB = 0.15
LANE_X = 1.75
HERO_Y = 92.0                      # where the car stops under a lamp (shot 3)
random.seed(11)
rng = np.random.default_rng(11)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def col_new(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or scene.collection).children.link(c)
    return c


SET = col_new("StreetSet")
PROPS = col_new("Props")
CAR = col_new("HeroCar")
CARP = col_new("HeroCar_Procedural")   # code-built car: backup, excluded (user supplied car.stl)
LIGHTS = col_new("Lights")
CAMS = col_new("Cameras")


# ---------- materials ----------
def principled(name, color=(0.8, 0.8, 0.8), rough=0.5, metal=0.0, **extra):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    for k, v in extra.items():
        sock = b.inputs.get(k)
        if sock is not None:
            sock.default_value = v
        else:
            print("no input", k)
    m.diffuse_color = (*color, 1)
    return m


def emissive(name, color, strength):
    m = principled(name, color=(0.02, 0.02, 0.02), rough=0.3)
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Emission Color"].default_value = (*color, 1)
    b.inputs["Emission Strength"].default_value = strength
    m.diffuse_color = (*color, 1)
    return m


def textured(name, tex, res, scale, rough_mul=1.0, tint=None):
    """Image-textured material using Object coordinates (metres) with box projection: no UVs needed."""
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; b = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tc = nt.nodes.new("ShaderNodeTexCoord"); mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / scale,) * 3
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    base = f"{A}/textures/{tex}/{tex}_"

    def img(kind, data):
        path = next((base + f"{kind}_{res}.{e}" for e in ("jpg", "png") if os.path.exists(base + f"{kind}_{res}.{e}")), None)
        if not path:
            return None
        n = nt.nodes.new("ShaderNodeTexImage"); n.image = bpy.data.images.load(path)
        n.projection = "BOX"; n.projection_blend = 0.2
        if data: n.image.colorspace_settings.name = "Non-Color"
        nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
        return n
    d = img("diff", False); r = img("rough", True); nm = img("nor_gl", True)
    if d:
        out = d.outputs["Color"]
        if tint:
            mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0; mix.inputs[7].default_value = (*tint, 1)
            nt.links.new(out, mix.inputs[6]); out = mix.outputs[2]
        nt.links.new(out, b.inputs["Base Color"])
    if r:
        mth = nt.nodes.new("ShaderNodeMath"); mth.operation = "MULTIPLY"; mth.inputs[1].default_value = rough_mul
        nt.links.new(r.outputs["Color"], mth.inputs[0]); nt.links.new(mth.outputs[0], b.inputs["Roughness"])
    if nm:
        n = nt.nodes.new("ShaderNodeNormalMap"); nt.links.new(nm.outputs["Color"], n.inputs["Color"])
        nt.links.new(n.outputs["Normal"], b.inputs["Normal"])
    return m


M_ROAD = textured("Asphalt_wet", "asphalt_02", "2k", 4.0, rough_mul=0.35, tint=(0.55, 0.55, 0.58))  # damp road = reflections
M_WALK = textured("Sidewalk", "concrete_pavement", "1k", 2.0)
M_BRICK = textured("Brick", "brick_wall_02", "1k", 2.5)
M_CONC = textured("Concrete", "concrete_wall_008", "1k", 3.0)
M_KERB = principled("Kerb", (0.45, 0.45, 0.43), 0.7)
M_PAINT = principled("RoadPaint", (0.85, 0.85, 0.8), 0.45)
M_YELLOW = principled("RoadPaintYellow", (0.85, 0.6, 0.08), 0.45)
M_GROUND = principled("Ground", (0.05, 0.05, 0.05), 0.9)
M_WIN_LIT = emissive("WindowLit", (1.0, 0.72, 0.42), 4.0)
M_WIN_COOL = emissive("WindowLitCool", (0.7, 0.85, 1.0), 3.0)
M_WIN_DARK = principled("WindowDark", (0.01, 0.012, 0.015), 0.08)


def box(name, x0, x1, y0, y1, z0, z1, mat, coll):
    me = bpy.data.meshes.new(name)
    v = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    me.from_pydata(v, [], f); me.materials.append(mat)
    o = bpy.data.objects.new(name, me); coll.objects.link(o)
    return o


# ---------- street: road, kerbs, sidewalks, markings ----------
box("Road", -ROAD, ROAD, Y0, Y1, -0.05, 0.0, M_ROAD, SET)
for s in (-1, 1):
    box(f"Kerb_{s:+d}", s * ROAD, s * (ROAD + 0.22), Y0, Y1, -0.05, KERB, M_KERB, SET)
    box(f"Sidewalk_{s:+d}", s * (ROAD + 0.22), s * WALK, Y0, Y1, -0.05, KERB - 0.01, M_WALK, SET)
    box(f"EdgeLine_{s:+d}", s * 3.55, s * 3.7, Y0, Y1, 0.0, 0.004, M_PAINT, SET)
box("GroundFar", -200, 200, -200, 400, -0.2, -0.06, M_GROUND, SET)
# dashed centre line (one mesh)
me = bpy.data.meshes.new("CentreLine"); v, f = [], []
for y in np.arange(Y0, Y1, 6.0):
    i = len(v); v += [(-0.07, y, 0.004), (0.07, y, 0.004), (0.07, y + 3.0, 0.004), (-0.07, y + 3.0, 0.004)]; f.append((i, i + 1, i + 2, i + 3))
me.from_pydata(v, [], f); me.materials.append(M_YELLOW)
SET.objects.link(bpy.data.objects.new("CentreLine", me))
# stop line + crosswalk near the end of the street
for k in range(8):
    x = -3.4 + k * 0.9
    box(f"Zebra_{k}", x, x + 0.5, 150.0, 153.5, 0.0, 0.004, M_PAINT, SET)


# ---------- buildings with lit windows ----------
def facade_windows(name, side, y0, y1, height, coll):
    """Window quads on the street-facing wall. side=-1: left block (wall at x=-WALK faces +X)."""
    x = side * (WALK - 0.02)
    me = bpy.data.meshes.new(name); v, f, mi = [], [], []
    floors = int((height - 4.0) // 3.2)
    for fl in range(floors):
        z = 4.0 + fl * 3.2
        for y in np.arange(y0 + 1.6, y1 - 1.6, 3.0):
            i = len(v)
            v += [(x, y, z), (x, y + 1.3, z), (x, y + 1.3, z + 1.7), (x, y, z + 1.7)]
            f.append((i, i + 1, i + 2, i + 3) if side > 0 else (i, i + 3, i + 2, i + 1))
            r = random.random()
            mi.append(0 if r < 0.22 else (1 if r < 0.30 else 2))
    if not f:
        return
    me.from_pydata(v, [], f)
    for m in (M_WIN_LIT, M_WIN_COOL, M_WIN_DARK):
        me.materials.append(m)
    for p, k in zip(me.polygons, mi):
        p.material_index = k
    coll.objects.link(bpy.data.objects.new(name, me))


BUILD = col_new("Buildings", SET)
LOT = (38.0, 58.0)                 # empty fenced lot on the left side (chainlink fence)
DOORS = []                          # (x, y, side) ground-floor doors -> roller shutters + wall lamps
for side in (-1, 1):
    y = Y0
    n = 0
    while y < Y1:
        length = random.uniform(12, 26)
        y1 = min(y + length, Y1)
        if side < 0 and y < LOT[1] and y1 > LOT[0]:     # leave the lot open
            if y < LOT[0]:
                y1 = LOT[0]
            else:
                y = LOT[1]; continue
        h = random.uniform(7, 16)
        mat = M_BRICK if n % 2 == 0 else M_CONC
        xa, xb = sorted((side * WALK, side * (WALK + random.uniform(10, 16))))
        box(f"Bldg_{side:+d}_{n}", xa, xb, y + 0.15, y1 - 0.15, -0.05, h, mat, BUILD)
        facade_windows(f"Windows_{side:+d}_{n}", side, y + 0.15, y1 - 0.15, h, BUILD)
        if y1 - y > 8:
            DOORS.append((side * (WALK - 0.01), y + (y1 - y) * random.uniform(0.3, 0.7), side))
        y = y1; n += 1


# ---------- Poly Haven assets as instanced groups ----------
LIB = col_new("AssetLib")
bpy.context.view_layer.layer_collection.children["AssetLib"].exclude = True
GROUPS = {   # group name: (asset folder, part-name filter)
    "lamp_post": ("street_lamp_01", lambda n: True),
    "wall_lamp": ("street_lamp_02", lambda n: True),
    "hydrant": ("fire_hydrant", lambda n: "aged" not in n),
    "barrier": ("concrete_road_barrier", lambda n: True),
    "utility_box": ("utility_box_01", lambda n: True),
    "manhole": ("water_manhole_cover", lambda n: True),
    "shutter": ("rollershutter_door", lambda n: "graffiti" not in n),
    "shutter_graffiti": ("rollershutter_door", lambda n: "graffiti" in n),
    "fence_panel": ("modular_chainlink_fence", lambda n: n in ("modular_chainlink_fence_double", "modular_chainlink_fence_post")),
    "power_pole": ("modular_electricity_poles", lambda n: n.startswith("preset_01_")),
    "tyre": ("old_tyre", lambda n: True),
    "covered_car": ("covered_car", lambda n: True),
    "bench": ("modular_street_seating", lambda n: n in ("seat", "seat_back", "legs_single", "legs_double", "back_support_l",
                                                       "back_support_r", "crossbar", "arm_rest_01", "suspended_support_01")),
    "barrel": ("Barrel_01", lambda n: True),
    "box": ("cardboard_box_01", lambda n: True),
    "trashbag": ("trashbag", lambda n: True),
}
IMPORTED = {}
for folder in sorted({g[0] for g in GROUPS.values()}):
    gl = next(f for f in os.listdir(f"{A}/models/{folder}") if f.endswith(".gltf"))
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=f"{A}/models/{folder}/{gl}")
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        if o.type == "MESH":
            mw = o.matrix_world.copy(); o.parent = None; o.matrix_world = mw
        for c in list(o.users_collection): c.objects.unlink(o)
    for o in new:
        if o.type != "MESH": bpy.data.objects.remove(o)
    IMPORTED[folder] = [o for o in new if o.name in bpy.data.objects]
G = {}
for g, (folder, keep) in GROUPS.items():
    objs = [o for o in IMPORTED[folder] if keep(o.name.split(".")[0])]
    c = bpy.data.collections.new("PH_" + g); LIB.children.link(c)
    for o in objs:
        c.objects.link(o)
    co = np.array([o.matrix_world @ Vector(b) for o in objs for b in o.bound_box])
    c.instance_offset = (co[:, 0].mean(), co[:, 1].mean(), co[:, 2].min())
    G[g] = (c, co.max(0) - co.min(0))
print("GROUPS", {k: [round(float(x), 2) for x in v[1]] for k, v in G.items()})


def place(g, x, y, z=KERB - 0.01, rotz=0.0, s=1.0, coll=PROPS):
    e = bpy.data.objects.new(g + "_i", None)
    e.instance_type = "COLLECTION"; e.instance_collection = G[g][0]
    e.location = (x, y, z); e.rotation_euler = (0, 0, rotz); e.scale = (s,) * 3
    e.hide_select = True
    coll.objects.link(e)
    return e


# street lamps both sides, staggered, + a real light at each head
def warm_light(name, loc, power, kind="SPOT", size=0.25, spot=math.radians(120), color=(1.0, 0.78, 0.5)):
    ld = bpy.data.lights.new(name, kind); ld.energy = power; ld.color = color
    ld.shadow_soft_size = size
    if kind == "SPOT":
        ld.spot_size = spot; ld.spot_blend = 0.6
    o = bpy.data.objects.new(name, ld); o.location = loc; LIGHTS.objects.link(o)
    return o


LAMP_H = float(G["lamp_post"][1][2])
lamp_ys = []
for side, start in ((1, -50.0), (-1, -41.0)):
    for y in np.arange(start, Y1 - 5, 18.0):
        if side < 0 and LOT[0] - 1 < y < LOT[1] + 1:
            continue
        if side > 0 and abs(y - (HERO_Y + 1.0)) < 9.0:      # the hero lamp stands here (was doubled 1 m apart)
            continue
        x = side * (ROAD + 0.65)
        place("lamp_post", x, y, rotz=0.0)
        warm_light(f"LampLight_{side:+d}_{int(y)}", (x, y, KERB + LAMP_H - 0.35), 900)
        lamp_ys.append((side, float(y)))
# a lamp exactly at the hero mark (right side) so the car stops in a pool of light
place("lamp_post", ROAD + 0.65, HERO_Y + 1.0)
warm_light("LampLight_hero", (ROAD + 0.65, HERO_Y + 1.0, KERB + LAMP_H - 0.35), 1400)

# roller shutters + wall lamps at ground-floor doors
for k, (x, y, side) in enumerate(DOORS):
    rot = -side * math.pi / 2           # model faces -Y (back at y=0): turn it to face the street
    place("shutter_graffiti" if k % 3 == 0 else "shutter", x + side * 0.0, y, z=KERB - 0.01, rotz=rot, s=1.6)
    place("wall_lamp", x, y, z=3.4, rotz=rot)
    warm_light(f"WallLight_{k}", (x - side * 0.6, y, 3.3), 250, size=0.1, color=(1.0, 0.85, 0.65))

# fenced lot on the left (fence along the sidewalk edge, facing the street)
for y in np.arange(LOT[0], LOT[1], 1.92):
    place("fence_panel", -(WALK - 0.3), y + 0.96, rotz=math.pi / 2)
place("tyre", -9.0, 44.0, z=0.3, rotz=0.3)
place("tyre", -9.4, 44.6, z=0.3, rotz=1.2)
place("barrel", -10.0, 50.0, z=0.0)
place("barrel", -10.6, 50.5, z=0.0)

# power poles, hydrants, boxes, benches, bins, manholes
for y in (-20.0, 22.0, 70.0, 118.0, 160.0):
    place("power_pole", -(ROAD + 1.4), y, rotz=math.pi / 2)
for x, y in ((ROAD + 0.9, 14.0), (-(ROAD + 0.9), 83.0), (ROAD + 0.9, 133.0)):
    place("hydrant", x, y, rotz=random.uniform(0, 6.28))
for x, y in ((ROAD + 2.4, 30.0), (-(WALK - 0.5), 100.0), (WALK - 0.5, 60.0)):
    place("utility_box", x, y, rotz=math.pi / 2)
place("bench", WALK - 0.6, 75.0, rotz=math.pi / 2)
place("bench", -(WALK - 0.6), 124.0, rotz=-math.pi / 2)
for x, y in ((WALK - 0.5, 42.0), (WALK - 0.8, 42.6), (-(WALK - 0.5), 108.0)):
    place("trashbag", x, y, rotz=random.uniform(0, 6.28))
place("box", WALK - 0.6, 43.4, rotz=0.4)
for y in (8.0, 64.0, 112.0):
    place("manhole", -LANE_X, y, z=0.0)
# road closed at the far end: barriers across the road after the crosswalk
for x in np.arange(-3.2, 3.6, 1.6):
    place("barrier", float(x), 168.0, z=0.0)
# a parked covered car on the left kerb (contrast with the hero car)
place("covered_car", -(ROAD - 1.1), 101.0, z=0.0, rotz=math.pi)


# ---------- hero car (built from code) ----------
def interp(keys, y):
    ks = np.array(keys); return float(np.interp(y, ks[:, 0], ks[:, 1]))


def loft(name, ys, section, mat, coll):
    """ys: stations along the car; section(y) -> list of (x, z) closed loop (same count each)."""
    v, f = [], []
    rings = [section(y) for y in ys]
    K = len(rings[0])
    for y, ring in zip(ys, rings):
        v += [(x, y, z) for x, z in ring]
    for i in range(len(ys) - 1):
        for k in range(K):
            a = i * K + k; b = i * K + (k + 1) % K
            f.append((a, b, b + K, a + K))
    f.append(tuple(range(K))[::-1]); f.append(tuple(range((len(ys) - 1) * K, len(ys) * K)))
    me = bpy.data.meshes.new(name); me.from_pydata(v, [], f); me.materials.append(mat)
    for p in me.polygons: p.use_smooth = True
    o = bpy.data.objects.new(name, me); coll.objects.link(o)
    return o


def superellipse(cx, cz, ax, az, n, K, x_scale=None):
    pts = []
    for k in range(K):
        t = 2 * math.pi * k / K
        c, s = math.cos(t), math.sin(t)
        x = ax * math.copysign(abs(c) ** (2 / n), c)
        z = cz + az * math.copysign(abs(s) ** (2 / n), s)
        if x_scale: x *= x_scale((z - (cz - az)) / (2 * az))
        pts.append((cx + x, z))
    return pts


M_CARPAINT = principled("CarPaint", (0.55, 0.018, 0.012), 0.28, 0.5, **{"Coat Weight": 1.0, "Coat Roughness": 0.03})
M_GLASS = principled("CarGlass", (0.005, 0.006, 0.008), 0.03, 0.0, **{"Coat Weight": 1.0})
M_TRIM = principled("BlackTrim", (0.01, 0.01, 0.01), 0.35)
M_TYRE = principled("Tyre", (0.015, 0.015, 0.015), 0.85)
M_RIM = principled("Rim", (0.75, 0.75, 0.78), 0.18, 1.0)
M_BRAKE = principled("BrakeCaliper", (0.9, 0.55, 0.02), 0.35)
M_HEAD = emissive("Headlight", (0.85, 0.92, 1.0), 6.0)      # 25 blew out the whole front
M_TAIL = emissive("Taillight", (1.0, 0.02, 0.01), 12.0)

root = bpy.data.objects.new("Car", None); root.empty_display_type = "ARROWS"; CAR.objects.link(root)  # root stays in HeroCar
L2, WB, TRACK, WR = 2.25, 1.38, 0.82, 0.34     # half length, half wheelbase, half track, wheel radius
TOP = [(-2.25, 0.78), (-2.12, 0.92), (-1.7, 0.98), (-1.2, 0.97), (0.6, 0.93), (1.5, 0.84), (2.05, 0.74), (2.25, 0.6)]
BOT = [(-2.25, 0.34), (-1.9, 0.24), (1.9, 0.22), (2.25, 0.3)]


def body_section(y):
    zt, zb = interp(TOP, y), interp(BOT, y)
    w = 0.95 * (1 - 0.22 * max(0.0, (abs(y) - 1.85) / 0.4) ** 2)
    return superellipse(0, (zt + zb) / 2, w, (zt - zb) / 2, 4.5, 36, x_scale=lambda u: 1 - 0.07 * max(0, u - 0.6) / 0.4)


body = loft("CarBody", np.linspace(-L2, L2, 48), body_section, M_CARPAINT, CARP)
sub = body.modifiers.new("Subdiv", "SUBSURF"); sub.levels = sub.render_levels = 2
for sy in (-1, 1):                     # wheel arches
    cut = bpy.data.objects.new(f"ArchCut_{sy:+d}", bpy.data.meshes.new(f"ArchCut_{sy:+d}"))
    CARP.objects.link(cut)
    bpy.context.view_layer.objects.active = None
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=WR + 0.06, radius2=WR + 0.06, depth=2.4)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=__import__("mathutils").Matrix.Rotation(math.pi / 2, 3, "Y"))
    bm.to_mesh(cut.data); bm.free()
    cut.location = (0, sy * WB, WR); cut.display_type = "WIRE"; cut.hide_render = True; cut.hide_set(True)
    cut.parent = root
    bo = body.modifiers.new(f"Arch_{sy:+d}", "BOOLEAN"); bo.object = cut; bo.operation = "DIFFERENCE"
body.parent = root

ROOF = [(-1.5, 0.95), (-1.15, 1.13), (-0.65, 1.27), (-0.05, 1.29), (0.3, 1.2), (0.78, 0.92)]


def cabin_section(y):
    zb = interp(TOP, y) - 0.03; zr = max(interp(ROOF, y), zb + 0.02)
    wb, wr = 0.86, 0.64
    pts = []
    K = 28
    for k in range(K):
        t = math.pi * k / (K - 1)                 # 0..pi across the top
        c, s = math.cos(t), math.sin(t)
        u = abs(s) ** (2 / 5)
        pts.append(((wb + (wr - wb) * u) * math.copysign(abs(c) ** (2 / 5), c), zb + (zr - zb) * u))
    pts.append((-wb * 0.95, zb - 0.05)); pts.append((wb * 0.95, zb - 0.05))
    return pts


cabin = loft("CarCabin", np.linspace(-1.5, 0.78, 30), cabin_section, M_GLASS, CARP)
cs = cabin.modifiers.new("Subdiv", "SUBSURF"); cs.levels = cs.render_levels = 1
cabin.parent = root


def car_box(name, x0, x1, y0, y1, z0, z1, mat, bevel=0.01):
    o = box(name, x0, x1, y0, y1, z0, z1, mat, CARP); o.parent = root
    if bevel:
        b = o.modifiers.new("Bevel", "BEVEL"); b.width = bevel; b.segments = 3
    return o


for sx in (-1, 1):
    car_box(f"Headlight_{sx:+d}", *sorted((sx * 0.48, sx * 0.82)), 2.12, 2.2, 0.66, 0.71, M_HEAD, 0.008)
    car_box(f"Mirror_{sx:+d}", *sorted((sx * 0.86, sx * 1.02)), 0.42, 0.56, 0.95, 1.04, M_CARPAINT, 0.02)
    car_box(f"SideSkirt_{sx:+d}", *sorted((sx * 0.9, sx * 0.97)), -0.95, 0.95, 0.2, 0.3, M_TRIM, 0.02)
car_box("Taillight", -0.88, 0.88, -2.23, -2.15, 0.84, 0.88, M_TAIL, 0.008)
car_box("Grille", -0.6, 0.6, 2.12, 2.24, 0.3, 0.46, M_TRIM, 0.02)
car_box("Diffuser", -0.75, 0.75, -2.3, -2.0, 0.24, 0.36, M_TRIM, 0.02)
car_box("Underbody", -0.85, 0.85, -2.0, 2.0, 0.16, 0.26, M_TRIM, 0)


def wheel(name, x, y):
    import bmesh
    from mathutils import Matrix
    hub = bpy.data.objects.new(name, None); hub.empty_display_type = "CIRCLE"; hub.empty_display_size = WR
    hub.location = (x, y, WR); hub.parent = root; CARP.objects.link(hub)
    out = 1 if x > 0 else -1

    def cyl(n, r, depth, off, mat, seg=48, bevel=0.0):
        me = bpy.data.meshes.new(n); bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=depth)
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "Y"))
        bmesh.ops.translate(bm, verts=bm.verts, vec=(off, 0, 0))
        bm.to_mesh(me); bm.free(); me.materials.append(mat)
        for p in me.polygons: p.use_smooth = True
        o = bpy.data.objects.new(n, me); CARP.objects.link(o); o.parent = hub
        if bevel:
            b = o.modifiers.new("Bevel", "BEVEL"); b.width = bevel; b.segments = 4
        return o
    cyl(name + "_tyre", WR, 0.24, 0, M_TYRE, bevel=0.05)
    cyl(name + "_rim", 0.235, 0.03, out * 0.11, M_RIM, bevel=0.008)
    cyl(name + "_cap", 0.05, 0.03, out * 0.125, M_TRIM, seg=24)
    cyl(name + "_disc", 0.2, 0.02, out * 0.05, M_RIM, seg=32)
    cal = car_box(name + "_caliper", -0.03, 0.03, -0.06, 0.06, 0.1, 0.2, M_BRAKE)
    cal.parent = None; cal.location = (x + out * 0.0, y + 0.0, 0); cal.parent = root   # caliper stays still (not on the hub)
    for k in range(5):                       # spokes
        me = bpy.data.meshes.new(f"{name}_spoke{k}")
        a = 2 * math.pi * k / 5
        o = box(f"{name}_spoke{k}", -0.012, 0.012, -0.022, 0.022, 0.04, 0.22, M_RIM, CARP)
        o.parent = hub; o.location = (out * 0.128, 0, 0); o.rotation_euler = (a, 0, 0)
    return hub


WHEELS = [wheel(f"Wheel_{'FR' if (y > 0 and x > 0) else 'FL' if y > 0 else 'RR' if x > 0 else 'RL'}", x, y)
          for x in (-TRACK, TRACK) for y in (-WB, WB)]

# car lights that light the scene (parented: they move with the car)
for sx in (-1, 1):
    ld = bpy.data.lights.new(f"Headbeam_{sx:+d}", "SPOT"); ld.energy = 2500; ld.color = (0.9, 0.95, 1.0)
    ld.spot_size = math.radians(55); ld.spot_blend = 0.5; ld.shadow_soft_size = 0.05
    o = bpy.data.objects.new(ld.name, ld); o.location = (sx * 0.65, 2.25, 0.68)
    o.rotation_euler = (math.radians(-84), 0, 0)          # spot points -Z; tilt to +Y, slightly down
    o.parent = root; CAR.objects.link(o)
ld = bpy.data.lights.new("TailGlow", "AREA"); ld.energy = 40; ld.color = (1.0, 0.05, 0.02); ld.size = 1.6
o = bpy.data.objects.new("TailGlow", ld); o.location = (0, -2.3, 0.86); o.rotation_euler = (math.radians(-90), 0, 0)
o.parent = root; CAR.objects.link(o)

def car_regions(o):
    """Per-face materials for the user's car.stl (one fused mesh) from face position/normal, in STL units
    (length 1.163 along X, front at -X; height 0..0.36). Measured with probe_regions.py: axles x -0.36 / +0.27,
    wheel radius ~0.085 (centre z 0.083), greenhouse z 0.25-0.335 over x -0.13..0.46."""
    me = o.data; n = len(me.polygons)
    c = np.zeros(n * 3); me.polygons.foreach_get("center", c); c = c.reshape(-1, 3) + np.array([0.0205, 0, 0])
    nm = np.zeros(n * 3); me.polygons.foreach_get("normal", nm); nm = nm.reshape(-1, 3)
    x, y, z = c[:, 0], np.abs(c[:, 1]), c[:, 2]
    mats = [M_CARPAINT, M_GLASS, M_RIM, M_TYRE, M_HEAD, M_TAIL, M_TRIM]
    for m in mats: me.materials.append(m)
    idx = np.zeros(n, int)
    idx[(z > 0.25) & (z < 0.335) & (np.abs(nm[:, 2]) < 0.8) & (x > -0.14) & (x < 0.47)] = 1   # glass
    idx[z < 0.03] = 6                                                                       # underbody
    idx[((x < -0.52) | (x > 0.565)) & (z > 0.04) & (z < 0.125)] = 2                          # chrome bumpers
    idx[(x < -0.49) & (z > 0.125) & (z < 0.19) & (y > 0.11) & (y < 0.205)] = 4                # headlights
    idx[(x > 0.55) & (z > 0.12) & (z < 0.175) & (y > 0.12)] = 5                              # tail lights
    for ax in (-0.3405, 0.2905):                         # axles (+0.0205 centring shift applied to x)
        d = np.hypot(x - ax, z - 0.083)
        wheel = (d < 0.09) & (y > 0.12)
        idx[wheel & (d >= 0.06)] = 3                      # tyre
        idx[wheel & (d < 0.06)] = 2                       # chrome wire wheel
    me.polygons.foreach_set("material_index", idx.tolist())
    print("CAR REGIONS", {m.name: int((idx == i).sum()) for i, m in enumerate(mats)})


# hero = the user's car.stl (one solid 300k-tri mesh, 1.163 long, front at -X, wheels fused to the body)
bpy.ops.wm.stl_import(filepath=HERE + "/car.stl")
stl = bpy.context.selected_objects[0]; stl.name = "CarSTL"
for c in list(stl.users_collection): c.objects.unlink(stl)
CAR.objects.link(stl)
S_STL = 4.5 / 1.163                                  # real-car length 4.5 m
stl.data.transform(__import__("mathutils").Matrix.Translation((-0.0205, 0, 0)))   # centre the length on the origin
stl.scale = (S_STL,) * 3; stl.rotation_euler = (0, 0, -math.pi / 2)                # front -X -> +Y
for p in stl.data.polygons: p.use_smooth = True
car_regions(stl)                                    # paint / glass / chrome / tyre / lights by position (model units)
stl.parent = root
bpy.context.view_layer.layer_collection.children["HeroCar_Procedural"].exclude = True

root.location = (LANE_X, HERO_Y, 0.0)      # parked on the hero mark for set-up; the drive is keyed in step 2


# ---------- world: blue-hour city HDRI ----------
world = bpy.data.worlds.new("World"); scene.world = world; world.use_nodes = True
wn = world.node_tree; bg = next(n for n in wn.nodes if n.type == "BACKGROUND")
env = wn.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(A + "/hdri/rooftop_night_2k.hdr")
mp = wn.nodes.new("ShaderNodeMapping"); tc = wn.nodes.new("ShaderNodeTexCoord")
wn.links.new(tc.outputs["Generated"], mp.inputs["Vector"]); wn.links.new(mp.outputs["Vector"], env.inputs["Vector"])
mp.inputs["Rotation"].default_value = (0, 0, math.radians(90))     # brightest part of the sky down the street
wn.links.new(env.outputs["Color"], bg.inputs["Color"])
bg.inputs["Strength"].default_value = 1.2          # v1 0.7 came out too dark through Wan


# ---------- shot cameras + markers (cuts) ----------
SHOTS = [  # name, start frame, location, look-at, lens   (first pose only; motion comes in step 2)
    ("S1_Establish", 1, (-2.8, 120.0, 0.6), (LANE_X, 40.0, 1.0), 35),      # low, down the street: headlights approach
    ("S2_Tracking", 193, (LANE_X - 6.5, 20.0, 1.2), (LANE_X, 22.0, 0.8), 40),  # side-on, moving with the car
    ("S3_Orbit", 577, (LANE_X - 4.5, HERO_Y + 5.5, 1.6), (LANE_X, HERO_Y, 0.7), 45),  # car stops under the lamp, orbit
    ("S4_Details", 961, (LANE_X + 1.6, HERO_Y + 3.0, 0.45), (LANE_X + 0.8, HERO_Y + 1.4, 0.4), 60),  # wheel + headlight close-ups
    ("S5_Drive_off", 1201, (0.0, HERO_Y - 12.0, 3.5), (LANE_X, HERO_Y + 30.0, 0.8), 32),  # pulls away to the barriers, crane up
]
for name, f, loc, look, lens in SHOTS:
    cd = bpy.data.cameras.new(name); cd.lens = lens; cd.clip_end = 400
    cam = bpy.data.objects.new(name, cd); cam.location = loc; CAMS.objects.link(cam)
    d = Vector(look) - Vector(loc)
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    mk = scene.timeline_markers.new(name, frame=f); mk.camera = cam
scene.camera = bpy.data.objects[SHOTS[0][0]]


# ---------- render settings (final render on RunPod; phone previews use Cycles at low res) ----------
for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
    try:
        scene.render.engine = eng; break
    except TypeError:
        pass
ee = scene.eevee
ee.taa_render_samples = 32
for k, v in {"use_shadows": True, "use_raytracing": True, "use_gtao": True, "ray_tracing_method": "SCREEN",
             "shadow_ray_count": 2, "shadow_step_count": 8, "fast_gi_method": "GLOBAL_ILLUMINATION"}.items():
    try: setattr(ee, k, v)
    except Exception as ex: print("eevee setting", k, ex)
scene.render.fps = FPS; scene.frame_start = 1; scene.frame_end = FRAMES
scene.render.use_motion_blur = True
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1920, 1080, 100
scene.render.image_settings.file_format = "JPEG"; scene.render.image_settings.quality = 92
scene.view_settings.view_transform = "AgX"
scene.view_settings.exposure = 1.0                 # brighter base for the AI pass (v1 too dark)
try: scene.view_settings.look = "AgX - Medium High Contrast"
except TypeError: pass

bpy.ops.wm.save_as_mainfile(filepath=HERE + "/car_street.blend", compress=True)
print("SAVED objects", len(bpy.data.objects), "lights", len([o for o in bpy.data.objects if o.type == "LIGHT"]),
      "doors", len(DOORS), "lamps", len(lamp_ys) + 1)
