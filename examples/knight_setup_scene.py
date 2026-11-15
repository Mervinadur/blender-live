"""Knight turntable scene for Blender 4.3 (Blender Live).

Builds: the user's knight STL (Knight.stl, one solid mesh) coloured by region: polished plate steel
(procedural, v3), red velvet cape (velour_velvet), stone base (monastery_stone_floor),
bone skulls and glowing flames. It stands on a rotating marble pedestal (marble_01) on a monastery
stone floor, lit by the castle_zavelstein_cellar HDRI. Animates one seamless, constant-speed 360 degree turn.

Assets: run fetch_assets.py first (puts them in ./assets). STL path: KNIGHT_STL or /root/models/knight/Knight.stl.
Run in Blender:  exec(open("/root/models/knight/setup_scene.py").read())
or from a shell:  blender --python setup_scene.py
"""
import math
import os

import bpy
from mathutils import Vector

ASSETS = os.environ.get("KNIGHT_ASSETS", "/root/models/knight/assets")
FRAMES = 120          # one full turn = 120 frames (5 s at 24 fps)
FPS = 24
RES = (1440, 1800)    # v3: 4:5 portrait (tall knight, fills a phone screen)


# ---------------------------------------------------------------- helpers
def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.cameras,
                 bpy.data.lights, bpy.data.curves, bpy.data.actions, bpy.data.node_groups):
        for block in list(coll):
            if block.users == 0:
                coll.remove(block)


def tex_path(name, kind, res):
    return os.path.join(ASSETS, "textures", name, f"{name}_{kind}_{res}.jpg")


def node(nodes, type_name):
    return next(n for n in nodes if n.type == type_name)


def pbr_material(mat_name, tex_name, res, scale=1.0, box=True, metallic=None, tint=None,
                 rough_mul=1.0, normal_strength=1.0, base_color=None):
    """Principled material from a Poly Haven texture set.
    box=True: box-projected object coordinates (no UVs needed); False: UV map.
    base_color: use this flat colour instead of the diffuse map (keeps rough/normal maps)."""
    mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = node(nodes, "BSDF_PRINCIPLED")

    coord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (scale, scale, scale)
    links.new(coord.outputs["Object" if box else "UV"], mapping.inputs["Vector"])

    def image(kind, non_color):
        path = tex_path(tex_name, kind, res)
        if not os.path.exists(path):
            return None
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(path, check_existing=True)
        if non_color:
            tex.image.colorspace_settings.name = "Non-Color"
        if box:
            tex.projection = "BOX"
            tex.projection_blend = 0.25
        links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        return tex

    diff = None if base_color else image("diff", False)
    if base_color:
        bsdf.inputs["Base Color"].default_value = (*base_color, 1.0)
        mat.diffuse_color = (*base_color, 1.0)
    if diff:
        if tint:
            mix = nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            links.new(diff.outputs["Color"], mix.inputs["A"])
            mix.inputs["B"].default_value = (*tint, 1.0)
            links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
        else:
            links.new(diff.outputs["Color"], bsdf.inputs["Base Color"])

    rough = image("rough", True)
    if rough:
        mul = nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = rough_mul
        links.new(rough.outputs["Color"], mul.inputs[0])
        links.new(mul.outputs["Value"], bsdf.inputs["Roughness"])

    if metallic is None:
        metal = image("metal", True)
        if metal:
            links.new(metal.outputs["Color"], bsdf.inputs["Metallic"])
    else:
        bsdf.inputs["Metallic"].default_value = metallic

    nor = image("nor_gl", True)
    if nor:
        nmap = nodes.new("ShaderNodeNormalMap")
        nmap.inputs["Strength"].default_value = normal_strength
        links.new(nor.outputs["Color"], nmap.inputs["Color"])
        links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def flat_material(name, color, metallic=0.0, roughness=0.5):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = node(mat.node_tree.nodes, "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    mat.diffuse_color = (*color, 1.0)
    return mat


def finish(ob, mat, parent, subsurf=2, bevel=0.0):
    ob.data.materials.append(mat)
    if bevel:
        m = ob.modifiers.new("Bevel", "BEVEL")
        m.width = bevel
        m.segments = 2
    if subsurf:
        ob.modifiers.new("Subsurf", "SUBSURF").levels = subsurf
        ob.modifiers["Subsurf"].render_levels = subsurf
    for p in ob.data.polygons:
        p.use_smooth = True
    ob.parent = parent
    return ob


def prim(kind, name, loc, scale=(1, 1, 1), rot=(0, 0, 0), mat=None, parent=None,
         subsurf=2, bevel=0.0, **kw):
    add = {"sphere": bpy.ops.mesh.primitive_uv_sphere_add,
           "cube": bpy.ops.mesh.primitive_cube_add,
           "cyl": bpy.ops.mesh.primitive_cylinder_add,
           "cone": bpy.ops.mesh.primitive_cone_add,
           "torus": bpy.ops.mesh.primitive_torus_add}[kind]
    if kind == "sphere":
        kw.setdefault("segments", 32)
        kw.setdefault("ring_count", 16)
    if kind in ("cyl", "cone"):
        kw.setdefault("vertices", 32)
    add(location=loc, rotation=rot, **kw)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = scale
    return finish(ob, mat, parent, subsurf, bevel)


def limb(name, p1, p2, r1, r2, mat, parent):
    """Tapered cylinder from p1 (radius r1) to p2 (radius r2)."""
    p1, p2 = Vector(p1), Vector(p2)
    d = p2 - p1
    bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=r1, radius2=r2, depth=d.length,
                                    location=(p1 + p2) / 2)
    ob = bpy.context.active_object
    ob.name = name
    ob.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    return finish(ob, mat, parent, subsurf=1)


def import_gltf(asset):
    folder = os.path.join(ASSETS, "models", asset)
    gltf = next(f for f in os.listdir(folder) if f.endswith(".gltf"))
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(folder, gltf))
    return [o for o in bpy.data.objects if o not in before]


def world_bbox(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == "MESH" for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def single_mesh(objs, keep_name):
    """Keep one mesh object from an import, unparented with transforms applied."""
    keep = bpy.data.objects[keep_name]
    mw = keep.matrix_world.copy()
    for o in objs:
        if o is not keep:
            bpy.data.objects.remove(o, do_unlink=True)
    keep.parent = None
    keep.matrix_world = mw
    return keep


def join_meshes(objs, name):
    """Join every mesh of an import into one object (drops empties), transforms kept."""
    meshes = [o for o in objs if o.type == "MESH"]
    mws = {o: o.matrix_world.copy() for o in meshes}
    for o in meshes:
        o.parent = None
        o.matrix_world = mws[o]
    for o in objs:
        if o.type != "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    return ob


def fit(ob, height=None, longest=None):
    """Scale ob, then centre it on X/Y=0 with its base at z=0 (all baked into the mesh)."""
    bpy.context.view_layer.update()
    lo, hi = world_bbox([ob])
    size = hi - lo
    s = height / size.z if height else longest / max(size)
    ob.scale = ob.scale * s
    bpy.context.view_layer.update()
    lo, hi = world_bbox([ob])
    ob.location -= Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return ob


# ---------------------------------------------------------------- scene parts
def setup_world():
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(
        os.path.join(ASSETS, "hdri", "castle_zavelstein_cellar_2k.hdr"), check_existing=True)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value[2] = math.radians(200)   # brightest window behind camera-left
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 1.2
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def setup_floor_and_pedestal():
    bpy.ops.mesh.primitive_plane_add(size=14, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = "Floor"
    floor.data.materials.append(pbr_material("StoneFloor", "monastery_stone_floor", "2k",
                                             scale=0.4, box=True))
    floor.hide_select = True

    turntable = bpy.data.objects.new("Turntable", None)
    turntable.empty_display_type = "CIRCLE"
    turntable.empty_display_size = 1.0
    bpy.context.collection.objects.link(turntable)

    marble = pbr_material("Marble", "marble_01", "2k", scale=0.8, box=True)
    prim("cyl", "PedestalBase", (0, 0, 0.06), mat=marble, parent=None, subsurf=0, bevel=0.02,
         radius=0.98, depth=0.12, vertices=96)
    prim("cyl", "PedestalTop", (0, 0, 0.21), mat=marble, parent=turntable, subsurf=0,
         bevel=0.025, radius=0.86, depth=0.18, vertices=96)
    bpy.data.objects["PedestalBase"].hide_select = True
    return turntable


STL = os.environ.get("KNIGHT_STL", "/root/models/knight/Knight.stl")
# Colour regions, in the STL's own coordinates (1.015 tall, z up, faces -Y, raised hand on +X).
SKULL_C, SKULL_R = Vector((0.1818, -0.1183, 0.8603)), 0.06   # least-squares fit of the held skull


# v3 colouring: split the surface into patches at creases > 12 degrees (the cape is one clean patch),
# then colour patches by rules; skulls on the base and the feet are found by position (top-down view).
CREASE_ANG = 12.0
SKULL_BOXES = [(-0.225, -0.135, -0.135, 0.01),    # front-left skull
               (-0.035, 0.09, -0.2, 0.035)]       # front-centre skull (lying, cranium to the back)
BOOT_BOXES = [(-0.15, -0.03, -0.215, 0.015), (0.07, 0.26, -0.135, 0.075)]   # feet, top-down view


def faces_and_patches(me):
    import numpy as np
    nf = len(me.polygons)
    g = lambda a, k: (lambda b: (me.polygons.foreach_get(a, b), b)[1])(np.empty(nf*k, int if a == "vertices" else float))
    nrm, cen, tri = g("normal", 3).reshape(-1,3), g("center", 3).reshape(-1,3), g("vertices", 3).reshape(-1,3)
    e = np.concatenate([tri[:,[0,1]], tri[:,[1,2]], tri[:,[2,0]]]); e.sort(1)
    f = np.tile(np.arange(nf), 3); o = np.lexsort((e[:,1], e[:,0])); e, f = e[o], f[o]
    same = (e[1:] == e[:-1]).all(1); pairs = np.stack([f[:-1][same], f[1:][same]], 1)
    smooth = pairs[(nrm[pairs[:,0]] * nrm[pairs[:,1]]).sum(1) > math.cos(math.radians(CREASE_ANG))]
    lab = np.arange(nf)
    while True:
        m = np.minimum(lab[smooth[:,0]], lab[smooth[:,1]]); old = lab.copy()
        np.minimum.at(lab, smooth[:,0], m); np.minimum.at(lab, smooth[:,1], m); lab = lab[lab]
        if (lab == old).all(): break
    return nrm, cen, pairs, np.unique(lab, return_inverse=True)[1]


def stl_regions(nrm, cen, pairs, patch):
    import numpy as np
    """0 armour, 1 cape, 2 base, 3 bone, 4 flame; -1 = undecided (filled from neighbours)."""
    x, y, z = cen.T
    cnt = np.bincount(patch); size = cnt[patch]
    pz_max = np.zeros(len(cnt)); np.maximum.at(pz_max, patch, z)
    reg = np.full(len(cen), -1)
    big = size >= 300                                                  # small patches = detail, decided later
    reg[big] = 0
    reg[patch == np.argmax(cnt)] = 1                                   # the cape (one big cloth patch)
    boots = np.zeros(len(cen), bool)
    for (x0, x1, y0, y1) in BOOT_BOXES:
        boots |= (x > x0) & (x < x1) & (y > y0) & (y < y1)
    pboot = np.bincount(patch, boots) / cnt                            # share of a patch inside a boot box
    reg[big & (pz_max[patch] < 0.17) & (pboot[patch] < 0.5)] = 2       # base disc + slabs (not the feet)
    reg[z < 0.065] = 2
    # held skull + flames (exact geometry rules from v2)
    d = np.linalg.norm(cen - np.array(SKULL_C), axis=1); hand = (x > 0.1) & (z > 0.75)
    reg[hand & (d <= SKULL_R + 0.004)] = 3
    reg[hand & (d > SKULL_R + 0.004) & (z > SKULL_C.z + 0.015) & (d < SKULL_R + 0.09)] = 4
    # skulls on the base (fused into the slabs, so found by position: top-down view, STL coords)
    for (x0, x1, y0, y1) in SKULL_BOXES:
        box = (x > x0) & (x < x1) & (y > y0) & (y < y1) & (z > 0.085) & (z < 0.25) & (reg != 1)
        flat = box & (np.abs(nrm[:, 2]) > 0.98)
        top = np.median(z[flat & (z < 0.17)]) if (flat & (z < 0.17)).any() else 0.13
        reg[box & (z > top + 0.003)] = 3
        print("skull box", (x0, x1, y0, y1), "slab top", round(float(top), 3), "faces", int((box & (z > top + 0.003)).sum()))
    # fill the rest by neighbour majority
    for _ in range(200):
        und = reg < 0
        if not und.any(): break
        a, b = pairs[:,0], pairs[:,1]
        votes = np.zeros((len(reg), 5))
        for s, t in ((a, b), (b, a)):
            ok = (reg[s] < 0) & (reg[t] >= 0)
            np.add.at(votes, (s[ok], reg[t[ok]]), 1)
        has = und & (votes.sum(1) > 0)
        reg[has] = votes[has].argmax(1)
    reg[reg < 0] = 0
    # stray armour-coloured slivers on the slabs (away from the boots) -> stone
    reg[(reg == 0) & (z < 0.17) & ~boots & (size < 300)] = 2
    return reg


def add_ao(mat, distance=0.04):
    """Darken crevices: Base Color -> Ambient Occlusion -> Base Color (brings out the sculpt detail)."""
    nt = mat.node_tree
    bsdf = node(nt.nodes, "BSDF_PRINCIPLED")
    ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = distance
    sock = bsdf.inputs["Base Color"]
    if sock.is_linked:
        nt.links.new(sock.links[0].from_socket, ao.inputs["Color"])
    else:
        ao.inputs["Color"].default_value = sock.default_value
    nt.links.new(ao.outputs["Color"], sock)


def flame_material():
    mat = bpy.data.materials.new("Flame")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = node(nt.nodes, "BSDF_PRINCIPLED")
    ramp = nt.nodes.new("ShaderNodeValToRGB")          # yellow core -> orange tips (by facing ratio)
    ramp.color_ramp.elements[0].color = (1.0, 0.85, 0.3, 1)
    ramp.color_ramp.elements[1].color = (1.0, 0.25, 0.02, 1)
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.4
    nt.links.new(lw.outputs["Facing"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 12.0
    mat.diffuse_color = (1.0, 0.45, 0.05, 1)
    return mat


def steel_material():
    """Polished plate armour: metallic, roughness varied by wear noise, faint hammered bump, no tiling pattern."""
    mat = bpy.data.materials.new("PlateSteel")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = node(nodes, "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.56, 0.57, 0.6, 1)
    bsdf.inputs["Metallic"].default_value = 1.0
    mat.diffuse_color = (0.56, 0.57, 0.6, 1)
    coord = nodes.new("ShaderNodeTexCoord")
    wear = nodes.new("ShaderNodeTexNoise")                # large soft patches: polished vs dull
    wear.inputs["Scale"].default_value = 6.0
    wear.inputs["Detail"].default_value = 6.0
    links.new(coord.outputs["Object"], wear.inputs["Vector"])
    ramp = nodes.new("ShaderNodeMapRange")
    ramp.inputs["From Min"].default_value = 0.35
    ramp.inputs["From Max"].default_value = 0.65
    ramp.inputs["To Min"].default_value = 0.18
    ramp.inputs["To Max"].default_value = 0.36
    links.new(wear.outputs["Fac"], ramp.inputs["Value"])
    links.new(ramp.outputs["Result"], bsdf.inputs["Roughness"])
    dents = nodes.new("ShaderNodeTexNoise")               # fine hammered surface
    dents.inputs["Scale"].default_value = 90.0
    dents.inputs["Detail"].default_value = 2.0
    links.new(coord.outputs["Object"], dents.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.04
    links.new(dents.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def build_stl_knight(turntable):
    import numpy as np
    before = set(bpy.data.objects)
    bpy.ops.wm.stl_import(filepath=STL)
    ob = next(o for o in bpy.data.objects if o not in before)
    ob.name = "Knight"
    me = ob.data
    reg = stl_regions(*faces_and_patches(me))

    steel = steel_material()      # v3: smooth plate steel (metal_plate maps showed a diamond tread pattern)
    cape = pbr_material("RedVelvet", "velour_velvet", "1k", scale=6.0, box=True, metallic=0.0,
                        tint=(0.55, 0.03, 0.04))
    base = pbr_material("BaseStone", "monastery_stone_floor", "2k", scale=2.5, box=True,
                        tint=(0.5, 0.5, 0.52))
    bone = flat_material("Bone", (0.86, 0.8, 0.66), roughness=0.55)
    for m in (steel, cape, base, bone):
        add_ao(m)
    for m in (steel, cape, base, bone, flame_material()):
        me.materials.append(m)
    me.polygons.foreach_set("material_index", reg)
    me.update()

    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(35))
    except Exception as e:                       # older Blender
        print("smooth by angle unavailable:", e)

    flame_pos = SKULL_C + Vector((0, 0, 0.09))   # STL coords, before fit() moves/scales it
    lo, hi = world_bbox([ob])
    scale = 1.9 / (hi.z - lo.z)
    shift = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    fit(ob, height=1.9)
    ob.location = (0, 0, 0.30)                   # on the pedestal top
    ob.parent = turntable

    glow = bpy.data.lights.new("FlameGlow", "POINT")   # orange light from the flames onto the armour
    glow.energy = 60
    glow.color = (1.0, 0.45, 0.12)
    glow.shadow_soft_size = 0.08
    glow_ob = bpy.data.objects.new("FlameGlow", glow)
    bpy.context.collection.objects.link(glow_ob)
    glow_ob.location = (flame_pos - shift) * scale + Vector((0, 0, 0.30))
    glow_ob.parent = turntable
    return ob


def setup_glow_compositor():
    """Fog-glow bloom on the bright flames (EEVEE Next has no built-in bloom)."""
    scene = bpy.context.scene
    scene.use_nodes = True
    nt = scene.node_tree
    nt.nodes.clear()
    rl = nt.nodes.new("CompositorNodeRLayers")
    glare = nt.nodes.new("CompositorNodeGlare")
    kinds = [i.identifier for i in glare.bl_rna.properties["glare_type"].enum_items]
    glare.glare_type = "FOG_GLOW" if "FOG_GLOW" in kinds else kinds[0]
    glare.quality = "HIGH"
    glare.threshold = 4.0                       # only the flames (emission 12), not steel highlights
    glare.size = 7
    comp = nt.nodes.new("CompositorNodeComposite")
    nt.links.new(rl.outputs["Image"], glare.inputs["Image"])
    nt.links.new(glare.outputs["Image"], comp.inputs["Image"])


def setup_camera_lights():
    cam_data = bpy.data.cameras.new("TurntableCam")
    cam_data.lens = 76                      # v3: a little wider for the 4:5 frame
    cam = bpy.data.objects.new("TurntableCam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (0, -6.4, 1.9)
    target = bpy.data.objects.new("CamTarget", None)
    bpy.context.collection.objects.link(target)
    target.location = (0, 0, 1.08)          # v3: lower, so the pedestal edge clears the frame
    track = cam.constraints.new("TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    bpy.context.scene.camera = cam

    key = bpy.data.lights.new("Key", "AREA")
    key.energy = 1200
    key.size = 2.5
    key_ob = bpy.data.objects.new("Key", key)
    key_ob.location = (-3.5, -3.5, 4.0)
    bpy.context.collection.objects.link(key_ob)
    rim = bpy.data.lights.new("Rim", "AREA")
    rim.energy = 700
    rim.size = 1.5
    rim.color = (1.0, 0.85, 0.65)
    rim_ob = bpy.data.objects.new("Rim", rim)
    rim_ob.location = (3.0, 3.5, 3.2)
    bpy.context.collection.objects.link(rim_ob)
    for ob in (key_ob, rim_ob):
        c = ob.constraints.new("TRACK_TO")
        c.target = target
        c.track_axis = "TRACK_NEGATIVE_Z"
        c.up_axis = "UP_Y"


def animate_turntable(turntable):
    scene = bpy.context.scene
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = FRAMES            # frame FRAMES+1 would equal frame 1 -> seamless loop
    turntable.rotation_euler = (0, 0, 0)
    turntable.keyframe_insert("rotation_euler", index=2, frame=1)
    turntable.rotation_euler.z = 2 * math.pi
    turntable.keyframe_insert("rotation_euler", index=2, frame=FRAMES + 1)
    fc = turntable.animation_data.action.fcurves.find("rotation_euler", index=2)
    for kp in fc.keyframe_points:
        kp.interpolation = "LINEAR"     # constant speed, no ease-in/out
    fc.extrapolation = "LINEAR"


def setup_render():
    """v3 default: Cycles production settings, 4:5 portrait (1440x1800), rendered on a rented GPU via
    render-remote.sh. KNIGHT_ENGINE=EEVEE gives the old fast phone preview (720x720)."""
    scene = bpy.context.scene
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_depth = "8"
    if os.environ.get("KNIGHT_ENGINE", "CYCLES").upper() == "EEVEE":
        scene.render.resolution_x = scene.render.resolution_y = 720
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        scene.eevee.taa_render_samples = 16            # ~19 s/frame at 720 px on llvmpipe
        scene.render.filepath = "/root/models/knight/frames/f_"
        return
    scene.render.resolution_x, scene.render.resolution_y = RES
    scene.render.engine = "CYCLES"
    cy = scene.cycles
    cy.device = "GPU"
    cy.samples = 1024                    # upper limit; adaptive sampling stops early where clean
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.008
    cy.adaptive_min_samples = 64
    cy.use_denoising = True              # denoiser itself is chosen on the GPU machine (v3/pod_render.py)
    cy.max_bounces = 12
    cy.diffuse_bounces = 4
    cy.glossy_bounces = 8                # polished steel reflecting itself
    cy.transmission_bounces = 8
    cy.transparent_max_bounces = 16
    cy.sample_clamp_indirect = 10.0      # no fireflies from the flames on steel
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 0.5
    cy.film_exposure = 1.0
    scene.render.use_motion_blur = True  # slight blur on the turning edge, like a real camera
    scene.render.motion_blur_shutter = 0.5
    scene.render.filter_size = 1.5
    scene.render.filepath = "/root/models/knight/frames_v3/f_"


def main():
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    clear_scene()
    setup_world()
    turntable = setup_floor_and_pedestal()
    build_stl_knight(turntable)
    setup_camera_lights()
    animate_turntable(turntable)
    setup_render()
    setup_glow_compositor()
    bpy.context.scene.frame_set(1)
    print("knight scene ready")


main()
