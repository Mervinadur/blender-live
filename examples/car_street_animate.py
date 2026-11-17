"""Step 2a: minimal motion for the AI (Wan VACE) route. Keys ONLY what the depth/mask feed needs: the car's drive and the
camera moves, directly at 16 fps (Wan's rate), frames 1-960 = 60 s. No wheel spin, no materials: Wan repaints everything.
./run_headless.sh animate.py  ->  car_street_anim.blend
Shots end on Wan chunk boundaries so a cut never falls inside a chunk (each shot = fresh chunk + car reference)."""
import bpy, math
from mathutils import Vector

HERE = "/root/models/car-street"
bpy.ops.wm.open_mainfile(filepath=HERE + "/car_street.blend")
sc = bpy.context.scene
FPS, FRAMES = 16, 960
sc.render.fps = FPS; sc.frame_start = 1; sc.frame_end = FRAMES
LANE_X, HERO_Y = 1.75, 92.0
V, BRAKE_T, STOP_T, GO_T, ACC = 7.0, 18.0, 24.0, 50.0, 1.2     # m/s cruise, brake 18-24 s, parked 24-50 s, leaves at 1.2 m/s²
Y_START = HERO_Y - (V * BRAKE_T + V * (STOP_T - BRAKE_T) / 2)


def car_y(t):
    if t < BRAKE_T: return Y_START + V * t
    if t < STOP_T:
        u = t - BRAKE_T; d = STOP_T - BRAKE_T
        return Y_START + V * BRAKE_T + V * u - V * u * u / (2 * d)
    if t < GO_T: return HERO_Y
    return HERO_Y + 0.5 * ACC * (t - GO_T) ** 2


def car_pos(t): return Vector((LANE_X, car_y(t), 0.0))


def lerp(a, b, u): return a + (b - a) * u
def ease(u): u = max(0.0, min(1.0, u)); return u * u * (3 - 2 * u)


# shot table: name, start s, end s, function(t, u) -> (camera location, look-at, lens)
def s1(t, u):   # low wide down the street, car's headlights approach; slow push back
    # (v1 at y 35-39, 32 mm: car too small, 38-90 m away) -> closer + longer lens: car 60 m -> ~9 m away
    return Vector((-1.6, lerp(10.0, 12.0, u), 0.55)), car_pos(t) + Vector((0, 0, 0.75)), 50
def s2(t, u):   # tracking side-on from the left lane, slightly ahead; stops with the car
    c = car_pos(t); return c + Vector((-4.8, lerp(2.5, 1.0, ease(u)), 1.05)), c + Vector((0, 0.4, 0.6)), 35
def s3(t, u):   # orbit the parked car (ellipse keeps clear of the buildings), drifting lower
    a = math.radians(lerp(215.0, 520.0, ease(u)))
    c = car_pos(t); return c + Vector((4.4 * math.cos(a), 6.5 * math.sin(a), lerp(1.7, 1.0, u))), c + Vector((0, 0, 0.55)), 38
def s4a(t, u):  # low slide from the front wheel to the headlight (right side)
    c = car_pos(t)
    return c + Vector((lerp(2.0, 1.4, u), lerp(0.2, 3.6, ease(u)), lerp(0.35, 0.55, u))), \
        c + Vector((0.8, lerp(1.3, 2.1, ease(u)), lerp(0.35, 0.6, u))), 50
def s4b(t, u):  # low push-in on the rear three-quarter / tail
    c = car_pos(t)
    return c + Vector((lerp(-3.2, -1.9, ease(u)), lerp(-4.6, -3.3, ease(u)), 0.5)), c + Vector((0, -1.6, 0.65)), 45
def s5(t, u):   # car pulls away to the crosswalk, camera cranes up behind it
    c = car_pos(t); return Vector((0.4, HERO_Y - 9.0, lerp(1.0, 6.5, ease(u)))), c + Vector((0, 0, 0.6)), 32


SHOTS = [("S1_Establish", 0, 8, s1), ("S2_Tracking", 8, 24, s2), ("S3_Orbit", 24, 40, s3),
         ("S4_Details", 40, 45, s4a), ("S4b_Tail", 45, 50, s4b), ("S5_Drive_off", 50, 60, s5)]

car = bpy.data.objects["Car"]
car.animation_data_clear()
for f in range(1, FRAMES + 1):
    car.location = car_pos((f - 1) / FPS); car.keyframe_insert("location", frame=f)

sc.timeline_markers.clear()
cams = bpy.data.collections["Cameras"]
for name, t0, t1, fn in SHOTS:
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name)); cams.objects.link(cam); cam.data.clip_end = 400
    cam.animation_data_clear(); cam.data.animation_data_clear()
    f0, f1 = int(t0 * FPS) + 1, int(t1 * FPS)
    for f in range(f0, f1 + 1):
        t = (f - 1) / FPS; u = (t - t0) / (t1 - t0)
        loc, look, lens = fn(t, u)
        cam.location = loc; cam.rotation_euler = (look - loc).to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = lens
        cam.keyframe_insert("location", frame=f); cam.keyframe_insert("rotation_euler", frame=f)
        cam.data.keyframe_insert("lens", frame=f)
    sc.timeline_markers.new(name, frame=f0).camera = cam
    print("SHOT", name, f0, f1, "frames", f1 - f0 + 1)
sc.camera = bpy.data.objects["S1_Establish"]
# colour render for the video-to-video AI pass (rendered on a RunPod GPU): same size as the Wan generation, 2.2:1 phone shape
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 960, 432, 100
sc.render.image_settings.file_format = "JPEG"; sc.render.image_settings.quality = 95
sc.eevee.taa_render_samples = 16      # user 2026-11-17: 16 next time (64 = ~1 frame/s on a 4090; Wan repaints at ~0.5 strength anyway)
print("CAR y start %.1f, stop %.1f, end %.1f" % (car_y(0), car_y(30), car_y(60)))
bpy.ops.wm.save_as_mainfile(filepath=HERE + "/car_street_anim.blend", compress=True)
print("SAVED anim")
