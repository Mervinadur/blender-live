"""Knight turntable scene for Blender 4.3 (Blender Live).

Builds: Poly Haven chess knight (marble statue) + an armoured knight made from primitives
(Poly Haven metal_plate / velour_velvet textures, real Poly Haven kite shield and estoc),
both on a rotating marble pedestal on a monastery stone floor, lit by the
castle_zavelstein_cellar HDRI. Animates one seamless, constant-speed 360 degree turn.

Assets: run fetch_assets.py first (puts them in ./assets).
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
    turntable.empty_display_size = 1.35
    bpy.context.collection.objects.link(turntable)

    marble = pbr_material("Marble", "marble_01", "2k", scale=0.8, box=True)
    prim("cyl", "PedestalBase", (0, 0, 0.06), mat=marble, parent=None, subsurf=0, bevel=0.02,
         radius=1.32, depth=0.12, vertices=96)
    prim("cyl", "PedestalTop", (0, 0, 0.21), mat=marble, parent=turntable, subsurf=0,
         bevel=0.025, radius=1.2, depth=0.18, vertices=96)
    bpy.data.objects["PedestalBase"].hide_select = True
    return turntable


def build_chess_knight(turntable):
    objs = import_gltf("chess_set")
    knight = single_mesh(objs, "piece_knight_white_01")
    knight.name = "ChessKnight"
    fit(knight, height=1.55)
    knight.rotation_euler.z = math.radians(-90)   # horse faces the camera at frame 1 (checked in a test render)
    knight.location = (0.58, 0.05, 0.30)
    knight.parent = turntable
    return knight


def build_armoured_knight(turntable):
    root = bpy.data.objects.new("ArmouredKnight", None)
    bpy.context.collection.objects.link(root)

    steel = pbr_material("Steel", "metal_plate", "2k", scale=3.0, box=True, metallic=1.0,
                         base_color=(0.8, 0.81, 0.83), rough_mul=0.7, normal_strength=0.4)
    velvet = pbr_material("RedVelvet", "velour_velvet", "1k", scale=4.0, box=True, metallic=0.0,
                          tint=(0.75, 0.06, 0.05))
    gold = flat_material("Gold", (1.0, 0.72, 0.3), metallic=1.0, roughness=0.3)
    leather = flat_material("Leather", (0.12, 0.06, 0.03), roughness=0.6)
    dark = flat_material("VisorDark", (0.01, 0.01, 0.01), roughness=0.9)

    for sx, side in ((1, "L"), (-1, "R")):
        x = 0.11 * sx
        prim("cube", f"Sabaton.{side}", (x, -0.05, 0.05), (0.06, 0.13, 0.045), mat=steel,
             parent=root, bevel=0.02)
        limb(f"Greave.{side}", (x, 0, 0.08), (x, 0, 0.5), 0.055, 0.072, steel, root)
        prim("sphere", f"Knee.{side}", (x, -0.015, 0.53), (0.075, 0.07, 0.07), mat=steel, parent=root)
        limb(f"Cuisse.{side}", (x, 0, 0.55), (x * 1.05, 0, 0.92), 0.075, 0.095, steel, root)

    prim("cone", "Skirt", (0, 0, 0.84), (1, 0.72, 1), mat=velvet, parent=root, subsurf=1,
         radius1=0.25, radius2=0.19, depth=0.36)
    prim("torus", "Belt", (0, 0, 1.02), (1, 0.76, 1), mat=leather, parent=root, subsurf=1,
         major_radius=0.19, minor_radius=0.028)
    prim("cube", "Buckle", (0, -0.165, 1.02), (0.035, 0.012, 0.03), mat=gold, parent=root, bevel=0.005)
    prim("sphere", "Cuirass", (0, 0, 1.26), (0.21, 0.155, 0.28), mat=steel, parent=root)
    prim("cyl", "Tabard", (0, -0.02, 1.2), (0.205, 0.145, 0.16),
         mat=velvet, parent=root, subsurf=2)
    prim("cube", "Cross.V", (0, -0.163, 1.22), (0.018, 0.01, 0.1), mat=gold, parent=root, subsurf=0,
         bevel=0.004)
    prim("cube", "Cross.H", (0, -0.163, 1.25), (0.065, 0.01, 0.018), mat=gold, parent=root, subsurf=0,
         bevel=0.004)
    prim("cyl", "Gorget", (0, 0, 1.53), (1, 1, 1), mat=steel, parent=root, subsurf=1,
         radius=0.085, depth=0.09)

    # arms: knight's right (-X) rests on the sword pommel, left (+X) holds the shield
    for sx, side in ((1, "L"), (-1, "R")):
        prim("sphere", f"Pauldron.{side}", (0.235 * sx, 0, 1.46), (0.125, 0.125, 0.09), mat=steel,
             parent=root)
        prim("sphere", f"PauldronLame.{side}", (0.25 * sx, 0, 1.39), (0.11, 0.11, 0.06), mat=steel,
             parent=root)
    arms = {"R": [(-0.26, 0, 1.42), (-0.29, -0.04, 1.17), (-0.12, -0.24, 1.0)],
            "L": [(0.26, 0, 1.42), (0.30, -0.02, 1.17), (0.27, -0.25, 1.08)]}
    for side, (sh, el, wr) in arms.items():
        limb(f"UpperArm.{side}", sh, el, 0.058, 0.05, steel, root)
        prim("sphere", f"Couter.{side}", el, (0.065, 0.065, 0.065), mat=steel, parent=root)
        limb(f"Vambrace.{side}", el, wr, 0.05, 0.045, steel, root)
        prim("sphere", f"Gauntlet.{side}", wr, (0.055, 0.06, 0.05), mat=steel, parent=root)

    prim("cyl", "Helm", (0, 0, 1.68), (1, 1, 1), mat=steel, parent=root, subsurf=1,
         radius=0.118, depth=0.22)
    prim("sphere", "HelmTop", (0, 0, 1.79), (0.118, 0.118, 0.07), mat=steel, parent=root)
    prim("cube", "EyeSlit", (0, -0.112, 1.715), (0.085, 0.02, 0.009), mat=dark, parent=root,
         subsurf=0)
    prim("cube", "HelmRidge", (0, -0.12, 1.65), (0.008, 0.008, 0.06), mat=steel, parent=root,
         subsurf=0, bevel=0.003)
    for i, z in enumerate((1.61, 1.635, 1.66)):
        for sx in (1, -1):
            prim("cube", f"Breath.{i}.{sx}", (0.05 * sx, -0.113, z), (0.02, 0.02, 0.004), mat=dark,
                 parent=root, subsurf=0)
    prim("sphere", "Plume", (0, 0.03, 1.88), (0.035, 0.13, 0.07), mat=velvet, parent=root)

    # Poly Haven props
    shield = join_meshes(import_gltf("kite_shield"), "KiteShield")
    fit(shield, height=0.95)
    sword = join_meshes(import_gltf("antique_estoc"), "Estoc")
    sword.rotation_euler.x += math.pi        # imported hilt-down; stand it point-down
    fit(sword, longest=1.1)
    shield.location = (0.36, -0.30, 0.42)    # on the left forearm
    shield.rotation_euler.z = math.radians(-12)
    sword.location = (-0.12, -0.24, 0.0)     # tip on the pedestal, grip in the right gauntlet
    for o in (shield, sword):
        o.parent = root

    root.location = (-0.52, 0.0, 0.30)
    root.parent = turntable
    return root, shield, sword


def setup_camera_lights():
    cam_data = bpy.data.cameras.new("TurntableCam")
    cam_data.lens = 72
    cam = bpy.data.objects.new("TurntableCam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (0, -6.4, 1.9)
    target = bpy.data.objects.new("CamTarget", None)
    bpy.context.collection.objects.link(target)
    target.location = (0, 0, 1.08)
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
    scene = bpy.context.scene
    scene.render.resolution_x = 720
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"     # Cycles here has no denoiser
    except TypeError as e:
        print("EEVEE Next not available:", e)
    else:
        scene.eevee.taa_render_samples = 16            # ~19 s/frame at 720 px on llvmpipe
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = "/root/models/knight/frames/f_"


def main():
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    clear_scene()
    setup_world()
    turntable = setup_floor_and_pedestal()
    build_chess_knight(turntable)
    build_armoured_knight(turntable)
    setup_camera_lights()
    animate_turntable(turntable)
    setup_render()
    bpy.context.scene.frame_set(1)
    print("knight scene ready")


main()
