"""Ripple: overlap and earthquake tools for Maya.

Ripple tab:  pass a driver object's animation to other selected objects,
             each one later (delay) and weaker (falloff).
Seismic tab: shatter the ground around an epicenter, then send P and S
             waves outward so the ground shakes and cracks open, starting
             at the epicenter and spreading out.

Run in Maya's Script Editor (Python tab), as ONE line:
    import sys, importlib; sys.path.append(r"E:\\pfa-midterm"); import ripple; importlib.reload(ripple); ripple.show()
"""

import json
import math
import os
import random

import maya.cmds as cmds
import maya.OpenMayaUI as omui

try:  # Maya 2025+
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:  # Maya 2024 and earlier
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance


# ==========================================================================
# Shared helpers
# ==========================================================================

OPTION_PREFIX = "ripple_"  # Maya optionVar names, remembered between sessions


def maya_main_window():
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget)


def world_pos(obj):
    return cmds.xform(obj, query=True, worldSpace=True, translation=True)


def make_slider(label, lo, hi, value, fmt=str):
    """A labelled slider with a live readout. Returns (slider, row layout)."""
    row = QtWidgets.QHBoxLayout()
    name = QtWidgets.QLabel(label)
    name.setMinimumWidth(130)
    slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    slider.setRange(lo, hi)
    slider.setValue(value)
    readout = QtWidgets.QLabel(fmt(value))
    readout.setMinimumWidth(60)
    slider.valueChanged.connect(lambda v: readout.setText(fmt(v)))
    row.addWidget(name)
    row.addWidget(slider, 1)
    row.addWidget(readout)
    return slider, row


def say(label, text, error=False):
    color = "#e57373" if error else "#c8c8c8"
    label.setText('<span style="color:{}">{}</span>'.format(color, text))


def load_option(key):
    key = OPTION_PREFIX + key
    if cmds.optionVar(exists=key):
        try:
            return json.loads(cmds.optionVar(query=key))
        except ValueError:
            return None
    return None


def save_option(key, data):
    cmds.optionVar(stringValue=(OPTION_PREFIX + key, json.dumps(data)))


# ==========================================================================
# RIPPLE: core logic
# ==========================================================================

CHANNELS = {
    "Translate": ["translateX", "translateY", "translateZ"],
    "Rotate": ["rotateX", "rotateY", "rotateZ"],
    "Scale": ["scaleX", "scaleY", "scaleZ"],
}

ORDERS = ["Selection order", "Distance from driver", "Left to right (X)"]

BUILTIN_PRESETS = {
    "Floppy Tail":  {"delay": 4, "falloff": 85, "order": 0, "channels": ["Rotate"]},
    "Wave Pop":     {"delay": 3, "falloff": 90, "order": 1, "channels": ["Translate", "Scale"]},
    "Domino Spin":  {"delay": 5, "falloff": 100, "order": 2, "channels": ["Rotate"]},
    "Heavy Rope":   {"delay": 8, "falloff": 60, "order": 0, "channels": ["Translate", "Rotate"]},
}


def sort_followers(driver, followers, order):
    """Return followers in ripple order: 0 selection, 1 distance, 2 left-to-right."""
    if order == 1:
        d = world_pos(driver)
        return sorted(followers, key=lambda o: sum((a - b) ** 2 for a, b in zip(world_pos(o), d)))
    if order == 2:
        return sorted(followers, key=lambda o: world_pos(o)[0])
    return list(followers)


def ripple_apply(driver, followers, attrs, delay, falloff, chunk_name="Ripple"):
    """Copy the driver's change in motion onto each follower.

    Each follower keeps its own starting value and adds the driver's change,
    scaled by falloff ** step and shifted later by delay * step frames.
    Everything happens inside one undo chunk. Returns a list of warnings.
    """
    warnings = []
    used_any = False
    cmds.undoInfo(openChunk=True, chunkName=chunk_name)
    try:
        for attr in attrs:
            times = cmds.keyframe(driver, attribute=attr, query=True, timeChange=True)
            if not times:
                continue
            values = cmds.keyframe(driver, attribute=attr, query=True, valueChange=True)
            in_tan = cmds.keyTangent(driver, attribute=attr, query=True, inTangentType=True) or []
            out_tan = cmds.keyTangent(driver, attribute=attr, query=True, outTangentType=True) or []
            base = values[0]
            used_any = True

            for step, obj in enumerate(followers, start=1):
                plug = "{}.{}".format(obj, attr)
                if not cmds.attributeQuery(attr, node=obj, exists=True):
                    continue
                if cmds.getAttr(plug, lock=True):
                    warnings.append("{} is locked, skipped".format(plug))
                    continue

                rest = cmds.getAttr(plug, time=times[0])
                strength = falloff ** step
                cmds.cutKey(obj, attribute=attr, clear=True)
                for i, (t, v) in enumerate(zip(times, values)):
                    new_t = t + delay * step
                    cmds.setKeyframe(obj, attribute=attr, time=new_t,
                                     value=rest + (v - base) * strength)
                    if i < len(in_tan) and i < len(out_tan):
                        try:  # copy the driver's tangent types (spline, linear, ...)
                            cmds.keyTangent(obj, attribute=attr, time=(new_t, new_t),
                                            inTangentType=in_tan[i], outTangentType=out_tan[i])
                        except RuntimeError:
                            pass
    finally:
        cmds.undoInfo(closeChunk=True)

    if not used_any:
        raise ValueError("The driver has no keys on the checked channels.")
    return warnings


def driver_curve(driver, attrs):
    """Return [(frame, value), ...] for the first animated channel, or None."""
    for attr in attrs:
        times = cmds.keyframe(driver, attribute=attr, query=True, timeChange=True)
        if times and len(times) > 1:
            values = cmds.keyframe(driver, attribute=attr, query=True, valueChange=True)
            if max(values) != min(values):
                return list(zip(times, values))
    return None


def user_preset_path():
    return os.path.join(cmds.internalVar(userAppDir=True), "ripple_presets.json")


def load_user_presets():
    try:
        with open(user_preset_path(), "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (IOError, OSError, ValueError):
        return {}


def save_user_presets(presets):
    with open(user_preset_path(), "w") as f:
        json.dump(presets, f, indent=2)


# ==========================================================================
# SEISMIC: shatter geometry (pure maths, no Maya)
# ==========================================================================

EPICENTER = "seismic_epicenter"
GROUND_GRP = "seismic_ground_grp"


def clip_half_plane(poly, nx, nz, c):
    """Keep the part of a 2D polygon [(x, z), ...] where nx*x + nz*z <= c."""
    out = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        fp = nx * p[0] + nz * p[1]
        fq = nx * q[0] + nz * q[1]
        p_in, q_in = fp <= c, fq <= c
        if p_in:
            out.append(p)
        if p_in != q_in:
            t = (c - fp) / (fq - fp)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def voronoi_cells(seeds, half):
    """Split the square [-half, half] x [-half, half] into one cell per seed.

    Each cell is the area closer to its seed than to any other seed, so the
    cells fit together exactly, like cracked ground.
    """
    square = [(-half, -half), (half, -half), (half, half), (-half, half)]
    cells = []
    for i, (sx, sz) in enumerate(seeds):
        poly = square
        # nearest seeds first; once the next seed is more than twice as far
        # as the cell's farthest corner, no later seed can cut the cell
        others = sorted(((tx - sx) ** 2 + (tz - sz) ** 2, tx, tz)
                        for j, (tx, tz) in enumerate(seeds) if j != i)
        reach2 = max((x - sx) ** 2 + (z - sz) ** 2 for x, z in poly)
        for dist2, tx, tz in others:
            if dist2 > 4.0 * reach2:
                break
            nx, nz = tx - sx, tz - sz
            mx, mz = (sx + tx) / 2.0, (sz + tz) / 2.0
            poly = clip_half_plane(poly, nx, nz, nx * mx + nz * mz)
            if len(poly) < 3:
                break
            reach2 = max((x - sx) ** 2 + (z - sz) ** 2 for x, z in poly)
        cells.append(poly)
    return cells


def make_terrain(height, size, seed):
    """Land with rolling hills, valleys and a few rocky ridges: returns h(x, z).

    Layers of smooth waves (wide hills down to small bumps, each in a random
    direction) plus sharp-topped ridges, so the land is uneven like real
    ground but not jagged.
    """
    rng = random.Random(seed * 7919 + 13)
    waves = []
    for wavelength, amp in ((1.0, 1.0), (0.5, 0.45), (0.25, 0.18), (0.12, 0.07)):
        for _ in range(2):
            a = rng.uniform(0, 2 * math.pi)
            f = 2 * math.pi / (wavelength * size)
            waves.append((f * math.cos(a), f * math.sin(a), rng.uniform(0, 2 * math.pi), amp))
    total = sum(w[3] for w in waves)
    ra = rng.uniform(0, 2 * math.pi)
    rf = 2 * math.pi / (0.35 * size)
    rfx, rfz, rph = rf * math.cos(ra), rf * math.sin(ra), rng.uniform(0, 2 * math.pi)
    mask_a = rng.uniform(0, 2 * math.pi)
    mf = 2 * math.pi / (0.8 * size)
    mfx, mfz = mf * math.cos(mask_a), mf * math.sin(mask_a)

    def h(x, z):
        n = sum(a * math.sin(fx * x + fz * z + ph) for fx, fz, ph, a in waves) / total
        ridge = (1.0 - abs(math.sin(rfx * x + rfz * z + rph))) ** 3     # sharp crests
        mask = max(0.0, math.sin(mfx * x + mfz * z + 1.0))               # ridges only in some areas
        return height * (1.3 * n + 0.6 * ridge * mask)

    return h


def terrain_slope(h, x, z, step=0.5):
    gx = (h(x + step, z) - h(x - step, z)) / (2 * step)
    gz = (h(x, z + step) - h(x, z - step)) / (2 * step)
    return math.hypot(gx, gz)


# ---- faults ---------------------------------------------------------------

def build_faults(epi, count, length, seed):
    """Jagged cracks running outward from the epicenter, plus side branches.

    Returns a list of faults: {"pts": [(x, z), ...], "L": length, "main": bool}.
    Main faults split the land into plates; branches only make trenches.
    """
    rng = random.Random(seed * 31 + 7)
    faults = []
    base = rng.uniform(0, 2 * math.pi)
    steps = 24
    for i in range(count):
        ang = base + 2 * math.pi * i / count + rng.uniform(-0.3, 0.3) * (2 * math.pi / count)
        L = length * rng.uniform(0.8, 1.1)
        pts, a = [tuple(epi)], ang
        x, z = epi
        for _ in range(steps):
            a = ang + max(-0.55, min(0.55, a - ang + rng.gauss(0, 0.28)))
            x += L / steps * math.cos(a)
            z += L / steps * math.sin(a)
            pts.append((x, z))
        faults.append({"pts": pts, "L": L, "main": True, "angle": ang})
    for f in [f for f in faults if f["main"]]:
        if rng.random() > 0.75:
            continue
        k = rng.randint(5, 15)
        bx, bz = f["pts"][k]
        a = f["angle"] + rng.choice((-1, 1)) * rng.uniform(0.5, 0.95)
        BL = f["L"] * rng.uniform(0.2, 0.4)
        pts = [(bx, bz)]
        b = a
        for _ in range(10):
            b = a + max(-0.5, min(0.5, b - a + rng.gauss(0, 0.3)))
            bx += BL / 10 * math.cos(b)
            bz += BL / 10 * math.sin(b)
            pts.append((bx, bz))
        faults.append({"pts": pts, "L": BL, "main": False, "angle": a, "start": k / float(steps)})
    return faults


def fault_hit(x, z, f):
    """Distance from (x, z) to the fault line, and how far along it (0..1)."""
    best, best_s, run = 1e18, 0.0, 0.0
    pts = f["pts"]
    total = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1))
    for i in range(len(pts) - 1):
        (ax, az), (bx, bz) = pts[i], pts[i + 1]
        dx, dz = bx - ax, bz - az
        seg = math.hypot(dx, dz)
        t = 0.0 if seg < 1e-9 else max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / (seg * seg)))
        d = math.hypot(x - (ax + t * dx), z - (az + t * dz))
        if d < best:
            best, best_s = d, (run + t * seg) / max(total, 1e-9)
        run += seg
    return best, best_s


def rift_width(f, s, width):
    """Rifts are widest at the epicenter and narrow toward their tips."""
    w = width * (0.25 + 0.75 * (1.0 - s))
    if not f["main"]:
        w *= 0.5 * (1.0 - 0.5 * f.get("start", 0.5))
    return w


def in_rift(x, z, faults, width):
    for f in faults:
        d, s = fault_hit(x, z, f)
        if d < rift_width(f, s, width):
            return True
    return False


def fault_angle_at(f, epi, r):
    """Direction (angle) of a fault seen from the epicenter, at distance r."""
    ex, ez = epi
    pts = f["pts"]
    prev = pts[0]
    for p in pts[1:]:
        rp = math.hypot(p[0] - ex, p[1] - ez)
        if rp >= r:
            r0 = math.hypot(prev[0] - ex, prev[1] - ez)
            t = 0.0 if rp - r0 < 1e-9 else (r - r0) / (rp - r0)
            x = prev[0] + t * (p[0] - prev[0])
            z = prev[1] + t * (p[1] - prev[1])
            if math.hypot(x - ex, z - ez) < 1e-6:
                return f["angle"]
            return math.atan2(z - ez, x - ex)
        prev = p
    return math.atan2(pts[-1][1] - ez, pts[-1][0] - ex)


def wedge_of(x, z, epi, mains):
    """Which plate (between which two main faults) a point belongs to."""
    r = math.hypot(x - epi[0], z - epi[1])
    phi = math.atan2(z - epi[1], x - epi[0])
    angles = [fault_angle_at(f, epi, r) for f in mains]
    n = len(mains)
    two_pi = 2 * math.pi
    for k in range(n):
        a0, a1 = angles[k], angles[(k + 1) % n]
        span = (a1 - a0) % two_pi
        if (phi - a0) % two_pi < span:
            return k
    return min(range(n), key=lambda k: abs(((phi - angles[k] + math.pi) % two_pi) - math.pi))


def ground_seeds(half, count, faults, width, epi, seed, inside=None, grain=1.0):
    """Crack points: packed tight inside the rifts (rubble), loose elsewhere."""
    rng = random.Random(seed * 101 + 3)
    seeds = []
    spacing = max(width * 0.25 * grain, 0.25)  # rubble: small broken pieces
    for f in faults:
        pts = f["pts"]
        for i in range(len(pts) - 1):
            (ax, az), (bx, bz) = pts[i], pts[i + 1]
            seg = math.hypot(bx - ax, bz - az)
            if seg < 1e-9:
                continue
            nx, nz = -(bz - az) / seg, (bx - ax) / seg
            for k in range(max(1, int(seg / spacing))):
                t = (k + rng.random()) * spacing / seg
                if t > 1:
                    break
                px, pz = ax + t * (bx - ax), az + t * (bz - az)
                s = (i + t) / float(len(pts) - 1)
                w = rift_width(f, s, width)
                o = -w
                while o <= w:
                    x = px + nx * (o + rng.uniform(-0.3, 0.3) * spacing)
                    z = pz + nz * (o + rng.uniform(-0.3, 0.3) * spacing)
                    if abs(x) < half * 0.995 and abs(z) < half * 0.995:
                        seeds.append((x, z))
                    o += spacing
    base, gap2 = [], (half * 2.0 / math.sqrt(max(count, 1)) * 0.5) ** 2
    tries = 0
    while len(base) < count and tries < count * 40:
        tries += 1
        x, z = rng.uniform(-half, half), rng.uniform(-half, half)
        if inside is not None and not inside(x, z):
            continue
        if in_rift(x, z, faults, width * 1.1):
            continue
        if all((x - bx) ** 2 + (z - bz) ** 2 >= gap2 for bx, bz in base):
            base.append((x, z))
    return seeds + base


# ---- Manhattan -------------------------------------------------------------

# A simplified outline of Manhattan, south (the Battery) to north (Inwood):
# (how far along the island 0..1, west shore, east shore), as fractions of
# the island's length. Widest around 14th Street, narrow in the north.
MANHATTAN_ROWS = [
    (0.00, 0.000, 0.000), (0.015, -0.028, 0.022), (0.04, -0.050, 0.050), (0.08, -0.064, 0.078),
    (0.13, -0.072, 0.094), (0.18, -0.076, 0.098), (0.24, -0.074, 0.080), (0.32, -0.070, 0.068),
    (0.42, -0.068, 0.062), (0.52, -0.064, 0.060), (0.62, -0.060, 0.056), (0.72, -0.056, 0.048),
    (0.80, -0.050, 0.034), (0.87, -0.044, 0.020), (0.93, -0.036, 0.012), (0.97, -0.024, 0.012),
    (1.00, -0.004, 0.004),
]
GRID_ANGLE = 29.0  # Manhattan's street grid runs 29 degrees east of true north

# Manhattan's real shoreline (latitude, longitude), clockwise from the Battery:
# up the Hudson, round Inwood, down the Harlem and East River.
MANHATTAN_LATLON = [
    (40.7005, -74.0135), (40.7035, -74.0180), (40.7075, -74.0192), (40.7120, -74.0170), (40.7170, -74.0150),
    (40.7230, -74.0125), (40.7300, -74.0118), (40.7370, -74.0110), (40.7420, -74.0100), (40.7480, -74.0088),
    (40.7570, -74.0055), (40.7620, -74.0018), (40.7720, -73.9945), (40.7810, -73.9895), (40.7900, -73.9835),
    (40.7990, -73.9775), (40.8080, -73.9705), (40.8190, -73.9615), (40.8270, -73.9560), (40.8340, -73.9520),
    (40.8430, -73.9490), (40.8513, -73.9470), (40.8600, -73.9370), (40.8660, -73.9325), (40.8710, -73.9300),
    (40.8755, -73.9265), (40.8762, -73.9190), (40.8742, -73.9128), (40.8680, -73.9150), (40.8612, -73.9192),
    (40.8540, -73.9245), (40.8450, -73.9300), (40.8360, -73.9338), (40.8275, -73.9358), (40.8190, -73.9362),
    (40.8125, -73.9366), (40.8062, -73.9335), (40.8010, -73.9298), (40.7960, -73.9295), (40.7905, -73.9360),
    (40.7860, -73.9402), (40.7790, -73.9432), (40.7720, -73.9472), (40.7640, -73.9540), (40.7560, -73.9620),
    (40.7490, -73.9682), (40.7420, -73.9722), (40.7340, -73.9742), (40.7260, -73.9722), (40.7180, -73.9732),
    (40.7110, -73.9782), (40.7090, -73.9915), (40.7068, -74.0000), (40.7045, -74.0055), (40.7025, -74.0098),
]
CENTRAL_PARK_LATLON = [(40.7644, -73.9730), (40.7681, -73.9819), (40.8003, -73.9580), (40.7968, -73.9493)]


def point_in_poly(x, z, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, zi = poly[i]
        xj, zj = poly[j]
        if (zi > z) != (zj > z) and x < (xj - xi) * (z - zi) / (zj - zi) + xi:
            inside = not inside
        j = i
    return inside


def manhattan_frame(size):
    """Everything about the island at this size. Its long side is the ground
    size, turned 29 degrees like the real grid (north is -Z, east is +X).
    Returns a dict of helpers."""
    a = math.radians(GRID_ANGLE)
    up = (math.sin(a), -math.cos(a))      # south -> north along the island
    east = (math.cos(a), math.sin(a))     # west -> east across it
    L = float(size)

    def to_world(u, w):
        return ((u - 0.5) * L * up[0] + w * L * east[0], (u - 0.5) * L * up[1] + w * L * east[1])

    def to_island(x, z):
        return (x * up[0] + z * up[1]) / L + 0.5, (x * east[0] + z * east[1]) / L

    outline = [to_world(*latlon_to_island(lat, lon)) for lat, lon in MANHATTAN_LATLON]
    park = [to_world(*latlon_to_island(lat, lon)) for lat, lon in CENTRAL_PARK_LATLON]

    def inside(x, z):
        return point_in_poly(x, z, outline)

    def in_park(x, z):  # Central Park: 59th to 110th Street, between 5th and 8th Avenue
        return point_in_poly(x, z, park)

    return {"L": L, "up": up, "east": east, "to_world": to_world, "to_island": to_island,
            "outline": outline, "inside": inside, "in_park": in_park, "rotate_y": -GRID_ANGLE}


def island_seeds(frame, count, seed, grain=1.0):
    """Extra seeds so the land's edge follows the coast: pairs just inside and
    just outside the shoreline, and loose water seeds further out."""
    rng = random.Random(seed * 71 + 5)
    outline = frame["outline"]
    L = frame["L"]
    spacing = max(L / 110.0 * grain, 0.4)
    land, water = [], []
    n = len(outline)
    for i in range(n):
        (ax, az), (bx, bz) = outline[i], outline[(i + 1) % n]
        seg = math.hypot(bx - ax, bz - az)
        if seg < 1e-9:
            continue
        nx, nz = (bz - az) / seg, -(bx - ax) / seg
        for k in range(max(1, int(seg / spacing))):
            t = (k + 0.5) * spacing / seg
            if t > 1:
                break
            px, pz = ax + t * (bx - ax), az + t * (bz - az)
            for sign, bucket in ((1, water), (-1, land)):
                x, z = px + sign * nx * spacing * 0.5, pz + sign * nz * spacing * 0.5
                if frame["inside"](x, z) == (sign < 0):
                    bucket.append((x, z))
    half = L / 2.0
    tries = 0
    while len(water) < count // 3 + 40 and tries < count * 20:
        tries += 1
        x, z = rng.uniform(-half, half), rng.uniform(-half, half)
        if not frame["inside"](x, z):
            water.append((x, z))
    return land, water


# ---- the other four boroughs -------------------------------------------------

BATTERY_LATLON = (40.7033, -74.0170)

# Simplified outlines (latitude, longitude), traced roughly from real maps.
# where Brooklyn meets Queens, from Newtown Creek to Jamaica Bay
BK_QN_BORDER = [(40.7372, -73.9615), (40.7350, -73.9500), (40.7290, -73.9370), (40.7210, -73.9250),
                (40.7130, -73.9200), (40.7040, -73.9120), (40.6960, -73.9010), (40.6900, -73.8880),
                (40.6830, -73.8760), (40.6720, -73.8660), (40.6580, -73.8610), (40.6480, -73.8620)]

# Real shorelines (latitude, longitude), traced from maps of New York City.
BOROUGH_LATLON = {
    "bronx": [
        (40.9120, -73.9190), (40.9150, -73.9000), (40.9170, -73.8780), (40.9150, -73.8620), (40.9050, -73.8530),
        (40.8950, -73.8390), (40.8850, -73.8270), (40.8800, -73.8150), (40.8880, -73.7980), (40.8800, -73.7870),
        (40.8650, -73.7950), (40.8580, -73.8040), (40.8450, -73.8100), (40.8300, -73.8070), (40.8180, -73.7950),
        (40.8050, -73.7920), (40.8080, -73.8150), (40.8115, -73.8320), (40.8130, -73.8450), (40.8050, -73.8600),
        (40.8145, -73.8720), (40.8040, -73.8800), (40.8020, -73.8950), (40.7990, -73.9080), (40.8030, -73.9230),
        (40.8085, -73.9290), (40.8140, -73.9318), (40.8215, -73.9320), (40.8300, -73.9310), (40.8380, -73.9290),
        (40.8475, -73.9255), (40.8560, -73.9200), (40.8635, -73.9135), (40.8700, -73.9100), (40.8772, -73.9105),
        (40.8792, -73.9210), (40.8815, -73.9265), (40.8920, -73.9215), (40.9030, -73.9185)],
    "queens": [BK_QN_BORDER[0]] + [
        (40.7450, -73.9600), (40.7530, -73.9530), (40.7620, -73.9430), (40.7700, -73.9370), (40.7765, -73.9330),
        (40.7800, -73.9230), (40.7840, -73.9120), (40.7790, -73.8920), (40.7850, -73.8800), (40.7810, -73.8640),
        (40.7700, -73.8580), (40.7620, -73.8500), (40.7680, -73.8400), (40.7800, -73.8450), (40.7880, -73.8450),
        (40.7960, -73.8250), (40.7940, -73.8000), (40.7930, -73.7770), (40.7750, -73.7720), (40.7650, -73.7620),
        (40.7620, -73.7530), (40.7740, -73.7460), (40.7600, -73.7300), (40.7490, -73.7010), (40.7270, -73.7060),
        (40.7130, -73.7280), (40.6900, -73.7280), (40.6640, -73.7300), (40.6520, -73.7380), (40.6440, -73.7470),
        (40.6280, -73.7680), (40.6250, -73.7800), (40.6350, -73.8020), (40.6500, -73.8100), (40.6530, -73.8350),
        (40.6520, -73.8500)] + BK_QN_BORDER[::-1][:-1],
    "brooklyn": BK_QN_BORDER + [
        (40.6380, -73.8740), (40.6300, -73.8820), (40.6200, -73.8930), (40.6100, -73.9050), (40.5960, -73.8920),
        (40.5850, -73.8950), (40.5820, -73.9100), (40.5830, -73.9250), (40.5770, -73.9400), (40.5750, -73.9600),
        (40.5720, -73.9850), (40.5760, -74.0110), (40.5850, -74.0000), (40.5950, -74.0000), (40.6010, -74.0130),
        (40.6080, -74.0350), (40.6200, -74.0420), (40.6350, -74.0380), (40.6480, -74.0230), (40.6560, -74.0180),
        (40.6680, -74.0130), (40.6720, -74.0190), (40.6800, -74.0130), (40.6910, -74.0020), (40.6970, -73.9990),
        (40.7040, -73.9900), (40.7010, -73.9760), (40.7060, -73.9740), (40.7120, -73.9690), (40.7200, -73.9620),
        (40.7300, -73.9610)],
    "rockaway": [
        (40.5540, -73.9370), (40.5590, -73.9100), (40.5670, -73.8800), (40.5760, -73.8500), (40.5810, -73.8200),
        (40.5850, -73.7900), (40.5920, -73.7600), (40.5960, -73.7400), (40.6050, -73.7450), (40.6000, -73.7650),
        (40.5960, -73.7900), (40.5920, -73.8150), (40.5860, -73.8450), (40.5780, -73.8750), (40.5700, -73.9000),
        (40.5620, -73.9250)],
    "staten": [
        (40.6440, -74.0750), (40.6450, -74.0900), (40.6410, -74.1100), (40.6400, -74.1300), (40.6430, -74.1500),
        (40.6420, -74.1700), (40.6380, -74.1850), (40.6250, -74.1950), (40.6050, -74.2000), (40.5800, -74.2050),
        (40.5600, -74.2150), (40.5450, -74.2250), (40.5250, -74.2400), (40.5100, -74.2520), (40.4990, -74.2550),
        (40.5050, -74.2250), (40.5150, -74.2000), (40.5250, -74.1750), (40.5350, -74.1500), (40.5450, -74.1300),
        (40.5550, -74.1100), (40.5680, -74.0920), (40.5800, -74.0730), (40.5950, -74.0600), (40.6050, -74.0530),
        (40.6150, -74.0620), (40.6300, -74.0700), (40.6400, -74.0720)],
}
JOINED = {("brooklyn", "queens"), ("queens", "brooklyn")}  # share a land border, no river

# what each borough is like: building mix, height range (share of Manhattan's
# length), how far apart the lots are (share of Manhattan's), and taller centres
BOROUGH_STYLE = {
    "bronx":    {"kinds": ("brick1", "brick2", "stone2", "stone1"), "h": (0.004, 0.011), "spacing": 1.7,
                 "centres": []},
    "queens":   {"kinds": ("brick2", "stone2", "brick1"), "h": (0.003, 0.008), "spacing": 2.0,
                 "centres": [((40.747, -73.945), 0.05, (0.015, 0.032), ("glass1", "glass2", "glass3")),   # Long Island City
                             ((40.758, -73.830), 0.04, (0.009, 0.018), ("stone1", "glass3"))]},          # Flushing
    "brooklyn": {"kinds": ("brick1", "brick2", "brick1", "stone2"), "h": (0.004, 0.010), "spacing": 1.8,
                 "centres": [((40.693, -73.988), 0.055, (0.014, 0.030), ("glass1", "glass2", "setback"))]},  # Downtown Brooklyn
    "staten":   {"kinds": ("house",), "h": (0.0018, 0.0035), "spacing": 2.2, "trees": 0.55, "centres": []},
    "rockaway": {"kinds": ("house", "house", "brick1", "stone2"), "h": (0.0030, 0.0070), "spacing": 0.9, "trees": 0.15,
                 "centres": []},
}


def latlon_to_island(lat, lon):
    """Real map position -> Manhattan's (along, across) frame, Battery at 0, 0."""
    dn = (lat - BATTERY_LATLON[0]) * 111.0
    de = (lon - BATTERY_LATLON[1]) * 84.1
    a = math.radians(GRID_ANGLE)
    along = dn * math.cos(a) + de * math.sin(a)
    across = de * math.cos(a) - dn * math.sin(a)
    return along / MANHATTAN_KM, across / MANHATTAN_KM


MANHATTAN_KM = 21.6


def poly_area(poly):
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))) / 2.0


def dist_to_poly(x, z, poly):
    best = 1e18
    n = len(poly)
    for i in range(n):
        (ax, az), (bx, bz) = poly[i], poly[(i + 1) % n]
        dx, dz = bx - ax, bz - az
        seg2 = dx * dx + dz * dz
        t = 0.0 if seg2 < 1e-12 else max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / seg2))
        best = min(best, math.hypot(x - ax - t * dx, z - az - t * dz))
    return best


def nearest_on_poly(x, z, poly):
    """The closest point on a polygon's edge to (x, z), and how far it is."""
    best = (x, z, 1e18)
    n = len(poly)
    for i in range(n):
        (ax, az), (bx, bz) = poly[i], poly[(i + 1) % n]
        dx, dz = bx - ax, bz - az
        seg2 = dx * dx + dz * dz
        t = 0.0 if seg2 < 1e-12 else max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / seg2))
        px, pz = ax + t * dx, az + t * dz
        d = math.hypot(x - px, z - pz)
        if d < best[2]:
            best = (px, pz, d)
    return best


def clip_to_land(cell, land_poly):
    """The part of a land outline inside one (convex) crack cell."""
    n = len(cell)
    cx = sum(p[0] for p in cell) / n
    cz = sum(p[1] for p in cell) / n
    out = land_poly
    for i in range(n):
        (ax, az), (bx, bz) = cell[i], cell[(i + 1) % n]
        nx, nz = bz - az, -(bx - ax)
        c = nx * ax + nz * az
        if nx * cx + nz * cz > c:  # point the test so the cell's centre is kept
            nx, nz, c = -nx, -nz, -c
        out = clip_half_plane(out, nx, nz, c)
        if len(out) < 3:
            return []
    return out


def cells_on_land(cells, lands):
    """Cut the crack cells to the real coastlines: every piece of ground is
    exactly the land inside its cell, so shores and rivers are crisp."""
    out = []
    for cell in cells:
        if len(cell) < 3:
            continue
        xs = [p[0] for p in cell]
        zs = [p[1] for p in cell]
        x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
        for land in lands:
            lx0, lx1, lz0, lz1 = land["box"]
            if x1 < lx0 or x0 > lx1 or z1 < lz0 or z0 > lz1:
                continue
            ins = [point_in_poly(x, z, land["poly"]) for x, z in cell]
            corner_in = any(x0 <= x <= x1 and z0 <= z <= z1 for x, z in land["poly"])
            if all(ins) and not corner_in:
                out.append(cell)
            elif any(ins) or corner_in:
                piece = clip_to_land(cell, land["poly"])
                if len(piece) >= 3 and poly_area(piece) > max(0.05 * poly_area(cell), 0.25):
                    out.append(piece)
    return out


def nyc_world(size, boroughs=True):
    """Manhattan plus (optionally) the Bronx, Queens, Brooklyn and Staten
    Island, all in one frame. The boroughs come from real map positions; any
    of their corners that would touch our simplified Manhattan are pushed
    back so a river always runs between them."""
    world = dict(manhattan_frame(size))
    L = world["L"]
    lands = [{"name": "manhattan", "poly": world["outline"]}]
    if boroughs:
        gap = L * 0.02    # the narrowest river (the Harlem), a little wider than life so it reads
        for name, pts in BOROUGH_LATLON.items():
            poly = []
            for lat, lon in pts:
                x, z = world["to_world"](*latlon_to_island(lat, lon))
                for other in lands:  # keep a river between this borough and the ones already placed
                    if (name, other["name"]) in JOINED:
                        continue
                    for _ in range(40):
                        nx, nz, d = nearest_on_poly(x, z, other["poly"])
                        if d >= gap and not point_in_poly(x, z, other["poly"]):
                            break
                        dx, dz = x - nx, z - nz
                        if point_in_poly(x, z, other["poly"]):
                            dx, dz = -dx, -dz
                        n = math.hypot(dx, dz) or 1.0
                        x, z = nx + dx / n * gap * 1.02, nz + dz / n * gap * 1.02
                poly.append((x, z))
            lands.append({"name": name, "poly": poly})
    for land in lands:
        xs = [p[0] for p in land["poly"]]
        zs = [p[1] for p in land["poly"]]
        land["box"] = (min(xs), max(xs), min(zs), max(zs))
        land["area"] = poly_area(land["poly"])

    def land_at(x, z):
        for land in lands:
            x0, x1, z0, z1 = land["box"]
            if x0 <= x <= x1 and z0 <= z <= z1 and point_in_poly(x, z, land["poly"]):
                return land["name"]
        return None

    xs = [b for land in lands for b in land["box"][:2]]
    zs = [b for land in lands for b in land["box"][2:]]
    margin = L * 0.25
    world.update({"lands": lands, "land_at": land_at,
                  "inside_any": lambda x, z: land_at(x, z) is not None,
                  "box": (min(xs) - margin, max(xs) + margin, min(zs) - margin, max(zs) + margin)})
    return world


def voronoi_cells_box(seeds, box):
    """Like voronoi_cells, inside a rectangle, and fast for thousands of
    seeds: each cell only looks at seeds in nearby grid buckets."""
    x0, x1, z0, z1 = box
    n = max(len(seeds), 1)
    bucket = math.sqrt((x1 - x0) * (z1 - z0) / n) * 1.5
    grid = {}
    for i, (sx, sz) in enumerate(seeds):
        grid.setdefault((int((sx - x0) // bucket), int((sz - z0) // bucket)), []).append(i)
    rect = [(x0, z0), (x1, z0), (x1, z1), (x0, z1)]
    cells = []
    for i, (sx, sz) in enumerate(seeds):
        bx, bz = int((sx - x0) // bucket), int((sz - z0) // bucket)
        poly = rect
        done = set([i])
        ring = 0
        while True:
            cand = []
            for gx in range(bx - ring, bx + ring + 1):
                for gz in range(bz - ring, bz + ring + 1):
                    if max(abs(gx - bx), abs(gz - bz)) != ring:
                        continue
                    for j in grid.get((gx, gz), ()):
                        if j not in done:
                            done.add(j)
                            tx, tz = seeds[j]
                            cand.append(((tx - sx) ** 2 + (tz - sz) ** 2, tx, tz))
            for d2, tx, tz in sorted(cand):
                nx, nz = tx - sx, tz - sz
                poly = clip_half_plane(poly, nx, nz, nx * (sx + tx) / 2.0 + nz * (sz + tz) / 2.0)
                if len(poly) < 3:
                    break
            if len(poly) < 3:
                break
            reach2 = max((x - sx) ** 2 + (z - sz) ** 2 for x, z in poly)
            covered = ring * bucket  # every seed closer than this has been used
            if 4.0 * reach2 <= covered * covered or ring > 60:
                break
            ring += 1
        cells.append(poly)
    return cells


def borough_seeds(world, count, seed, grain=1.0):
    """Crack points for the boroughs: about a ninth as dense as Manhattan
    (bigger pieces), so the whole city stays light enough to animate."""
    rng = random.Random(seed * 59 + 21)
    man_area = world["lands"][0]["area"]
    out = []
    for land in world["lands"][1:]:
        n = int(count * land["area"] / man_area / 12.0)
        x0, x1, z0, z1 = land["box"]
        gap = math.sqrt(land["area"] / max(n, 1)) * 0.5
        grid, tries = {}, 0
        made = 0
        while made < n and tries < n * 30:
            tries += 1
            x, z = rng.uniform(x0, x1), rng.uniform(z0, z1)
            if not point_in_poly(x, z, land["poly"]):
                continue
            gx, gz = int(x // gap), int(z // gap)
            if any((x - a) ** 2 + (z - b) ** 2 < gap * gap
                   for i in (-1, 0, 1) for j in (-1, 0, 1) for a, b in grid.get((gx + i, gz + j), ())):
                continue
            grid.setdefault((gx, gz), []).append((x, z))
            out.append((x, z))
            made += 1
    return out


def coast_seeds(world, count, seed, grain=1.0):
    """Seeds just inside and just outside every shore, so each landmass's
    edge follows its coast, plus loose water seeds around the city."""
    rng = random.Random(seed * 71 + 5)
    L = world["L"]
    land_seeds, water = [], []
    for land in world["lands"]:
        spacing = max(L / (110.0 if land["name"] == "manhattan" else 60.0) * grain, 0.4)
        poly = land["poly"]
        n = len(poly)
        for i in range(n):
            (ax, az), (bx, bz) = poly[i], poly[(i + 1) % n]
            seg = math.hypot(bx - ax, bz - az)
            if seg < 1e-9:
                continue
            nx, nz = (bz - az) / seg, -(bx - ax) / seg
            for k in range(max(1, int(seg / spacing))):
                t = (k + 0.5) * spacing / seg
                if t > 1:
                    break
                px, pz = ax + t * (bx - ax), az + t * (bz - az)
                for sign in (1, -1):
                    x, z = px + sign * nx * spacing * 0.5, pz + sign * nz * spacing * 0.5
                    here = world["land_at"](x, z)
                    if here == land["name"]:
                        if land["name"] == "manhattan":
                            land_seeds.append((x, z))
                    elif here is None:
                        water.append((x, z))
    x0, x1, z0, z1 = world["box"]
    tries = 0
    while len(water) < count // 2 + 300 and tries < count * 40:
        tries += 1
        x, z = rng.uniform(x0, x1), rng.uniform(z0, z1)
        if world["land_at"](x, z) is None:
            water.append((x, z))
    return land_seeds, water


def manhattan_surface(frame):
    """Calm pavement tones everywhere, grass in Central Park."""
    land_at = frame.get("land_at")

    def surface(x, z, y, height, slope):
        if land_at and land_at(x, z) in ("staten", "rockaway"):  # leafy suburbs
            return "grass" if math.sin(0.8 * x + 1.0) * math.sin(0.7 * z) > -0.3 else "pavement"
        if frame["in_park"](x, z):
            return "grass" if math.sin(1.3 * x + 0.4) * math.sin(1.1 * z) > -0.5 else "dry"
        return "pavement" if math.sin(0.35 * x + 2.0) * math.sin(0.3 * z + 0.5) > -0.35 else "pavement2"
    return surface


def manhattan_lots(frame, rng):
    """Building lots on the street grid, each with what to build there:
    [(x, z, kind, width, depth, height)]. Everything is a share of the
    island's length, so the proportions hold at any map size: tall towers
    Downtown and in Midtown, lower blocks elsewhere, a few landmark-style
    towers, and trees instead of buildings in Central Park."""
    L = frame["L"]
    lot_w, lot_len = L / 48.0, L / 68.0            # across (avenue blocks), along (street blocks)
    landmarks = {  # where the real ones stand
        "empire": (40.7484, -73.9857), "chrysler": (40.7516, -73.9755), "flatiron": (40.7411, -73.9897),
        "slender": (40.7646, -73.9774),
    }
    taken, lots = [], []
    for name, (lat, lon) in landmarks.items():
        x, z = frame["to_world"](*latlon_to_island(lat, lon))
        if frame["inside"](x, z):
            lots.append((x, z, name, lot_w, lot_len, 0.0, frame["rotate_y"]))
            taken.append((x, z))
    zones = [  # (up to, height range as share of length, building kinds)
        (0.08, (0.022, 0.048), ("glass1", "glass2", "glass3", "setback", "stone1")),   # Downtown
        (0.21, (0.005, 0.012), ("brick1", "brick2", "brick1", "stone2")),              # Villages, SoHo, Chelsea
        (0.37, (0.025, 0.052), ("glass1", "glass2", "setback", "setback", "stone1", "glass3")),  # Midtown
        (0.56, (0.010, 0.022), ("stone1", "stone2", "brick2", "setback")),             # Upper sides
        (1.01, (0.005, 0.013), ("brick1", "brick2", "stone2")),                        # Harlem and north
    ]
    nu = int(L / lot_len)
    nw = int(0.2 * L / lot_w) + 2
    for i in range(nu):
        u = (i + 0.5) * lot_len / L
        for j in range(-nw, nw + 1):
            w = j * lot_w / L
            x, z = frame["to_world"](u, w)
            if not frame["inside"](x, z):
                continue
            if not all(frame["inside"](x + dx, z + dz) for dx, dz in
                       ((lot_w * 0.6, 0), (-lot_w * 0.6, 0), (0, lot_w * 0.6), (0, -lot_w * 0.6))):
                continue  # keep a clear margin from the shore
            if any(math.hypot(x - tx, z - tz) < lot_w * 1.3 for tx, tz in taken):
                continue
            if frame["in_park"](x, z):
                for _ in range(2):  # Central Park: trees
                    lots.append((x + rng.uniform(-0.45, 0.45) * lot_w, z + rng.uniform(-0.45, 0.45) * lot_len,
                                 "tree", 0, 0, 0, rng.uniform(0, 360)))
                continue
            for top, (lo, hi), kinds in zones:
                if u < top:
                    break
            height = rng.uniform(lo, hi) * L
            if rng.random() < 0.12:
                height *= 0.45  # the odd low building keeps the skyline uneven
            lots.append((x, z, rng.choice(kinds), lot_w * rng.uniform(0.62, 0.8),
                         lot_len * rng.uniform(0.62, 0.82), height, frame["rotate_y"]))
    return lots


BOROUGH_GRID = {"bronx": -5.0, "queens": -18.0, "brooklyn": -2.0, "staten": -35.0, "rockaway": -12.0}  # street grid turns


def borough_lots(world, rng):
    """Buildings for the other boroughs on their own street grids: lower and
    further apart than Manhattan, taller around Downtown Brooklyn, Long
    Island City and Flushing; small houses among trees on Staten Island."""
    L = world["L"]
    lots = []
    for land in world["lands"][1:]:
        style = BOROUGH_STYLE[land["name"]]
        lot_w, lot_len = L / 48.0 * style["spacing"], L / 68.0 * style["spacing"]
        turn = BOROUGH_GRID[land["name"]]
        a = math.radians(turn)
        dx1, dz1 = math.cos(a), -math.sin(a)      # the grid's own axes
        dx2, dz2 = math.sin(a), math.cos(a)
        x0, x1, z0, z1 = land["box"]
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        span = max(x1 - x0, z1 - z0)
        centres = []
        for (lat, lon), radius, hrange, kinds in style["centres"]:
            u, w = latlon_to_island(lat, lon)
            centres.append((world["to_world"](u, w), radius * L, hrange, kinds))
        ni, nj = int(span / lot_w) + 2, int(span / lot_len) + 2
        for i in range(-ni // 2 - 1, ni // 2 + 2):
            for j in range(-nj // 2 - 1, nj // 2 + 2):
                x = cx + i * lot_w * dx1 + j * lot_len * dx2
                z = cz + i * lot_w * dz1 + j * lot_len * dz2
                if world["land_at"](x, z) != land["name"]:
                    continue
                if not all(point_in_poly(x + ox, z + oz, land["poly"]) for ox, oz in
                           ((lot_w * 0.6, 0), (-lot_w * 0.6, 0), (0, lot_w * 0.6), (0, -lot_w * 0.6))):
                    continue
                if rng.random() < style.get("trees", 0.0):
                    lots.append((x + rng.uniform(-0.3, 0.3) * lot_w, z + rng.uniform(-0.3, 0.3) * lot_len,
                                 "tree", 0, 0, 0, rng.uniform(0, 360)))
                    continue
                lo, hi = style["h"]
                kinds = style["kinds"]
                for (px, pz), radius, hrange, ckinds in centres:
                    if math.hypot(x - px, z - pz) < radius:
                        lo, hi = hrange
                        kinds = ckinds
                        break
                height = rng.uniform(lo, hi) * L
                kind = rng.choice(kinds)
                if kind == "house":
                    lots.append((x, z, kind, lot_w * 0.35, lot_len * 0.45, height, turn + rng.uniform(-6, 6)))
                else:
                    lots.append((x, z, kind, lot_w * rng.uniform(0.55, 0.75), lot_len * rng.uniform(0.55, 0.8),
                                 height, turn))
    return lots


# ---- building the land ----------------------------------------------------

GRASS = (0.30, 0.40, 0.16)
DRY = (0.55, 0.50, 0.30)
SOIL = (0.62, 0.53, 0.38)
ROCK = (0.45, 0.42, 0.38)
TOPSOIL = (0.34, 0.24, 0.15)
BEDROCK = (0.27, 0.25, 0.24)


def _mix(a, b, t):
    t = min(max(t, 0.0), 1.0)
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _jitter(c, x, z, amount=0.08):
    n = math.sin(1.7 * x + 0.3) * math.sin(1.3 * z + 1.1) + 0.5 * math.sin(4.1 * x - 2.3 * z)
    k = 1.0 + amount * n
    return tuple(min(1.0, max(0.0, v * k)) for v in c)


def surface_colour(x, z, y, height, slope):
    """Grass in the valleys, dry grass and soil on the slopes, rock up high
    and on steep ground."""
    hn = y / height if height > 1e-6 else 0.0
    c = _mix(GRASS, DRY, (hn + 0.35) / 0.5)
    c = _mix(c, SOIL, (hn - 0.2) / 0.4)
    c = _mix(c, ROCK, max((hn - 0.7) / 0.5, (slope - 0.45) / 0.35))
    return _jitter(c, x, z)


def surface_category(x, z, y, height, slope):
    """Which material the ground surface is here: grass in the valleys, dry
    grass and soil on the slopes, rock up high and on steep ground."""
    hn = y / height if height > 1e-6 else 0.0
    hn += 0.18 * (math.sin(0.9 * x + 0.4) * math.sin(0.7 * z + 1.3) + 0.5 * math.sin(2.3 * x - 1.7 * z))
    if slope > 0.6 or hn > 0.75:
        return "rock"
    if hn < -0.15:
        return "grass"
    if hn < 0.25:
        return "dry"
    return "soil"


def build_group_mesh(cells, origin, h, bottom, soil_depth, height, surface=None, walls=("topsoil", "bedrock")):
    """One mesh from one or more cells that move together.

    Tops follow the hills (each cell's top is subdivided in rings so it can
    bend) and are joined into one smooth surface. Walls, only where the piece
    meets other ground, are separate so they don't spoil the top's shading:
    an upper band of topsoil over rock.
    Returns (verts, counts, connects, materials) with one material per face.
    """
    ox, oy, oz = origin
    verts, index = [], {}

    def vid(key, x, y, z):
        if key not in index:
            index[key] = len(verts)
            verts.append((x - ox, y - oy, z - oz))
        return index[key]

    def rkey(x, z):
        return (round(x, 4), round(z, 4))

    edge_count, oriented = {}, []
    for poly in cells:
        area2 = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                    for i in range(len(poly)))
        if area2 > 0:
            poly = list(reversed(poly))
        oriented.append(poly)
        for i in range(len(poly)):
            e = tuple(sorted((rkey(*poly[i]), rkey(*poly[(i + 1) % len(poly)]))))
            edge_count[e] = edge_count.get(e, 0) + 1

    counts, connects, mats = [], [], []

    def top_face(ids, pts):
        counts.append(len(ids))
        connects.extend(ids)
        x = sum(p[0] for p in pts) / len(pts)
        z = sum(p[1] for p in pts) / len(pts)
        y = h(x, z)
        mats.append((surface or surface_category)(x, z, y, height, terrain_slope(h, x, z)))

    for ci, poly in enumerate(oriented):
        n = len(poly)
        cx = sum(p[0] for p in poly) / n
        cz = sum(p[1] for p in poly) / n
        ring_pts = [poly]
        ring_ids = [[vid(("t",) + rkey(x, z), x, h(x, z), z) for x, z in poly]]
        for li, frac in enumerate((0.66, 0.33)):
            pts = [(cx + (x - cx) * frac, cz + (z - cz) * frac) for x, z in poly]
            ring_pts.append(pts)
            ring_ids.append([vid(("i", ci, li, i), x, h(x, z), z) for i, (x, z) in enumerate(pts)])
        c = vid(("c", ci), cx, h(cx, cz), cz)
        for r in range(2):
            outer, inner = ring_ids[r], ring_ids[r + 1]
            op, ip = ring_pts[r], ring_pts[r + 1]
            for i in range(n):
                j = (i + 1) % n
                top_face([inner[i], outer[i], outer[j], inner[j]], [ip[i], op[i], op[j], ip[j]])
        for i in range(n):
            j = (i + 1) % n
            top_face([c, ring_ids[2][i], ring_ids[2][j]], [(cx, cz), ring_pts[2][i], ring_pts[2][j]])
        counts.append(n)
        connects.extend(vid(("b",) + rkey(x, z), x, bottom, z) for x, z in reversed(poly))
        mats.append(walls[1])
        for i in range(n):
            j = (i + 1) % n
            e = tuple(sorted((rkey(*poly[i]), rkey(*poly[j]))))
            if edge_count.get(e, 0) > 1:
                continue  # inside the piece: no wall needed
            (xi, zi), (xj, zj) = poly[i], poly[j]
            ti = vid(("wt",) + rkey(xi, zi), xi, h(xi, zi), zi)
            tj = vid(("wt",) + rkey(xj, zj), xj, h(xj, zj), zj)
            si = vid(("ws",) + rkey(xi, zi), xi, h(xi, zi) - soil_depth, zi)
            sj = vid(("ws",) + rkey(xj, zj), xj, h(xj, zj) - soil_depth, zj)
            bi = vid(("wb",) + rkey(xi, zi), xi, bottom, zi)
            bj = vid(("wb",) + rkey(xj, zj), xj, bottom, zj)
            counts += [4, 4]
            connects += [ti, si, sj, tj, si, bi, bj, sj]
            mats += list(walls)
    return verts, counts, connects, mats


def plan_ground(size, count, epi, faults_n, fault_len, width, seed, collapse=0.3, split=False, island=None,
                grain=1.0):
    """Decide every piece of ground: its outline cells and its role.

    Roles: "plate" (land between two faults, in an inner and an outer block
    that tilt into the rift), "rift" (rubble in a crack or the collapse zone),
    "slab" (land beyond the faults). With split=True every cell is its own
    piece (so everything can crumble), and the cells of a block share the
    block's hinge so they still tilt together.
    Returns (groups, faults).
    """
    half = size / 2.0
    faults = build_faults(epi, faults_n, fault_len, seed)
    mains = [f for f in faults if f["main"]]
    count = int(count * (1.5 if island else 1.0) / (grain * grain))  # smaller pieces: more of them
    seeds = ground_seeds(half, count, faults, width, epi, seed, island["inside"] if island else None, grain)
    collapse_r = fault_len * collapse
    if collapse_r > 0:  # the collapse zone around the epicenter: packed with small rubble
        crng = random.Random(seed * 211 + 9)
        spacing = max(width * 0.3 * grain, 0.3)
        if island and len(island.get("lands", [])) > 1:
            spacing *= 1.7  # the whole city: coarser rubble keeps it light enough to play
        steps = int(collapse_r / spacing) + 1
        for i in range(-steps, steps + 1):
            for j in range(-steps, steps + 1):
                x = epi[0] + (i + crng.uniform(-0.35, 0.35)) * spacing
                z = epi[1] + (j + crng.uniform(-0.35, 0.35)) * spacing
                if math.hypot(x - epi[0], z - epi[1]) < collapse_r * 1.05 and abs(x) < half * 0.995 and abs(z) < half * 0.995:
                    seeds.append((x, z))
    if island and island.get("lands") and len(island["lands"]) > 1:  # the five boroughs
        seeds = [q for q in seeds if island["inside_any"](*q)] + borough_seeds(island, count, seed, grain)
        land_in, water = coast_seeds(island, count, seed, grain)
        seeds += land_in  # (no water seeds: the cells are cut to the coast instead)
        cells = cells_on_land(voronoi_cells_box(seeds, island["box"]), island["lands"])
        is_land = [True] * len(cells)
    elif island:  # only land inside the island; water seeds shape the coast
        land_in, water = island_seeds(island, count, seed, grain)
        seeds = [q for q in seeds if island["inside"](*q)] + land_in
        is_land = [True] * len(seeds) + [False] * len(water)
        seeds = seeds + water
        cells = voronoi_cells(seeds, half)
    else:
        is_land = [True] * len(seeds)
        cells = voronoi_cells(seeds, half)
    rng = random.Random(seed * 53 + 11)
    n_slabs = max(8, count // 12)
    slab_centres = [(rng.uniform(-half, half), rng.uniform(-half, half)) for _ in range(n_slabs)]
    ex, ez = epi

    plates, slabs, rifts = {}, {}, []
    for poly, land in zip(cells, is_land):
        if len(poly) < 3 or not land:
            continue
        cx = sum(p[0] for p in poly) / len(poly)
        cz = sum(p[1] for p in poly) / len(poly)
        r = math.hypot(cx - ex, cz - ez)
        if r < collapse_r or in_rift(cx, cz, faults, width):
            rifts.append(poly)
            continue
        k = wedge_of(cx, cz, epi, mains)
        k2 = (k + 1) % len(mains)
        reach = 0.92 * min(mains[k]["L"], mains[k2]["L"])
        if r < reach:
            band = 0 if r < collapse_r + (reach - collapse_r) / 2.0 else 1
            plates.setdefault((k, band), []).append(poly)
        else:
            s = min(range(n_slabs), key=lambda i: (cx - slab_centres[i][0]) ** 2 + (cz - slab_centres[i][1]) ** 2)
            slabs.setdefault(s, []).append(poly)

    def rv():
        return tuple(rng.random() for _ in range(5))

    def centre(polys):
        pts = [p for poly in polys for p in poly]
        return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)

    groups = []
    for (k, band), polys in sorted(plates.items()):
        k2 = (k + 1) % len(mains)
        reach = 0.9 * min(mains[k]["L"], mains[k2]["L"])
        r_in = collapse_r + band * (reach - collapse_r) / 2.0
        r_out = collapse_r + (band + 1) * (reach - collapse_r) / 2.0
        a0 = fault_angle_at(mains[k], epi, (r_in + r_out) * 0.5)
        span = (fault_angle_at(mains[k2], epi, (r_in + r_out) * 0.5) - a0) % (2 * math.pi)
        mid = a0 + span / 2.0
        ux, uz = math.cos(mid), math.sin(mid)
        block = {
            "role": "plate", "pivot": (ex + ux * r_out, ez + uz * r_out),
            "u": (ux, uz), "axis": (-uz, ux), "hinge": r_out, "r_in": r_in,
            "tilt": rng.uniform(0.7, 1.3) * (1.4 if band == 0 else 0.8) * (1 if rng.random() < 0.85 else -0.5),
        }
        for part in ([[p] for p in polys] if split else [polys]):
            g = dict(block, cells=part, rv=rv())
            cx, cz = centre(part)
            g["d"] = math.hypot(cx - ex, cz - ez)
            groups.append(g)
    for s, polys in sorted(slabs.items()):
        for part in ([[p] for p in polys] if split else [polys]):
            groups.append({"role": "slab", "cells": part, "rv": rv()})
    for poly in rifts:
        groups.append({"role": "rift", "cells": [poly], "rv": rv()})
    for g in groups:
        if "pivot" not in g:
            g["pivot"] = centre(g["cells"])
            g["d"] = math.hypot(g["pivot"][0] - ex, g["pivot"][1] - ez)
    return groups, faults


def shrink_polygon(poly, gap):
    """Pull each corner toward the centre by gap/2 so thin cracks show."""
    cx = sum(p[0] for p in poly) / len(poly)
    cz = sum(p[1] for p in poly) / len(poly)
    out = []
    for x, z in poly:
        dx, dz = cx - x, cz - z
        length = math.hypot(dx, dz)
        k = min(gap * 0.5 / length, 0.45) if length > 1e-9 else 0.0
        out.append((x + dx * k, z + dz * k))
    return out, (cx, cz)


# ==========================================================================
# SEISMIC: wave maths (pure, no Maya)
# ==========================================================================

P_PERIOD = 4.0   # frames per P-wave wiggle (fast, small)
S_PERIOD = 8.0   # frames per S-wave swing (slower, bigger)
S_RATIO = 1.7    # S-waves travel about 1.7 times slower than P-waves


def ground_scale(p):
    """Everything is tuned for a 30-unit ground and scales with the size."""
    return p.get("size", 30) / 30.0


def quake_numbers(p):
    """Amplitude at the epicenter, crack threshold, and damping per unit."""
    sc = ground_scale(p)
    amp0 = 0.1 * p["mag"] * sc
    thr = amp0 * p["threshold"] / 100.0
    k = p["damping"] / 100.0 * 0.3 / sc
    return amp0, thr, k


def crack_radius(p):
    """How far from the epicenter the ground cracks (None = everywhere)."""
    amp0, thr, k = quake_numbers(p)
    if not p["fracture"] or thr <= 0 or thr > amp0:
        return 0.0 if p["fracture"] else None
    if k <= 0:
        return None
    return math.log(amp0 / thr) / k


def arrivals(d, p):
    speed = p["speed"] / 10.0
    t_p = p["start"] + d / speed
    t_s = p["start"] + d * S_RATIO / speed
    return t_p, t_s


def ground_offset(t, d, p, rv, can_break=True):
    """Movement of one object at frame t, at distance d from the epicenter.

    Returns (radial, vertical, sideways, tilt_x, tilt_z): radial is away from
    the epicenter, sideways is across it, tilts are in degrees.
    rv = three random numbers 0..1 for this object (its own crack shape).
    """
    amp0, thr, k = quake_numbers(p)
    amp = amp0 * math.exp(-k * d)
    t_p, t_s = arrivals(d, p)
    rad = vert = side = rx = rz = 0.0

    if p["use_p"] and t >= t_p:  # P-wave: quick push and pull along the ray
        x = t - t_p
        rad += 0.35 * amp * math.sin(2 * math.pi * x / P_PERIOD) * math.exp(-x / 6.0)

    if p["use_s"] and t >= t_s:  # S-wave: big sideways and vertical shaking
        x = t - t_s
        e = math.exp(-x / 14.0)
        side += amp * math.sin(2 * math.pi * x / S_PERIOD) * e
        vert += 0.5 * amp * math.sin(2 * math.pi * x / (S_PERIOD * 0.75)) * e
        rx += 6.0 * amp * math.sin(2 * math.pi * x / S_PERIOD + 0.0) * e

    broken = can_break and p["fracture"] and amp >= thr
    if broken:  # the piece cracks loose: drops, tilts, slides apart
        t_break = t_s if p["use_s"] else t_p
        b = min(max((t - t_break) / 10.0, 0.0), 1.0)
        b = b * b * (3 - 2 * b)  # smooth ease in/out
        sev = min(max((amp - thr) / thr, 0.25), 1.0) if thr > 0 else 1.0
        sc = ground_scale(p)
        rad += 0.25 * sev * b * sc
        vert += -(0.25 + 0.75 * rv[0]) * 1.2 * sev * b * sc
        rx += (rv[1] * 2 - 1) * 16.0 * sev * b
        rz += (rv[2] * 2 - 1) * 16.0 * sev * b
    return rad, vert, side, rx, rz


def quake_times(d, p):
    """Frames to key for one object: denser where the wiggles are fast."""
    t_p, t_s = arrivals(d, p)
    first = t_p if p["use_p"] else t_s
    times = {round(first - 1.0, 3)}
    if p["use_p"]:
        times.update(round(t_p + i * P_PERIOD / 4.0, 3) for i in range(13))
    if p["use_s"]:
        times.update(round(t_s + i * S_PERIOD / 4.0, 3) for i in range(25))
    end = (t_s if p["use_s"] else t_p) + 6 * S_PERIOD
    if p["fracture"]:
        brk = t_s if p["use_s"] else t_p
        times.update(round(brk + i * 2.5, 3) for i in range(5))
    times.add(round(end, 3))
    return sorted(times), end


def quake_end(p, max_d):
    t_p, t_s = arrivals(max_d, p)
    return (t_s if p["use_s"] else t_p) + 6 * S_PERIOD


# ---- how each kind of ground moves -----------------------------------------

def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def aftershocks(p):
    """The main shock plus repeated tremors until the land is gone:
    [(frame, strength), ...]. Same seed, same tremors."""
    rng = random.Random(p.get("seed", 1) * 977 + 3)
    shocks = [(p["start"], 1.0)]
    end = p.get("tremor_end", p["start"])
    t = p["start"]
    while True:
        t += rng.uniform(22.0, 42.0)
        if t >= end:
            break
        shocks.append((t, rng.uniform(0.45, 0.9)))
    return shocks


def shake(t, d, p, scale, shocks=None):
    """Ground shaking at distance d: the main shock's P and S waves, every
    aftershock's S wave, and a steady rumble until the end. Returns
    (radial, vertical, sideways, tilt)."""
    amp0, _, k = quake_numbers(p)
    amp = amp0 * math.exp(-k * d) * scale                 # main shock: fades with distance
    after = amp0 * max(math.exp(-k * d), 0.7) * scale     # tremors: felt across the whole map
    speed = p["speed"] / 10.0
    rad = vert = side = rx = 0.0
    t_p, t_s = arrivals(d, p)
    if p["use_p"] and t >= t_p:
        x = t - t_p
        rad += 0.3 * amp * math.sin(2 * math.pi * x / P_PERIOD) * math.exp(-x / 6.0)
    if p["use_s"]:
        for i, (tb, strength) in enumerate(shocks if shocks is not None else aftershocks(p)):
            arrive = tb + d * S_RATIO / speed
            x = t - arrive
            if x < 0 or x > 70:
                continue
            a = amp if i == 0 else after
            e = strength * math.exp(-x / 14.0)
            side += a * math.sin(2 * math.pi * x / S_PERIOD) * e
            vert += 0.5 * a * math.sin(2 * math.pi * x / (S_PERIOD * 0.75)) * e
            rx += 3.0 * a * math.sin(2 * math.pi * x / S_PERIOD) * e
        end = p.get("tremor_end", p["start"])
        if t_s <= t <= end:  # the rumble never stops while there's land left
            ph = d * 0.7
            r = 0.3 * after
            side += r * math.sin(2 * math.pi * t / 5.3 + ph)
            vert += 0.6 * r * math.sin(2 * math.pi * t / 3.7 + 1.7 * ph)
            rad += 0.5 * r * math.sin(2 * math.pi * t / 4.4 + 0.6 * ph)
    return rad, vert, side, rx


SHAKE_SCALE = {"plate": 0.3, "slab": 0.5, "rift": 0.5, "object": 0.6}


def shake_distance(info):
    if info["role"] == "plate":
        return (info.get("r_in", 0.0) + info.get("hinge", 0.0)) * 0.5
    return info.get("d", 0.0)


def plate_timing(info, p):
    """A block starts tilting when the crack reaches its inner edge and keeps
    going while the crack runs across it."""
    speed = p["speed"] / 10.0
    r_in = info.get("r_in", 0.0)
    t0 = p["start"] + r_in * S_RATIO / speed + 2.0
    return t0, (info["hinge"] - r_in) * S_RATIO / speed + 15.0


def collapse_front(d, p):
    """Frame the spreading collapse reaches distance d (total collapse)."""
    reach = max(p.get("size", 80) * 0.75, 1.0)
    return p["start"] + 6.0 + min(d / reach, 1.2) * p.get("duration", 240)


def collapse_order(x, z, d, size, seed, rv):
    """When this spot gives way, 0 (first) .. 1 (last): partly how far it is
    from the epicenter, mostly a lumpy random pattern, so the land caves in
    as scattered sinkholes and clusters, not a neat ring."""
    rng = random.Random(seed * 389 + 17)
    n = 0.0
    for wavelength, w in ((0.45, 0.6), (0.2, 0.4)):
        a = rng.uniform(0, 2 * math.pi)
        f = 2 * math.pi / (wavelength * size)
        n += w * math.sin(f * (x * math.cos(a) + z * math.sin(a)) + rng.uniform(0, 6.3))
        a = rng.uniform(0, 2 * math.pi)
        n += w * 0.7 * math.sin(f * 1.3 * (x * math.cos(a) + z * math.sin(a)) + rng.uniform(0, 6.3))
    n = 0.5 + 0.5 * n / 1.7
    c = 0.35 * min(d / (size * 0.75), 1.0) + 0.55 * n + 0.2 * (rv[0] - 0.5)
    return min(max(c, 0.0), 1.0)


FALL_STYLES = ("drop", "lurch", "tip")


def fall_style(info):
    r = info.get("rv", (0.5,) * 5)[4]
    return "drop" if r < 0.35 else ("lurch" if r < 0.7 else "tip")


def fall_shape(x, info, p):
    """How far a piece has sunk x frames after it starts to go, and its extra
    tilt: (drop, rx, rz). Three styles so the collapse looks irregular:
    drop - falls straight away; lurch - sinks a little, hangs while the
    ground shakes, then gives way; tip - tips over and slides, then falls."""
    rv = info.get("rv", (0.5,) * 5)
    sc = p.get("size", 80) / 80.0
    g = 0.12 * sc
    style = fall_style(info)
    spin = SPIN.get(info["role"], 30.0)
    sx, sz = rv[2] * 2 - 1, rv[3] * 2 - 1
    if style == "drop":
        s = min(1.0, x / 14.0)
        return 0.5 * g * x * x, sx * spin * s, sz * spin * s
    if style == "lurch":
        first = (0.4 + 0.8 * rv[1]) * sc
        hold = 6.0 + 14.0 * rv[2]
        if x < 4.0:
            e = ease(x / 4.0)
            return first * e, sx * 8.0 * e, sz * 8.0 * e
        if x < 4.0 + hold:
            return first, sx * 8.0, sz * 8.0
        y = x - 4.0 - hold
        s = min(1.0, y / 14.0)
        return first + 0.5 * g * y * y, sx * (8.0 + spin * s), sz * (8.0 + spin * s)
    tip = 30.0 + 25.0 * rv[1]
    if x < 10.0:
        e = ease(x / 10.0)
        return 0.3 * sc * e, sx * tip * e, sz * tip * e
    y = x - 10.0
    s = min(1.0, y / 14.0)
    return 0.3 * sc + 0.5 * g * y * y, sx * (tip + spin * 0.5 * s), sz * (tip + spin * 0.5 * s)


def fall_time_to(depth, info, p):
    """Frames from starting to fall until the piece has sunk to depth."""
    x = 0.0
    while x < 400.0:
        if fall_shape(x, info, p)[0] >= depth:
            return x
        x += 0.5
    return 400.0


def melt_triggers(p):
    """The shocks that set off a new batch of melting: the main shock and the
    aftershocks during the collapse duration."""
    return aftershocks(dict(p, tremor_end=p["start"] + p.get("duration", 240)))


def melt_plan(info, p, triggers=None):
    """When a piece starts melting and how long it takes:
    (start frame, frames, depth, frame it's gone or None), or None.

    Each piece belongs to one shock: small rubble to the first ones, bigger
    land to later ones (info["order"], 0 = first .. 1 = last). It starts
    melting when that shock's wave reaches it.
    """
    if not p["fracture"]:
        return None
    role = info["role"]
    if not p.get("total", True) and role != "rift":
        return None
    trig = triggers if triggers is not None else melt_triggers(p)
    rv = info.get("rv", (0.5,) * 5)
    order = info.get("order", 0.5)
    k = min(int(order * len(trig)), len(trig) - 1)
    speed = p["speed"] / 10.0
    tm = trig[k][0] + info.get("d", 0.0) * S_RATIO / speed + 3.0 + rv[0] * 14.0
    if role == "plate":  # a land block finishes tilting first
        t0, dur = plate_timing(info, p)
        tm = max(tm, t0 + dur * 0.7)
    frames = 24.0 + 36.0 * info.get("size_rank", 0.5) + 10.0 * rv[1]
    depth = info.get("drop", 12.0)
    if not p.get("vanish", True):  # sinks below the old ground and stays
        return tm, frames, depth * 0.6, None
    return tm, frames, depth, tm + frames


def rift_fall_time(info, p):
    melt = melt_plan(dict(info, role="rift"), p)
    return melt[0] if melt else None


SPIN = {"rift": 70.0, "slab": 40.0, "plate": 25.0}


def piece_offset(t, info, p, shocks=None):
    """Offsets for one piece at frame t: (tx, ty, tz, rx, rz, sx, sy, sz),
    where sx, sy, sz multiply the piece's scale.

    Every piece shakes with the main shock, the aftershocks and the rumble.
    plate: tilts about its block's hinge into the rift as the crack runs.
    When its shock reaches it a piece melts like an iceberg: it sinks into
    the ground, slowly at first, while shrinking and slumping and rolling a
    little, then disappears (see piece_vanish).
    """
    role = info["role"]
    ux, uz = info.get("u", (1.0, 0.0))
    vx, vz = -uz, ux
    rad, vert, side, rx = shake(t, shake_distance(info), p, SHAKE_SCALE.get(role, 0.6), shocks)
    tx, ty, tz, rz = rad * ux + side * vx, vert, rad * uz + side * vz, 0.0
    sx = sy = sz = 1.0
    if p["fracture"] and role == "plate":
        t0, dur = plate_timing(info, p)
        angle = (4.0 + 14.0 * p["mag"] / 10.0) * info["tilt"] * ease((t - t0) / dur)
        ax, az = info["axis"]
        rx += angle * ax
        rz += angle * az
    melt = info["melt"] if "melt" in info else melt_plan(info, p)
    if melt and t >= melt[0]:
        tm, frames, depth, gone = melt
        u = min(max((t - tm) / frames, 0.0), 1.0)
        rv = info.get("rv", (0.5,) * 5)
        ty -= depth * u ** 1.6                       # sinks straight down, slowly at first
        if gone is not None:
            sy = 1.0 - 0.9 * ease(min(1.0, u * 1.2))  # slumps flat as it melts...
            sx = sz = 1.0 - 0.3 * ease(u)             # ...shrinking only a little sideways
        roll = ease(u)
        rx += (rv[2] * 2 - 1) * 6.0 * roll            # barely tips as it goes
        rz += (rv[3] * 2 - 1) * 6.0 * roll
    return tx, ty, tz, rx, rz, sx, sy, sz


def piece_vanish(info, p):
    """Frame a piece disappears for good (melted away), or None."""
    melt = info["melt"] if "melt" in info else melt_plan(info, p)
    return melt[3] if melt else None


def piece_times(info, p):
    """Frames to key for one piece: every 2 frames while it shakes, every
    frame while it melts. Returns (times, end)."""
    d = shake_distance(info)
    t_p, t_s = arrivals(d, p)
    first = (min(t_p, t_s) if p["use_p"] else t_s) - 1.0
    end = max(p.get("tremor_end", p["start"]), t_s + 6 * S_PERIOD)
    times = set()
    if p["use_p"]:
        times.update(t_p + i for i in range(13))
    if p["fracture"] and info["role"] == "plate":
        t0, dur = plate_timing(info, p)
        first = min(first, t0 - 1.0)
        times.update(t0 + dur * i / 16.0 for i in range(17))
    melt = info["melt"] if "melt" in info else melt_plan(info, p)
    if melt:
        tm, frames, depth, gone = melt
        first = min(first, tm - 1.0)
        times.update(tm + i for i in range(int(frames) + 2))
        if gone is not None:
            end = gone + 1.0
    t = first
    while t < end:
        times.add(t)
        t += 2.0
    times.add(end)
    return sorted({round(x, 3) for x in times if first <= x <= end}), end


# ==========================================================================
# SEISMIC: Maya side
# ==========================================================================

QUAKE_ATTRS = ["translateX", "translateY", "translateZ", "rotateX", "rotateZ", "scaleX", "scaleY", "scaleZ"]

SEISMIC_PRESETS = {
    "Light Tremor":  {"mag": 3, "speed": 30, "damping": 40, "threshold": 90},
    "Strong Quake":  {"mag": 7, "speed": 20, "damping": 25, "threshold": 35},
    "Shallow Quake": {"mag": 6, "speed": 12, "damping": 50, "threshold": 30},
    "Mega Quake":    {"mag": 10, "speed": 24, "damping": 12, "threshold": 20},
}


def ensure_epicenter():
    """Create the epicenter locator if needed. Returns (name, created?)."""
    if cmds.objExists(EPICENTER):
        return EPICENTER, False
    loc = cmds.spaceLocator(name=EPICENTER)[0]
    cmds.setAttr(loc + ".localScale", 2, 2, 2)
    cmds.setAttr(loc + ".overrideEnabled", 1)
    cmds.setAttr(loc + ".overrideColor", 13)  # red
    return loc, True


def epicenter_xz():
    x, _, z = world_pos(EPICENTER)
    return x, z


PROPS_GRP = "seismic_props_grp"
DATA_ATTR = "seismicData"


def create_mesh(name, verts, counts, connects):
    """Build a polygon mesh with Maya's API. Returns the transform name."""
    import maya.api.OpenMaya as om
    points = om.MPointArray([om.MPoint(x, y, z) for x, y, z in verts])
    obj = om.MFnMesh().create(points, counts, connects)
    return cmds.rename(om.MFnDagNode(obj).name(), name)


MATERIAL_COLOURS = {
    "grass": (0.27, 0.37, 0.13), "dry": (0.55, 0.49, 0.29), "soil": (0.60, 0.50, 0.35),
    "rock": (0.45, 0.42, 0.38), "topsoil": (0.32, 0.22, 0.14), "bedrock": (0.26, 0.24, 0.23),
    "bush": (0.19, 0.31, 0.11), "tuft": (0.46, 0.50, 0.20), "boulder": (0.40, 0.38, 0.35),
    "bark": (0.30, 0.20, 0.12), "leaves": (0.20, 0.38, 0.13), "pine": (0.11, 0.27, 0.12),
    "asphalt": (0.30, 0.30, 0.31), "pavement": (0.50, 0.50, 0.49), "pavement2": (0.45, 0.45, 0.45),
    "water": (0.09, 0.22, 0.30), "stone": (0.72, 0.67, 0.57), "white": (0.88, 0.87, 0.84),
    "glass1": (0.30, 0.42, 0.52), "glass2": (0.22, 0.33, 0.38), "glass3": (0.45, 0.55, 0.60),
    "spandrel": (0.12, 0.14, 0.17), "stone1": (0.74, 0.69, 0.58), "stone2": (0.62, 0.58, 0.52),
    "brick1": (0.50, 0.26, 0.18), "brick2": (0.42, 0.30, 0.24), "trim": (0.80, 0.77, 0.70),
    "tank": (0.36, 0.26, 0.18), "steel": (0.78, 0.79, 0.81), "roof": (0.22, 0.22, 0.24),
    "seawall": (0.62, 0.61, 0.58), "schist": (0.24, 0.24, 0.26),
    "wave": (0.07, 0.26, 0.32), "foam": (0.86, 0.92, 0.94), "deepwater": (0.03, 0.09, 0.13),
    "wavelight": (0.20, 0.52, 0.55),
    "house": (0.80, 0.76, 0.66), "house2": (0.66, 0.72, 0.76), "rooftile": (0.45, 0.22, 0.17),
    "copper": (0.36, 0.60, 0.52), "granite": (0.70, 0.67, 0.61), "gold": (0.90, 0.70, 0.28),
}


GLOSSY = {"glass1", "glass2", "glass3", "water", "steel", "spandrel", "wave", "wavelight", "gold"}


def land_material(kind):
    """A material for the scene (made once). Glass, steel and water are
    Blinn so they catch the light; the rest are Lambert. Returns its shading
    group."""
    shader = "seismicLook_{}_mat".format(kind)
    sg = shader + "SG"
    if not cmds.objExists(shader):
        glossy = kind in GLOSSY
        cmds.shadingNode("blinn" if glossy else "lambert", asShader=True, name=shader)
        cmds.setAttr(shader + ".color", *MATERIAL_COLOURS[kind], type="double3")
        cmds.setAttr(shader + ".diffuse", 0.8)
        if glossy:
            cmds.setAttr(shader + ".specularColor", 0.45, 0.45, 0.45, type="double3")
            cmds.setAttr(shader + ".eccentricity", 0.18)
            if kind == "wavelight":  # the thin front face: light shows through
                cmds.setAttr(shader + ".transparency", 0.35, 0.35, 0.35, type="double3")
            if kind == "water":
                cmds.setAttr(shader + ".specularColor", 0.6, 0.6, 0.62, type="double3")
                cmds.setAttr(shader + ".eccentricity", 0.1)
    if not cmds.objExists(sg):
        cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=sg)
        cmds.connectAttr(shader + ".outColor", sg + ".surfaceShader", force=True)
    return sg


def face_ranges(name, indices):
    """['piece.f[0:5]', 'piece.f[9]', ...] for a list of face numbers."""
    out, start, prev = [], None, None
    for i in sorted(indices):
        if start is None:
            start = prev = i
        elif i == prev + 1:
            prev = i
        else:
            out.append("{}.f[{}:{}]".format(name, start, prev))
            start = prev = i
    if start is not None:
        out.append("{}.f[{}:{}]".format(name, start, prev))
    return out


def make_props(seed):
    """Low-poly trees, bushes, grass tufts and boulders to scatter on the land.
    They're built once, hidden, and placed as instances. Every prop stands on
    its own origin (y = 0 is the ground)."""
    rng = random.Random(seed * 17 + 5)
    grp = cmds.group(empty=True, name=PROPS_GRP)
    protos = {"rock": [], "bush": [], "grass": [], "tree": []}

    def lumpy(name, sx, sy, squash, rough, material, lift=0.6, radius=1.0):
        obj = cmds.polySphere(name=name, radius=radius, subdivisionsX=sx, subdivisionsY=sy,
                              constructionHistory=False)[0]
        count = cmds.polyEvaluate(obj, vertex=True)
        for i in range(count):
            cmds.move(rng.uniform(-rough, rough), rng.uniform(-rough, rough), rng.uniform(-rough, rough),
                      "{}.vtx[{}]".format(obj, i), relative=True, objectSpace=True)
        cmds.scale(1, squash, 1, obj + ".vtx[*]", pivot=(0, 0, 0))
        cmds.move(0, squash * radius * lift, 0, obj + ".vtx[*]", relative=True)
        cmds.sets(obj, edit=True, forceElement=land_material(material))
        return obj

    def unite(parts, name):
        obj = cmds.polyUnite(parts, name=name, constructionHistory=False)[0]
        for part in parts:  # tidy up any empty leftovers
            if cmds.objExists(part):
                cmds.delete(part)
        cmds.parent(obj, grp)
        return obj

    def trunk(height, radius):
        t = cmds.polyCylinder(radius=radius, height=height, subdivisionsX=6, constructionHistory=False)[0]
        cmds.move(0, height / 2.0, 0, t + ".vtx[*]", relative=True)
        cmds.sets(t, edit=True, forceElement=land_material("bark"))
        return t

    # pine trees: a trunk and three stacked cones
    for i in range(2):
        tall = rng.uniform(4.0, 5.5)
        parts = [trunk(tall * 0.35, 0.16)]
        for layer in range(3):
            r = 1.2 - layer * 0.3
            c = cmds.polyCone(radius=r, height=tall * 0.4, subdivisionsX=7, constructionHistory=False)[0]
            cmds.move(0, tall * (0.42 + layer * 0.2), 0, c + ".vtx[*]", relative=True)
            cmds.sets(c, edit=True, forceElement=land_material("pine"))
            parts.append(c)
        protos["tree"].append(unite(parts, "proto_pine{}".format(i + 1)))
    # leafy trees: a trunk and a few lumpy crowns
    for i in range(2):
        tall = rng.uniform(3.0, 4.2)
        parts = [trunk(tall * 0.55, 0.18)]
        for j in range(3):
            crown = lumpy("crown{}_{}".format(i, j), 7, 5, 0.85, 0.15, "leaves", lift=0.0,
                          radius=rng.uniform(0.8, 1.1))
            cmds.move(rng.uniform(-0.5, 0.5), tall * 0.62 + rng.uniform(0, 0.6), rng.uniform(-0.5, 0.5),
                      crown + ".vtx[*]", relative=True)
            parts.append(crown)
        protos["tree"].append(unite(parts, "proto_leafy{}".format(i + 1)))
    for i in range(3):
        rock = lumpy("proto_rock{}".format(i + 1), 6, 4, rng.uniform(0.5, 0.8), 0.25, "boulder")
        cmds.parent(rock, grp)
        protos["rock"].append(rock)
    bush = lumpy("proto_bush1", 7, 5, 0.7, 0.18, "bush", radius=0.7)
    cmds.parent(bush, grp)
    protos["bush"].append(bush)
    blades = []
    for i in range(5):
        b = cmds.polyCone(radius=0.07, height=1.0, subdivisionsX=3, constructionHistory=False)[0]
        cmds.move(0, 0.5, 0, b + ".vtx[*]", relative=True)
        cmds.rotate(rng.uniform(-25, 25), rng.uniform(0, 360), rng.uniform(-25, 25), b + ".vtx[*]", pivot=(0, 0, 0))
        cmds.move(rng.uniform(-0.15, 0.15), 0, rng.uniform(-0.15, 0.15), b + ".vtx[*]", relative=True)
        cmds.sets(b, edit=True, forceElement=land_material("tuft"))
        blades.append(b)
    protos["grass"].append(unite(blades, "proto_grass"))
    cmds.setAttr(grp + ".visibility", 0)
    return protos


def scatter_props(group_name, group, origin, h, height, size, density, protos, rng):
    """Place trees, plants and rocks on one piece of land, inside its outline
    and standing on the ground. They're parented to the piece, so they ride
    along with it and go when it goes."""
    sc = max(size / 80.0, 0.6)
    placed = 0
    ox, oy, oz = origin
    for poly in group["cells"]:
        n = len(poly)
        area = abs(sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))) / 2
        cx = sum(p[0] for p in poly) / n
        cz = sum(p[1] for p in poly) / n
        amount = area * density * 0.06 / (sc * sc)
        k = int(amount) + (1 if rng.random() < amount - int(amount) else 0)
        for _ in range(min(k, 12)):
            i = rng.randrange(n)
            a, b = rng.random(), rng.random()
            if a + b > 1:
                a, b = 1 - a, 1 - b
            a, b = a * 0.85, b * 0.85  # keep clear of the piece's edge
            (x1, z1), (x2, z2) = poly[i], poly[(i + 1) % n]
            x = cx + a * (x1 - cx) + b * (x2 - cx)
            z = cz + a * (z1 - cz) + b * (z2 - cz)
            y = h(x, z)
            hn = y / height if height > 1e-6 else 0.0
            steep = terrain_slope(h, x, z) > 0.5
            roll = rng.random()
            if hn > 0.55 or steep:
                kind = "rock" if roll < 0.7 else "grass"
            elif group["role"] == "rift":
                kind = "grass" if roll < 0.6 else "rock"  # rubble: no trees
            else:
                kind = ("tree" if roll < 0.35 else "grass" if roll < 0.7
                        else "bush" if roll < 0.85 else "rock")
            proto = rng.choice(protos[kind])
            inst = cmds.instance(proto)[0]
            inst = cmds.parent(inst, group_name, relative=True)[0]
            s = sc * {"rock": rng.uniform(0.3, 1.3), "bush": rng.uniform(0.5, 1.0),
                      "grass": rng.uniform(0.6, 1.4), "tree": rng.uniform(0.7, 1.3)}[kind]
            # set each value on its own: position in the piece's space, then turn and size
            cmds.setAttr(inst + ".translate", x - ox, y - oy - 0.05 * s, z - oz, type="double3")
            cmds.setAttr(inst + ".rotate", 0, rng.uniform(0, 360), 0, type="double3")
            cmds.setAttr(inst + ".scale", s, s, s, type="double3")
            placed += 1
    return placed


# ---- Manhattan buildings (Maya) ----------------------------------------------

WATER = "seismic_water"


def _box(w, h, d, y0, material, x=0.0, z=0.0):
    """A box standing on y0 (its base), centred on x, z."""
    b = cmds.polyCube(width=w, height=h, depth=d, constructionHistory=False)[0]
    cmds.move(x, y0 + h / 2.0, z, b + ".vtx[*]", relative=True)
    cmds.sets(b, edit=True, forceElement=land_material(material))
    return b


def _unite(parts, name, grp):
    if len(parts) == 1:
        obj = cmds.rename(parts[0], name)
    else:
        obj = cmds.polyUnite(parts, name=name, constructionHistory=False)[0]
        for part in parts:
            if cmds.objExists(part):
                cmds.delete(part)
    if grp:
        cmds.parent(obj, grp)
    return obj


def make_building_protos(grp):
    """Unit-sized building shapes (1 wide, 1 tall, 1 deep, standing on the
    ground), each with a bit of architecture, in a few colour variations.
    They're placed as instances and sized per lot."""
    protos = {}

    def bands(material, every, start=0.08, end=0.94, thick=0.012, grow=0.012):
        out, y = [], start
        while y < end:
            out.append(_box(1 + grow, thick, 1 + grow, y, material))
            y += every
        return out

    for i, body in enumerate(("glass1", "glass2", "glass3")):   # curtain-wall towers
        parts = [_box(1, 0.95, 1, 0, body)] + bands("spandrel", 0.09)
        parts += [_box(0.6, 0.035, 0.6, 0.95, "roof"), _box(0.3, 0.03, 0.25, 0.985, "steel", 0.1, 0.0)]
        protos[body] = _unite(parts, "proto_bldg_" + body, grp)
    for i, body in enumerate(("stone1", "stone2")):              # masonry towers
        parts = [_box(1, 0.93, 1, 0, body), _box(1.05, 0.025, 1.05, 0.9, body),   # cornice
                 _box(0.7, 0.05, 0.7, 0.93, body), _box(0.72, 0.012, 0.72, 0.975, "roof")]
        parts += bands("trim", 0.16, start=0.15, end=0.85, thick=0.008, grow=0.008)
        protos[body] = _unite(parts, "proto_bldg_" + body, grp)
    for i, body in enumerate(("brick1", "brick2")):              # walk-ups with water tanks
        parts = [_box(1, 0.86, 1, 0, body), _box(1.04, 0.05, 1.04, 0.86, "trim"),
                 _box(1.0, 0.04, 1.0, 0.0, "trim")]
        tank = cmds.polyCylinder(radius=0.12, height=0.1, subdivisionsX=8, constructionHistory=False)[0]
        cmds.move(0.22, 0.91 + 0.05 + 0.04, 0.18, tank + ".vtx[*]", relative=True)
        cap = cmds.polyCone(radius=0.13, height=0.05, subdivisionsX=8, constructionHistory=False)[0]
        cmds.move(0.22, 0.91 + 0.1 + 0.04 + 0.025, 0.18, cap + ".vtx[*]", relative=True)
        for p in (tank, cap):
            cmds.sets(p, edit=True, forceElement=land_material("tank"))
        parts += [tank, cap, _box(0.2, 0.04, 0.2, 0.91, "trim", 0.22, 0.18)]
        protos[body] = _unite(parts, "proto_bldg_" + body, grp)
    parts = [_box(1, 0.5, 1, 0, "stone1"), _box(0.8, 0.22, 0.8, 0.5, "stone1"),     # Art Deco setback
             _box(0.6, 0.14, 0.6, 0.72, "stone1"), _box(0.42, 0.08, 0.42, 0.86, "stone2")]
    parts += bands("trim", 0.1, start=0.1, end=0.5, thick=0.008, grow=0.01)
    spire = cmds.polyCone(radius=0.12, height=0.08, subdivisionsX=8, constructionHistory=False)[0]
    cmds.move(0, 0.94 + 0.04, 0, spire + ".vtx[*]", relative=True)
    cmds.sets(spire, edit=True, forceElement=land_material("steel"))
    protos["setback"] = _unite(parts + [spire], "proto_bldg_setback", grp)
    # a small house with a pitched roof (Staten Island)
    body = _box(1, 0.6, 1, 0, "house")
    roof = cmds.polyPrism(length=1.05, sideLength=1.1, numberOfSides=3, constructionHistory=False)[0]
    cmds.rotate(90, 0, 90, roof + ".vtx[*]", pivot=(0, 0, 0))
    cmds.scale(1.0, 0.5, 1.0, roof + ".vtx[*]", pivot=(0, 0, 0))
    cmds.move(0, 0.6 + 0.2, 0, roof + ".vtx[*]", relative=True)
    cmds.sets(roof, edit=True, forceElement=land_material("rooftile"))
    protos["house"] = _unite([body, roof], "proto_bldg_house", grp)
    return protos


def make_landmark(kind, s, name):
    """Simplified, recognisable Manhattan towers, base on the origin.
    s scales them with the map."""
    parts = []
    if kind == "empire":       # setbacks, a long shaft, mast and needle
        parts += [_box(4.4 * s, 2.5 * s, 3.6 * s, 0, "stone"),
                  _box(3.2 * s, 16 * s, 2.6 * s, 2.5 * s, "stone"),
                  _box(2.4 * s, 5 * s, 1.9 * s, 18.5 * s, "stone"),
                  _box(1.5 * s, 3 * s, 1.2 * s, 23.5 * s, "stone"),
                  _box(0.9 * s, 2 * s, 0.9 * s, 26.5 * s, "steel")]
        mast = cmds.polyCylinder(radius=0.35 * s, height=3 * s, subdivisionsX=8, constructionHistory=False)[0]
        cmds.move(0, 28.5 * s + 1.5 * s, 0, mast + ".vtx[*]", relative=True)
        needle = cmds.polyCone(radius=0.25 * s, height=3.5 * s, subdivisionsX=8, constructionHistory=False)[0]
        cmds.move(0, 31.5 * s + 1.75 * s, 0, needle + ".vtx[*]", relative=True)
        for p in (mast, needle):
            cmds.sets(p, edit=True, forceElement=land_material("steel"))
        parts += [mast, needle]
    elif kind == "chrysler":   # a shaft, a stepped silver crown and a spire
        parts += [_box(3.4 * s, 2 * s, 3.4 * s, 0, "stone"), _box(2.6 * s, 19 * s, 2.6 * s, 2 * s, "stone")]
        y = 21 * s
        for i, r in enumerate((1.6, 1.3, 1.0, 0.7)):
            c = cmds.polyCone(radius=r * s, height=2.2 * s, subdivisionsX=8, constructionHistory=False)[0]
            cmds.move(0, y + 1.1 * s, 0, c + ".vtx[*]", relative=True)
            cmds.sets(c, edit=True, forceElement=land_material("steel"))
            parts.append(c)
            y += 1.5 * s
        spire = cmds.polyCone(radius=0.25 * s, height=5 * s, subdivisionsX=6, constructionHistory=False)[0]
        cmds.move(0, y + 2.5 * s, 0, spire + ".vtx[*]", relative=True)
        cmds.sets(spire, edit=True, forceElement=land_material("steel"))
        parts.append(spire)
    elif kind == "flatiron":   # a triangular wedge
        f = cmds.polyCylinder(radius=2.6 * s, height=8 * s, subdivisionsX=3, constructionHistory=False)[0]
        cmds.move(0, 4 * s, 0, f + ".vtx[*]", relative=True)
        cmds.scale(0.65, 1, 1.25, f + ".vtx[*]", pivot=(0, 0, 0))
        cmds.sets(f, edit=True, forceElement=land_material("stone"))
        parts.append(f)
    else:                      # "slender": a pencil-thin supertall
        parts += [_box(1.5 * s, 36 * s, 1.5 * s, 0, "white")]
        for k in range(1, 6):
            parts.append(_box(1.56 * s, 0.25 * s, 1.56 * s, k * 6 * s, "spandrel"))
    return _unite(parts, name, None)


WATER_FX = "seismic_water_fx"


def water_material():
    """Glossy water whose colour carries moving ripple rings: an animated
    'wave' noise texture between deep and lighter teal. Shows in the
    viewport from any distance. Returns the shading group."""
    shader, sg = "seismicLook_ripplewater_mat", "seismicLook_ripplewater_matSG"
    if cmds.objExists(shader):
        return sg
    cmds.shadingNode("blinn", asShader=True, name=shader)
    cmds.setAttr(shader + ".specularColor", 0.7, 0.7, 0.72, type="double3")
    cmds.setAttr(shader + ".eccentricity", 0.08)
    cmds.setAttr(shader + ".diffuse", 0.85)
    cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=sg)
    cmds.connectAttr(shader + ".outColor", sg + ".surfaceShader", force=True)
    try:
        noise = cmds.shadingNode("noise", asTexture=True, name="seismic_ripples")
        place = cmds.shadingNode("place2dTexture", asUtility=True, name="seismic_ripples_place")
        for a in ("coverage", "translateFrame", "rotateFrame", "mirrorU", "mirrorV", "stagger", "wrapU",
                  "wrapV", "repeatUV", "offset", "rotateUV", "noiseUV", "vertexUvOne", "vertexUvTwo",
                  "vertexUvThree", "vertexCameraOne"):
            _try(cmds.connectAttr, "{}.{}".format(place, a), "{}.{}".format(noise, a), force=True)
        _try(cmds.connectAttr, place + ".outUV", noise + ".uv", force=True)
        _try(cmds.connectAttr, place + ".outUvFilterSize", noise + ".uvFilterSize", force=True)
        cmds.setAttr(place + ".repeatUV", 9, 9, type="double2")
        cmds.setAttr(noise + ".noiseType", 2)          # "Wave": overlapping ripple rings
        cmds.setAttr(noise + ".numWaves", 9)
        cmds.setAttr(noise + ".frequency", 6)
        cmds.setAttr(noise + ".amplitude", 0.9)
        cmds.setAttr(noise + ".depthMax", 2)
        cmds.setAttr(noise + ".colorOffset", 0.05, 0.17, 0.24, type="double3")   # deep teal
        cmds.setAttr(noise + ".colorGain", 0.13, 0.22, 0.24, type="double3")     # up to lighter teal
        cmds.connectAttr(noise + ".outColor", shader + ".color", force=True)
        cmds.expression(name="seismic_ripples_expr", string="seismic_ripples.time = time * 0.35;",
                        alwaysEvaluate=True)
    except Exception as exc:
        cmds.setAttr(shader + ".color", *MATERIAL_COLOURS["water"], type="double3")
        print("Ripple: the water colour won't ripple ({})".format(exc))
    return sg


TSUNAMI_GRP = "seismic_tsunami_grp"


# The wave's cross-section, from the back (inside) to the front (outside):
# (offset from the ring's radius, height, material of the strip after it).
# A wave train: two smaller swells behind the main wave, whose crest curls
# forward into an overhanging foam lip above a steep, lighter front face.
TSUNAMI_PROFILE = [
    # third crest (lowest, about 45%)
    (-0.34, -0.12, "wave"), (-0.31, 0.05, "wave"), (-0.29, 0.36, "foam"), (-0.27, 0.45, "wave"),
    (-0.245, 0.30, "wave"), (-0.22, 0.06, "wave"),
    # second crest (about 70%)
    (-0.20, 0.04, "wave"), (-0.175, 0.40, "wave"), (-0.155, 0.62, "foam"), (-0.135, 0.70, "wave"),
    (-0.115, 0.48, "wave"), (-0.09, 0.10, "wave"),
    # first crest (tallest), curling forward into a foam lip over a lighter face
    (-0.07, 0.08, "wave"), (-0.045, 0.55, "wave"), (-0.022, 0.86, "foam"), (0.0, 1.00, "foam"),
    (0.022, 1.02, "foam"), (0.040, 0.90, "wavelight"), (0.036, 0.72, "wavelight"),
    (0.024, 0.58, "wavelight"), (0.026, 0.36, "wave"), (0.040, 0.14, "foam"), (0.065, -0.12, "wave"),
]


def tsunami_ring_topology(segments=180, seed=7):
    """A ring of breaking waves, radius 1, crest height about 1, built from
    TSUNAMI_PROFILE swept around the ring. The crest is uneven: higher and
    lower along its length, with ragged spray on the lip, so it doesn't look
    like a smooth wall. Returns (verts, counts, connects, materials)."""
    rng = random.Random(seed)
    phases = [(k, rng.uniform(0, 2 * math.pi), a) for k, a in ((3, 0.18), (7, 0.12), (13, 0.07), (23, 0.04))]
    rows = len(TSUNAMI_PROFILE)
    verts = []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        ca, sa = math.cos(a), math.sin(a)
        hmult = 1.0 + sum(amp * math.sin(k * a + ph) for k, ph, amp in phases)
        wobble = 0.012 * math.sin(5 * a + phases[0][1]) + 0.008 * math.sin(11 * a + phases[1][1])
        for j, (dr, y, _) in enumerate(TSUNAMI_PROFILE):
            r = 1.0 + dr + wobble
            yy = y * hmult
            if 10 <= j <= 13:  # spray: ragged bits along the foam lip
                yy += rng.uniform(-0.05, 0.09) * y
            verts.append((r * ca, yy, r * sa))
    counts, connects, mats = [], [], []
    for i in range(segments):
        j2 = (i + 1) % segments
        for k in range(rows - 1):
            a0, a1 = i * rows + k, i * rows + k + 1
            b0, b1 = j2 * rows + k, j2 * rows + k + 1
            counts.append(4)
            connects += [a0, b0, b1, a1]
            mats.append(TSUNAMI_PROFILE[k][2])
    return verts, counts, connects, mats


TSUNAMI_WAVES = (  # (which shock, as a share of the shocks; height as a share of the main wave)
    (0.0, 1.0), (0.34, 0.65), (0.67, 0.45),
)


def tsunami_arc_topology(span_deg=95.0, segments=64, seed=7):
    """One wave front: an arc of breaking wave, radius 1, crest height about
    1, facing +X, built from TSUNAMI_PROFILE swept across span_deg. Its ends
    taper down to nothing so it reads as a section of wave, and its crest is
    uneven with ragged spray. Returns (verts, counts, connects, materials)."""
    rng = random.Random(seed)
    phases = [(k, rng.uniform(0, 2 * math.pi), a) for k, a in ((2, 0.16), (5, 0.10), (11, 0.06))]
    rows = len(TSUNAMI_PROFILE)
    span = math.radians(span_deg)
    verts = []
    for i in range(segments + 1):
        u = i / float(segments)
        a = -span / 2 + span * u
        ca, sa = math.cos(a), math.sin(a)
        taper = math.sin(math.pi * u) ** 0.6           # the ends die down
        hmult = taper * (1.0 + sum(amp * math.sin(k * a * 4 + ph) for k, ph, amp in phases))
        wobble = 0.015 * math.sin(7 * a + phases[0][1])
        for j, (dr, y, _) in enumerate(TSUNAMI_PROFILE):
            r = 1.0 + dr + wobble
            yy = y * hmult if y > 0 else y  # skirts stay just under the surface
            if y >= 0.6:  # spray: ragged bits along each crest
                yy += rng.uniform(-0.05, 0.09) * y * taper
            verts.append((r * ca, yy, -r * sa))
    counts, connects, mats = [], [], []
    for i in range(segments):
        for k in range(rows - 1):
            a0, a1 = i * rows + k, i * rows + k + 1
            b0, b1 = (i + 1) * rows + k, (i + 1) * rows + k + 1
            counts.append(4)
            connects += [a0, a1, b1, b0]
            mats.append(TSUNAMI_PROFILE[k][2])
    return verts, counts, connects, mats


def coast_points(land, world, count, rng):
    """count points on a landmass's shore that face open water, spread far
    apart, each with the direction straight out to sea: [(x, z, dx, dz)]."""
    poly = land["poly"]
    n = len(poly)
    area2 = sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1] for i in range(n))
    out_sign = -1.0 if area2 > 0 else 1.0
    L = world["L"]
    cands = []
    for i in range(n):
        (ax, az), (bx, bz) = poly[i], poly[(i + 1) % n]
        seg = math.hypot(bx - ax, bz - az)
        if seg < 1e-9:
            continue
        nx, nz = (bz - az) / seg * out_sign, -(bx - ax) / seg * out_sign
        mx, mz = (ax + bx) / 2.0, (az + bz) / 2.0
        if point_in_poly(mx + nx * L * 0.01, mz + nz * L * 0.01, poly):
            nx, nz = -nx, -nz  # make sure it points out to sea
        if not point_in_poly(mx + nx * L * 0.01, mz + nz * L * 0.01, land["poly"]) and \
                world["land_at"](mx + nx * L * 0.04, mz + nz * L * 0.04) is None:
            cands.append((mx, mz, nx, nz))
    if not cands:
        return []
    picked = [cands[rng.randrange(len(cands))]]
    while len(picked) < min(count, len(cands)):  # spread them out
        picked.append(max(cands, key=lambda c: min(math.hypot(c[0] - p[0], c[1] - p[1]) for p in picked)))
    return picked


def tsunami_plan(size, island=None, epi=(0.0, 0.0), seed=1):
    """Where each wave front starts, which way it runs, how big and when:
    [{centre, heading (degrees, Maya rotateY), span, start radius, end radius,
      frames to travel, strength, shock share, delay}].
    For Manhattan they leave different stretches of the coast in different
    directions; on open land they fan out around the epicenter."""
    rng = random.Random(seed * 131 + 7)
    L = float(size)
    plan = []

    def add(x, z, dx, dz, strength, share, delay):
        """A set of three fronts from one stretch of coast, one after another,
        each lower than the last (100%, 75%, 50%)."""
        heading = math.degrees(math.atan2(-dz, dx)) + rng.uniform(-12, 12)
        span = rng.uniform(75, 115)
        travel = rng.uniform(105, 150)
        r1 = L * rng.uniform(0.95, 1.35)
        for n, (k, lag) in enumerate(((1.0, 0.0), (0.75, 22.0), (0.5, 44.0))):
            plan.append({"centre": (x, z), "heading": heading + rng.uniform(-4, 4),
                         "span": span * rng.uniform(0.9, 1.05), "r0": L * 0.03, "r1": r1 * (1.0 - 0.06 * n),
                         "travel": travel * (1.0 + 0.05 * n), "strength": strength * k, "share": share,
                         "delay": delay + lag, "seed": rng.randrange(10000)})

    if island:
        ux, uz = island["up"]
        ex, ez = island["east"]

        def shore(u, side):  # a point on the west (-1) or east (+1) shore at u along the island
            near = sorted(island["outline"], key=lambda q: abs(island["to_island"](*q)[0] - u))[:8]
            x, z = (min if side < 0 else max)(near, key=lambda q: island["to_island"](*q)[1])
            cx, cz = island["to_world"](u, island["to_island"](x, z)[1] - side * 0.004)
            return cx, cz

        def toward(side, lean):  # out across the river, leaning up or down the island
            dx, dz = side * ex + lean * ux, side * ez + lean * uz
            n = math.hypot(dx, dz)
            return dx / n, dz / n

        b = island["to_world"](0.01, 0.0)
        add(b[0], b[1], -ux, -uz, 1.0, 0.0, 0)                         # Battery, south into the harbour
        for u, side, lean, strength, share, delay in (
                (0.30, -1, 0.1, 0.95, 0.0, 6),                           # Midtown, west over the Hudson
                (0.32, 1, -0.1, 0.9, 0.0, 12),                           # Midtown, east over the East River
                (0.10, 1, -0.35, 0.8, 0.0, 20),                          # Downtown, east
                (0.08, -1, -0.3, 0.7, 0.34, 0),                          # Downtown, west
                (0.50, -1, 0.25, 0.65, 0.34, 10),                        # Upper West Side
                (0.62, 1, 0.3, 0.6, 0.34, 18)):                          # Harlem, east
            x, z = shore(u, side)
            dx, dz = toward(side, lean)
            add(x, z, dx, dz, strength, share, delay)
        t = island["to_world"](*latlon_to_island(40.8740, -73.9240))
        add(t[0], t[1], -ex * 0.8 + ux * 0.6, -ez * 0.8 + uz * 0.6, 0.5, 0.67, 0)  # Inwood, up the Hudson
        # the other boroughs: three stretches of each one's shore, facing open water
        for land, strength, share, delay in ((lnd, *cfg) for lnd in island.get("lands", [])[1:]
                                             for cfg in [{"brooklyn": (0.85, 0.0, 28), "queens": (0.8, 0.0, 38),
                                                          "bronx": (0.75, 0.34, 4),
                                                          "staten": (0.7, 0.34, 14),
                                                          "rockaway": (0.75, 0.0, 34)}[lnd["name"]]]):
            for k, (x, z, dx, dz) in enumerate(coast_points(land, island, 3, rng)):
                add(x, z, dx, dz, strength * (1.0 - 0.1 * k), share, delay + 8 * k)
    else:
        for k in range(8):
            a = 2 * math.pi * k / 8 + rng.uniform(-0.25, 0.25)
            add(epi[0], epi[1], math.cos(a), math.sin(a), 1.0 if k < 4 else 0.65,
                0.0 if k < 4 else 0.34, (k % 4) * 6)
    return plan


def key_tsunami(p, shocks, size):
    """Key the tsunami for this quake. First the sea draws back from the
    shore; then each wave front rises off its stretch of coast (the biggest
    taller than the towers: exaggerated on purpose) and runs out in its own
    direction at its own pace, getting lower as it spreads, then is gone.
    Returns the frame the last wave has died down (or None)."""
    L = float(size)
    end = None
    main_t0 = None
    fronts = cmds.listRelatives(TSUNAMI_GRP, children=True, type="transform") if cmds.objExists(TSUNAMI_GRP) else []
    for front in fronts or []:
        if not cmds.attributeQuery("share", node=front, exists=True):
            continue
        get = lambda a: cmds.getAttr(front + "." + a)
        share, delay, strength = get("share"), get("delay"), get("strength")
        r0, r1, travel = get("r0"), get("r1"), get("travel")
        t0 = shocks[min(int(share * len(shocks)), len(shocks) - 1)][0] + delay + (24.0 if share == 0 else 6.0)
        main_t0 = t0 if main_t0 is None else min(main_t0, t0)
        height = L * 0.1 * strength * (0.5 + 0.5 * p["mag"] / 10.0)
        cmds.cutKey(front, attribute=["scaleX", "scaleY", "scaleZ", "visibility", "translateY"], clear=True)
        grow = [(t0 - 1, 0.0), (t0 + travel * 0.25, 0.2), (t0 + travel, 1.0)]  # fast off the coast, then steady
        base_y = get("baseY") if cmds.attributeQuery("baseY", node=front, exists=True) else 0.0
        for attr, keys in (
                ("visibility", [(t0 - 1, 0.0), (t0, 1.0), (t0 + travel * 1.1, 1.0), (t0 + travel * 1.1 + 0.5, 0.0)]),
                ("scaleY", [(t0 - 1, height * 0.15), (t0 + 6, height * 0.6), (t0 + 16, height),
                            (t0 + travel * 0.55, height * 0.75), (t0 + travel * 1.1, height * 0.45)]),
                # rises out of the sea, then sinks back under it as it dies (no flat smear on the water)
                ("translateY", [(t0 - 1, base_y - height * 0.3), (t0 + 8, base_y),
                                (t0 + travel * 0.75, base_y), (t0 + travel * 1.1, base_y - height * 0.7)]),
                ("scaleX", [(t, r0 + (r1 - r0) * g) for t, g in grow]),
                ("scaleZ", [(t, r0 + (r1 - r0) * g) for t, g in grow])):
            for t, v in keys:
                cmds.setKeyframe(front, attribute=attr, time=t, value=v)
        end = max(end or 0.0, t0 + travel * 1.1 + 1)
    # the sea draws back from the shore just before the first wave, then surges back
    if main_t0 is not None and cmds.objExists(WATER):
        base = cmds.getAttr(WATER + ".translateY", time=p["start"])
        drop = L / 70.0
        cmds.cutKey(WATER, attribute="translateY", clear=True)
        for t, v in ((p["start"] + 2, base), (main_t0 - 4, base - drop), (main_t0 + 2, base - drop),
                     (main_t0 + 22, base + drop * 0.4), (main_t0 + 50, base)):
            cmds.setKeyframe(WATER, attribute="translateY", time=t, value=v)
    return end


def make_water(size, level, epi=(0.0, 0.0), island=None):
    """The Hudson and East River around the island, moving: the surface
    really waves (rings spreading from the epicenter, and a slow swell
    crossing them), and its colour carries drifting ripple rings. Both run
    with the timeline, so press play to see them."""
    L = float(size)
    wx = wz = 0.0
    extent = L * 2.6
    if island and island.get("box") and len(island.get("lands", [])) > 1:  # the whole city
        x0, x1, z0, z1 = island["box"]
        wx, wz = (x0 + x1) / 2.0, (z0 + z1) / 2.0
        extent = max(x1 - x0, z1 - z0) * 1.15
    plane = cmds.polyPlane(name=WATER, width=extent, height=extent,
                           subdivisionsX=260, subdivisionsY=260, constructionHistory=False)[0]
    cmds.setAttr(plane + ".translate", wx, level, wz, type="double3")
    cmds.sets(plane, edit=True, forceElement=water_material())
    # the deep sea under the surface, so sinking pieces can't be seen from the side
    body = cmds.polyCube(name=WATER + "_deep", width=extent * 0.995, depth=extent * 0.995, height=L * 0.6,
                         constructionHistory=False)[0]
    # right under the surface (same centre), well below the ripple troughs so the two never flicker
    cmds.setAttr(body + ".translate", wx, level - L / 40.0 - L * 0.3, wz, type="double3")
    cmds.sets(body, edit=True, forceElement=land_material("deepwater"))
    cmds.parent(body, plane)
    for obj in (plane, body):  # no sun shadows on the sea: they streak on the moving surface
        for attr in ("receiveShadows", "castsShadows"):
            _try(cmds.setAttr, obj + "." + attr, 0)
    # keep the ripple pattern the same size however big the sea is
    _try(cmds.setAttr, "seismic_ripples_place.repeatUV", 9 * extent / (L * 2.6), 9 * extent / (L * 2.6),
         type="double2")
    # tsunami wave fronts: hidden until a quake is keyed (see key_tsunami)
    try:
        tgrp = cmds.group(empty=True, name=TSUNAMI_GRP)
        for i, w in enumerate(tsunami_plan(L, island, epi)):
            verts, counts, connects, mats = tsunami_arc_topology(w["span"], seed=w["seed"])
            front = create_mesh("seismic_tsunami{}".format(i + 1), verts, counts, connects)
            for m in ("wave", "foam", "wavelight"):
                idx = [f for f, mm in enumerate(mats) if mm == m]
                cmds.sets(face_ranges(front, idx), edit=True, forceElement=land_material(m))
            _try(cmds.polySoftEdge, front, angle=80, constructionHistory=False)
            cmds.setAttr(front + ".translate", w["centre"][0], level + 0.05, w["centre"][1], type="double3")
            cmds.setAttr(front + ".rotate", 0, w["heading"], 0, type="double3")
            cmds.setAttr(front + ".scale", w["r0"], 0.01, w["r0"], type="double3")
            cmds.setAttr(front + ".visibility", 0)
            for attr in ("r0", "r1", "travel", "strength", "share", "delay"):
                cmds.addAttr(front, longName=attr, attributeType="double")
                cmds.setAttr(front + "." + attr, w[attr])
            cmds.addAttr(front, longName="baseY", attributeType="double")
            cmds.setAttr(front + ".baseY", level + 0.05)
            cmds.parent(front, tgrp)
    except Exception as exc:
        print("Ripple: couldn't build the tsunami ({})".format(exc))
    try:
        grp = cmds.group(empty=True, name=WATER_FX)
        waves = []
        # (centre, wavelength, height, wavelengths per second): rings from the epicenter, a far-off swell
        for i, (cx, cz, wavelength, height, speed) in enumerate((
                (epi[0], epi[1], L / 16.0, L / 220.0, 0.5),
                (-L * 1.6, L * 1.0, L / 7.0, L / 300.0, 0.22))):
            reach = max(math.hypot(cx - wx - sx * extent / 2, cz - wz - sz * extent / 2)
                        for sx in (-1, 1) for sz in (-1, 1)) * 1.05
            deformer, handle = cmds.nonLinear(plane, type="wave")
            handle = cmds.rename(handle, "seismic_wave{}_handle".format(i + 1))
            cmds.setAttr(handle + ".translate", cx, level, cz, type="double3")
            cmds.setAttr(handle + ".scale", reach, reach, reach, type="double3")
            cmds.setAttr(deformer + ".wavelength", wavelength / reach)
            cmds.setAttr(deformer + ".amplitude", height / reach)
            cmds.setAttr(deformer + ".minRadius", 0)
            cmds.setAttr(deformer + ".maxRadius", 1)
            cmds.setAttr(deformer + ".dropoff", 0.3 if i == 0 else 0.0)  # epicenter rings fade a little outward
            cmds.parent(handle, grp)
            waves.append((deformer, wavelength / reach, speed))
        cmds.setAttr(grp + ".visibility", 0)  # hide the wave handles; the waves still work
        expr = "\n".join("{}.offset = -time * {:.6f};".format(d, wl * sp) for d, wl, sp in waves)
        cmds.expression(name="seismic_water_expr", string=expr, alwaysEvaluate=True)
    except Exception as exc:  # moving water is a bonus; still water is fine
        print("Ripple: the water surface won't wave ({})".format(exc))
    return plane


def place_buildings(frame, pieces, h, protos, tree_protos, rng, plants):
    """Put the city on the land. pieces: [(name, cells, origin)].
    Each building is parented to the piece of ground under it, so it shakes,
    sinks and disappears with that ground. Returns (buildings, trees)."""
    L = frame["L"]
    lots = manhattan_lots(frame, rng)
    if frame.get("lands") and len(frame["lands"]) > 1:
        lots += borough_lots(frame, rng)
    index = []  # for finding the piece under a point quickly
    for name, cells, origin in pieces:
        for poly in cells:
            xs = [p[0] for p in poly]
            zs = [p[1] for p in poly]
            index.append((min(xs), max(xs), min(zs), max(zs), poly, name, origin))
    cell = L / 20.0
    grid = {}
    for e in index:
        for gx in range(int(e[0] // cell), int(e[1] // cell) + 1):
            for gz in range(int(e[2] // cell), int(e[3] // cell) + 1):
                grid.setdefault((gx, gz), []).append(e)

    def piece_at(x, z):
        for x0, x1, z0, z1, poly, name, origin in grid.get((int(x // cell), int(z // cell)), ()):
            if x0 <= x <= x1 and z0 <= z <= z1 and point_in_poly(x, z, poly):
                return name, origin
        # in a crack between pieces: use the nearest piece
        best = min(index, key=lambda e: ((e[0] + e[1]) / 2 - x) ** 2 + ((e[2] + e[3]) / 2 - z) ** 2, default=None)
        if best and math.hypot((best[0] + best[1]) / 2 - x, (best[2] + best[3]) / 2 - z) < L / 25.0:
            return best[5], best[6]
        return None, None

    landmark_scale = L * 0.068 / 34.0   # the tallest landmark reaches about 7% of the island's length
    tree_scale = L / 80.0 * 0.22        # trees about 1% of the length
    buildings = trees = 0
    progress_start("Placing buildings...", len(lots))
    for li, (x, z, kind, w, d, height, turn) in enumerate(lots):
        progress_step(li, "Placing buildings: {} of {}".format(li, len(lots)))
        name, origin = piece_at(x, z)
        if name is None:
            continue
        ox, oy, oz = origin
        y = h(x, z)
        if kind == "tree":
            if not tree_protos or rng.random() > max(plants, 0.2):
                continue
            inst = cmds.instance(rng.choice(tree_protos))[0]
            s = tree_scale * rng.uniform(0.7, 1.2)
            scale = (s, s, s)
            trees += 1
        elif kind in protos:
            inst = cmds.instance(protos[kind])[0]
            scale = (w, height, d)
            buildings += 1
        else:  # a landmark: built on the spot, a little broader than its true shape
            inst = make_landmark(kind, landmark_scale, "landmark_" + kind)
            scale = (1.5, 1, 1.5)
            buildings += 1
        inst = cmds.parent(inst, name, relative=True)[0]
        cmds.setAttr(inst + ".translate", x - ox, y - oy - 0.02 * L / 80.0, z - oz, type="double3")
        cmds.setAttr(inst + ".rotate", 0, turn, 0, type="double3")
        cmds.setAttr(inst + ".scale", *scale, type="double3")
    return buildings, trees


# ---- the Statue of Liberty ---------------------------------------------------

LIBERTY_GRP = "seismic_liberty"
MANHATTAN_METRES = 21600.0  # Manhattan is about 21.6 km long: the map's length
# Liberty Island seen from the Battery: about 2.5 km down the island's line
# and 1.3 km to the west of it (real map positions, turned to the 29° grid)
LIBERTY_UW = (-0.116, -0.059)


def liberty_place(frame):
    """Where the statue stands, and which way it falls: away from Manhattan."""
    x, z = frame["to_world"](*LIBERTY_UW)
    bx, bz = frame["to_world"](0.0, 0.0)
    dx, dz = x - bx, z - bz
    return (x, z), math.degrees(math.atan2(dx, dz))


def prism_mesh(name, outline, y0, y1, top_mat, side_mat, bottom_mat=None):
    """A flat-topped prism from a 2D outline [(x, z)], from y0 up to y1."""
    poly = list(outline)
    area2 = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                for i in range(len(poly)))
    if area2 > 0:
        poly.reverse()
    n = len(poly)
    verts = [(x, y1, z) for x, z in poly] + [(x, y0, z) for x, z in poly]
    counts, connects, mats = [n, n], list(range(n)) + [n + i for i in reversed(range(n))], \
        [top_mat, bottom_mat or side_mat]
    for i in range(n):
        j = (i + 1) % n
        counts.append(4)
        connects += [i, n + i, n + j, j]
        mats.append(side_mat)
    obj = create_mesh(name, verts, counts, connects)
    for m in set(mats):
        cmds.sets(face_ranges(obj, [f for f, mm in enumerate(mats) if mm == m]),
                  edit=True, forceElement=land_material(m))
    return obj


def frustum_mesh(name, r0, r1, y0, y1, material, sides=12, x=0.0, z=0.0):
    """A tapered column (wider at the bottom), centred on x, z."""
    verts = []
    for r, y in ((r1, y1), (r0, y0)):
        for i in range(sides):
            a = 2 * math.pi * i / sides
            verts.append((x + r * math.cos(a), y, z - r * math.sin(a)))
    n = sides
    counts, connects = [n, n], list(range(n)) + [n + i for i in reversed(range(n))]
    for i in range(n):
        j = (i + 1) % n
        counts.append(4)
        connects += [i, n + i, n + j, j]
    obj = create_mesh(name, verts, counts, connects)
    cmds.sets(obj, edit=True, forceElement=land_material(material))
    return obj


def build_liberty(frame, level, boost=8.0):
    """Liberty Island and the Statue of Liberty, in its real spot. boost
    enlarges it: 1 is true to scale against Manhattan (93 m from the ground
    to the torch, on a map 21.6 km long: tiny next to the exaggerated
    skyline); the default 8 makes it read clearly, like the skyline's own
    exaggeration. The island grows with it, a little less. Parts are grouped
    so the torch arm can snap, the statue can topple and everything can sink.
    Returns the statue's height in scene units."""
    true_s = frame["L"] / MANHATTAN_METRES     # scene units per metre, true scale
    s = true_s * boost                         # the statue, pedestal and fort
    isl = true_s * max(1.0, boost * 0.45)      # the island
    (x, z), heading = liberty_place(frame)
    grp = cmds.group(empty=True, name=LIBERTY_GRP)
    cmds.addAttr(grp, longName="unitsPerMetre", attributeType="double")
    cmds.setAttr(grp + ".unitsPerMetre", s)
    cmds.setAttr(grp + ".translate", x, 0.0, z, type="double3")
    cmds.setAttr(grp + ".rotate", 0, heading, 0, type="double3")   # local +Z points away from Manhattan

    # the island (about 400 m by 250 m), its lawn level with Manhattan's streets
    island = [(150 * isl * math.cos(2 * math.pi * k / 20), 230 * isl * math.sin(2 * math.pi * k / 20) *
               (1.0 + 0.15 * math.sin(3 * 2 * math.pi * k / 20))) for k in range(20)]
    land = prism_mesh("liberty_island", island, level - 1.0, 0.0, "grass", "seawall", "schist")
    # Fort Wood: the eleven-pointed star the pedestal stands on
    star = [((55 if k % 2 == 0 else 38) * s * math.cos(math.pi * k / 11),
             (55 if k % 2 == 0 else 38) * s * math.sin(math.pi * k / 11)) for k in range(22)]
    fort = prism_mesh("liberty_fort", star, 0.0, 10 * s, "granite", "granite")
    pedestal = [_box(28 * s, 12 * s, 28 * s, 10 * s, "granite"), _box(20 * s, 20 * s, 20 * s, 22 * s, "granite"),
                _box(24 * s, 3 * s, 24 * s, 42 * s, "granite"), _box(18 * s, 2 * s, 18 * s, 45 * s, "granite")]
    base = _unite([land, fort] + pedestal, "liberty_base", None)
    cmds.parent(base, grp, relative=True)

    # the statue stands on top of the pedestal (47 m); it pivots at its feet to fall
    feet = cmds.group(empty=True, name="liberty_figure_pivot")
    cmds.parent(feet, grp, relative=True)
    cmds.setAttr(feet + ".translateY", 47 * s)
    parts = [frustum_mesh("liberty_robe", 5.5 * s, 3.2 * s, 0, 24 * s, "copper"),
             frustum_mesh("liberty_chest", 3.2 * s, 2.3 * s, 24 * s, 28 * s, "copper"),
             frustum_mesh("liberty_neck", 1.3 * s, 1.1 * s, 28 * s, 29.5 * s, "copper")]
    head = cmds.polySphere(radius=2.6 * s, subdivisionsX=10, subdivisionsY=8, constructionHistory=False)[0]
    cmds.move(0, 31.5 * s, 0, head + ".vtx[*]", relative=True)
    cmds.sets(head, edit=True, forceElement=land_material("copper"))
    parts.append(head)
    for k in range(7):  # the crown's seven rays
        ray = cmds.polyCone(radius=0.35 * s, height=3.5 * s, subdivisionsX=5, constructionHistory=False)[0]
        a = math.radians(-75 + 25 * k)
        cmds.rotate(-55, math.degrees(a), 0, ray + ".vtx[*]", pivot=(0, 0, 0))
        cmds.move(1.8 * s * math.sin(a), 33.8 * s, 1.8 * s * math.cos(a), ray + ".vtx[*]", relative=True)
        cmds.sets(ray, edit=True, forceElement=land_material("copper"))
        parts.append(ray)
    tablet = _box(1.0 * s, 6 * s, 3.2 * s, 18 * s, "copper", -3.6 * s, 0.6 * s)  # held in the left arm
    parts.append(tablet)
    figure = _unite(parts, "liberty_figure", None)
    cmds.parent(figure, feet, relative=True)

    # the raised right arm with the torch, pivoting at the shoulder so it can snap off
    shoulder = cmds.group(empty=True, name="liberty_arm_pivot")
    cmds.parent(shoulder, feet, relative=True)
    cmds.setAttr(shoulder + ".translate", 2.8 * s, 27 * s, 0, type="double3")
    arm_parts = [frustum_mesh("liberty_arm_mesh", 1.0 * s, 0.8 * s, 0, 14 * s, "copper"),
                 frustum_mesh("liberty_torch_handle", 0.7 * s, 0.9 * s, 14 * s, 17 * s, "copper", sides=8)]
    flame = cmds.polyCone(radius=1.1 * s, height=3 * s, subdivisionsX=8, constructionHistory=False)[0]
    cmds.move(0, 18.5 * s, 0, flame + ".vtx[*]", relative=True)
    cmds.sets(flame, edit=True, forceElement=land_material("gold"))
    arm = _unite(arm_parts + [flame], "liberty_arm", None)
    cmds.parent(arm, shoulder, relative=True)
    cmds.setAttr(shoulder + ".rotateZ", -8)  # the arm leans slightly out
    return 93 * s


def key_liberty(p, size):
    """The statue's collapse: it trembles with the quake, then when the
    Battery's tsunami reaches it the torch arm snaps down, the statue topples
    over away from Manhattan and sinks, and the pedestal and island sink after
    it. Returns the frame it's all gone (or None)."""
    if not cmds.objExists(LIBERTY_GRP):
        return None
    L = float(size)
    s = (cmds.getAttr(LIBERTY_GRP + ".unitsPerMetre")
         if cmds.attributeQuery("unitsPerMetre", node=LIBERTY_GRP, exists=True) else L / MANHATTAN_METRES)
    hit = p["start"] + 45.0  # about when the first wave from the Battery arrives
    feet, shoulder, base = "liberty_figure_pivot", "liberty_arm_pivot", "liberty_base"
    for node in (feet, shoulder, base):
        if cmds.objExists(node):
            cmds.cutKey(node, clear=True)
    keys = [
        # the quake makes it tremble
        (feet, "rotateZ", [(p["start"] + 8 + 3 * k, (1.2 if k % 2 else -1.2) * (1 - k / 14.0)) for k in range(14)]),
        # the torch arm snaps down
        (shoulder, "rotateZ", [(hit - 1, -8), (hit + 3, -40), (hit + 9, -125)]),
        (shoulder, "rotateX", [(hit - 1, 0), (hit + 9, 25)]),
        # the statue topples, slowly at first, then crashes over
        (feet, "rotateX", [(hit + 3, 0), (hit + 12, 10), (hit + 20, 38), (hit + 27, 96)]),
        (feet, "translateY", [(hit + 27, 47 * s), (hit + 34, 44 * s), (hit + 75, -120 * s)]),
        (feet, "visibility", [(hit + 74, 1), (hit + 75, 0)]),
        # then the pedestal and the island go under
        (base, "translateY", [(hit + 40, 0), (hit + 60, -10 * s), (hit + 130, -L / 25.0)]),
        (base, "rotateX", [(hit + 40, 0), (hit + 130, 6)]),
        (base, "visibility", [(hit + 129, 1), (hit + 130, 0)]),
    ]
    for node, attr, ks in keys:
        if not cmds.objExists(node):
            continue
        for t, v in ks:
            cmds.setKeyframe(node, attribute=attr, time=t, value=v)
    return hit + 131


def shatter_ground(size, count, faults_n, width, seed, fault_len, terrain=6.0, plants=50, collapse=0.3, grain=1.0,
                   liberty=8.0, boroughs=True,
                   split=True, map_name="manhattan"):
    """Build the land and crack it: land blocks, rifts and slabs.

    Builds outside the undo queue (the API mesh calls can't be undone), so the
    queue is flushed afterwards. Click Shatter Ground again to rebuild.
    map_name "manhattan": the island of Manhattan with its streets and
    buildings, Central Park and the rivers; "square": open hilly land.
    Returns (pieces, land-block pieces, rubble pieces, props, buildings).
    """
    sc = size / 80.0
    epi = epicenter_xz()
    island = nyc_world(size, boroughs) if map_name == "manhattan" else None
    if island:
        terrain = terrain * 0.35  # Manhattan is fairly flat
    groups, _ = plan_ground(size, count, epi, faults_n, fault_len, width * sc, seed, collapse, split, island,
                            grain)
    h = make_terrain(terrain, size, seed)
    surface = manhattan_surface(island) if island else None
    depth = 2.0 + terrain * 1.3
    bottom = -terrain * 1.3 - 2.0 * max(sc, 0.5)
    soil_depth = 0.8 * max(sc, 0.4)
    rng = random.Random(seed * 13 + 1)

    cmds.undoInfo(stateWithoutFlush=False)
    try:
        for node in (GROUND_GRP, PROPS_GRP, WATER, WATER_FX, TSUNAMI_GRP, LIBERTY_GRP, "seismic_water_expr"):
            if cmds.objExists(node):
                cmds.delete(node)
        grp = cmds.group(empty=True, name=GROUND_GRP)
        protos = make_props(seed) if (plants > 0 or island) else None
        building_protos = make_building_protos(PROPS_GRP) if island else None
        names, places, built, data = [], [], [], {}
        faces_by_mat = {}
        counters = {"plate": 0, "slab": 0, "rift": 0}
        progress_start("Building the ground...", len(groups))
        for gi, g in enumerate(groups):
            progress_step(gi, "Building the ground: {} of {} pieces".format(gi, len(groups)))
            role = g["role"]
            if role == "rift":  # rubble: pull the edges in a little so the breaks show
                g = dict(g, cells=[shrink_polygon(c, 0.12 * max(sc, 0.5))[0] for c in g["cells"]])
            px, pz = g["pivot"]
            py = h(px, pz) if role == "plate" else (h(px, pz) + bottom) / 2.0
            verts, counts, connects, mats = build_group_mesh(
                g["cells"], (px, py, pz), h, bottom, soil_depth, max(terrain, 1e-6), surface,
                ("seawall", "schist") if island else ("topsoil", "bedrock"))
            counters[role] += 1
            name = create_mesh("{}_{:04d}".format(role, counters[role]), verts, counts, connects)
            for i, m in enumerate(mats):
                faces_by_mat.setdefault(m, {}).setdefault(name, []).append(i)
            names.append(name)
            places.append((px, py, pz))
            built.append(g)
            pts = [q for c in g["cells"] for q in c]
            cx, cz = sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts)
            area = sum(abs(sum(c[i][0] * c[(i + 1) % len(c)][1] - c[(i + 1) % len(c)][0] * c[i][1]
                               for i in range(len(c)))) / 2.0 for c in g["cells"])
            info = {"role": role, "d": g["d"], "rv": g["rv"], "drop": depth + 4.0 * sc,
                    "c": collapse_order(cx, cz, g["d"], size, seed, g["rv"]), "area": area,
                    "centre": (cx, (h(cx, cz) + bottom) / 2.0, cz)}
            if role == "plate":
                info.update({"axis": g["axis"], "hinge": g["hinge"], "tilt": g["tilt"], "r_in": g["r_in"]})
            data[name] = info
        for name, pos in zip(names, places):
            cmds.xform(name, worldSpace=True, translation=pos)
            if data[name]["role"] == "plate":  # tilt about the hinge, but melt about its own middle
                cmds.xform(name, worldSpace=True, scalePivot=data[name]["centre"])
        if names:  # few calls for all pieces together, which is much faster
            cmds.parent(names, grp)
            for mat, by_name in faces_by_mat.items():
                comps = []
                for name, idx in by_name.items():
                    comps += face_ranges(name, idx)
                cmds.sets(comps, edit=True, forceElement=land_material(mat))
            for name in (names if len(names) <= 700 else []):  # (skipped for the whole city: too slow)
                try:
                    cmds.polySoftEdge(name, angle=60, constructionHistory=False)
                except RuntimeError:
                    pass  # only affects shading; never stop the build for it
        if not cmds.attributeQuery(DATA_ATTR, node=grp, exists=True):
            cmds.addAttr(grp, longName=DATA_ATTR, dataType="string")
        cmds.setAttr(grp + "." + DATA_ATTR, json.dumps(data), type="string")
        props = buildings = 0
        if island:  # the city: buildings on the street grid, trees in Central Park
            try:  # a problem with the buildings must never cost the sea and the tsunami
                buildings, props = place_buildings(
                    island, [(n, g["cells"], pos) for n, g, pos in zip(names, built, places)], h,
                    building_protos, protos["tree"], rng, plants / 100.0)
            except Exception as exc:
                import traceback
                traceback.print_exc()
                print("Ripple: couldn't place every building ({})".format(exc))
            make_water(size, -terrain - 0.4, epi, island)  # just below the lowest street
            try:
                build_liberty(island, -terrain - 0.4, liberty)
            except Exception as exc:
                print("Ripple: couldn't build the Statue of Liberty ({})".format(exc))
        elif protos and plants > 0:
            for name, g, pos in zip(names, built, places):
                props += scatter_props(name, g, pos, h, terrain, size, plants / 100.0, protos, rng)
        ex, ez = epi
        cmds.setAttr(EPICENTER + ".translateY", h(ex, ez) + 0.3)
    finally:
        progress_end()
        cmds.undoInfo(stateWithoutFlush=True)
    cmds.flushUndo()
    cmds.select(EPICENTER)
    try:
        beauty_view(size, island)
    except Exception as exc:  # the look is a bonus; never fail the build for it
        print("Ripple: Beauty View couldn't be set up ({})".format(exc))
        show_land_nicely()
    plates = sum(1 for v in data.values() if v["role"] == "plate")
    rifts = sum(1 for v in data.values() if v["role"] == "rift")
    return len(names), plates, rifts, props, buildings


LIGHTS_GRP = "seismic_lights"
CAMERA = "seismic_cam"


def show_land_nicely():
    """Shaded viewports without wireframe, so the land reads as land."""
    for panel in cmds.getPanel(type="modelPanel") or []:
        try:
            cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded", wireframeOnShaded=False)
        except RuntimeError:
            pass


def _try(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (RuntimeError, TypeError, ValueError):
        return None


def beauty_view(size, island=None):
    """A polished viewport: a warm low sun with shadows, a cool sky fill,
    ambient occlusion, anti-aliasing, haze, a dusk sky, and a camera framing
    the map from over the water. Plain View undoes it."""
    L = float(size)
    # remember the user's background so Plain View can put it back
    if not cmds.optionVar(exists=OPTION_PREFIX + "saved_bg"):
        saved = {"gradient": _try(cmds.displayPref, query=True, displayGradient=True)}
        for key in ("background", "backgroundTop", "backgroundBottom"):
            saved[key] = _try(cmds.displayRGBColor, key, query=True)
        save_option("saved_bg", saved)

    if cmds.objExists(LIGHTS_GRP):
        cmds.delete(LIGHTS_GRP)
    grp = cmds.group(empty=True, name=LIGHTS_GRP)
    sun = cmds.directionalLight(name="seismic_sun", rgb=(1.0, 0.86, 0.68), intensity=1.35)
    sun_t = cmds.listRelatives(sun, parent=True)[0]
    cmds.setAttr(sun_t + ".rotate", -32, 62, 0, type="double3")
    _try(cmds.setAttr, sun + ".useDepthMapShadows", 1)
    _try(cmds.setAttr, sun + ".dmapResolution", 4096)
    _try(cmds.setAttr, sun + ".dmapBias", 0.02)       # no shadow streaks on flat roofs
    _try(cmds.setAttr, sun + ".dmapFilterSize", 3)
    sky = cmds.directionalLight(name="seismic_sky", rgb=(0.55, 0.68, 0.95), intensity=0.45)
    sky_t = cmds.listRelatives(sky, parent=True)[0]
    cmds.setAttr(sky_t + ".rotate", -70, -130, 0, type="double3")
    amb = cmds.ambientLight(name="seismic_ambient", rgb=(0.62, 0.66, 0.76), intensity=0.22)
    amb_t = cmds.listRelatives(amb, parent=True)[0]
    cmds.parent([sun_t, sky_t, amb_t], grp)

    # camera: a three-quarter view from over the water, looking at the middle
    if cmds.objExists(CAMERA):
        cmds.delete(CAMERA)
    city = bool(island and len(island.get("lands", [])) > 1)
    # a near clip that isn't tiny keeps the depth sharp, so faces far away don't flicker black
    cam_t, cam_s = cmds.camera(name=CAMERA, focalLength=32, farClipPlane=L * 30, nearClipPlane=L * 0.02)
    cam_t = cmds.rename(cam_t, CAMERA)
    if island and len(island.get("lands", [])) > 1:  # the whole city, from over the harbour
        x0, x1, z0, z1 = island["box"]
        tx, tz = (x0 + x1) / 2.0, (z0 + z1) / 2.0
        span = max(x1 - x0, z1 - z0)
        eye = (tx - 0.45 * span, 0.42 * span, tz + 0.55 * span)
        target = (tx, 0.0, tz)
    elif island:
        tx, tz = island["to_world"](0.42, 0.0)
        ux, uz = island["up"]
        ex, ez = island["east"]
        eye = (tx - ux * 0.55 * L - ex * 0.42 * L, 0.24 * L, tz - uz * 0.55 * L - ez * 0.42 * L)
        target = (tx, 0.0, tz)
    else:
        eye, target = (-0.75 * L, 0.5 * L, 0.75 * L), (0.0, 0.0, 0.0)
    _try(cmds.viewPlace, cam_t, eye=eye, lookAt=target)

    # Viewport 2.0: anti-aliasing, ambient occlusion and haze
    hw = "hardwareRenderingGlobals"
    for attr, value in (("multiSampleEnable", 1), ("multiSampleCount", 4 if city else 8), ("ssaoEnable", 1),
                        ("ssaoAmount", 1.2), ("ssaoRadius", 12), ("ssaoFilterRadius", 12),
                        ("ssaoSamples", 8 if city else 16), ("consolidateWorld", 1),
                        ("hwFogEnable", 1), ("hwFogFalloff", 0), ("hwFogStart", L * (1.2 if city else 0.6)),
                        ("hwFogEnd", L * (5.0 if city else 3.2)),
                        ("hwFogColorR", 0.78), ("hwFogColorG", 0.80), ("hwFogColorB", 0.86), ("hwFogAlpha", 0.6)):
        _try(cmds.setAttr, "{}.{}".format(hw, attr), value)
    _try(cmds.displayPref, displayGradient=True)
    _try(cmds.displayRGBColor, "backgroundTop", 0.40, 0.52, 0.70)
    _try(cmds.displayRGBColor, "backgroundBottom", 0.93, 0.80, 0.66)
    for panel in cmds.getPanel(type="modelPanel") or []:
        _try(cmds.modelEditor, panel, edit=True, displayAppearance="smoothShaded", wireframeOnShaded=False,
             displayLights="all", shadows=True, grid=False, locators=True, displayTextures=True,
             deformers=False)
    panel = cmds.getPanel(withFocus=True)
    if not panel or cmds.getPanel(typeOf=panel) != "modelPanel":
        panels = cmds.getPanel(type="modelPanel") or []
        visible = cmds.getPanel(visiblePanels=True) or []
        panels = [p for p in panels if p in visible] or panels
        panel = panels[0] if panels else None
    if panel:
        _try(cmds.lookThru, panel, cam_t)


class Cancelled(Exception):
    pass


def progress_start(title, total):
    """A progress bar with a Cancel button (press Esc) for long jobs."""
    _try(cmds.progressWindow, endProgress=True)
    _try(cmds.progressWindow, title="Ripple", status=title, progress=0, maxValue=max(int(total), 1),
         isInterruptable=True)


def progress_step(i, status, every=40):
    if i % every:
        return
    _try(cmds.progressWindow, edit=True, progress=int(i), status=status)
    if _try(cmds.progressWindow, query=True, isCancelled=True) is True:
        raise Cancelled("cancelled")


def progress_end():
    _try(cmds.progressWindow, endProgress=True)


def fast_playback():
    """Smoother playback of a big scene: Maya's parallel evaluation, and
    cached playback (Maya 2019+), which remembers each frame once played so
    the second play runs at full speed."""
    _try(cmds.evaluationManager, mode="parallel")
    _try(cmds.evaluator, name="cache", enable=True)
    _try(cmds.optionVar, intValue=("cachedPlaybackEnable", 1))
    _try(cmds.playbackOptions, playbackSpeed=1.0, maxPlaybackSpeed=0)  # real time


def plain_view():
    """Back to Maya's normal viewport (keeps the scene)."""
    for panel in cmds.getPanel(type="modelPanel") or []:
        _try(cmds.modelEditor, panel, edit=True, displayLights="default", shadows=False, grid=True)
        _try(cmds.lookThru, panel, "persp")
    hw = "hardwareRenderingGlobals"
    for attr in ("ssaoEnable", "hwFogEnable"):
        _try(cmds.setAttr, "{}.{}".format(hw, attr), 0)
    saved = load_option("saved_bg")
    if saved:
        if saved.get("gradient") is not None:
            _try(cmds.displayPref, displayGradient=bool(saved["gradient"]))
        for key in ("background", "backgroundTop", "backgroundBottom"):
            if saved.get(key):
                _try(cmds.displayRGBColor, key, *saved[key][:3])
        cmds.optionVar(remove=OPTION_PREFIX + "saved_bg")
    if cmds.objExists(LIGHTS_GRP):
        cmds.delete(LIGHTS_GRP)


def ground_pieces():
    if not cmds.objExists(GROUND_GRP):
        return []
    return sorted(cmds.listRelatives(GROUND_GRP, children=True, type="transform") or [])


def ground_data():
    if cmds.objExists(GROUND_GRP) and cmds.attributeQuery(DATA_ATTR, node=GROUND_GRP, exists=True):
        try:
            return json.loads(cmds.getAttr(GROUND_GRP + "." + DATA_ATTR) or "{}")
        except ValueError:
            return {}
    return {}


_FAST_KEYS = [True]
_CHECKED = [0]  # how many fast curves have been double-checked  # switched off for the session if the fast way misbehaves


def key_curve(obj, attr, times, values):
    """Key one channel. Fast way: build the whole animation curve in three
    commands (create it, fill every key at once, connect it). If that ever
    gives the wrong result, fall back to setKeyframe, one key at a time.
    Both ways are undoable."""
    if _FAST_KEYS[0]:
        curve = None
        try:
            kind = ("animCurveTA" if attr.startswith("rotate")
                    else "animCurveTU" if attr == "visibility" else "animCurveTL")
            curve = cmds.createNode(kind, name="{}_{}".format(obj, attr))
            flat = []
            for t, v in zip(times, values):
                flat += [t, v]
            cmds.setAttr("{}.ktv[0:{}]".format(curve, len(times) - 1), *flat)
            if _CHECKED[0] >= 25:  # the first curves came out right: trust the rest
                cmds.connectAttr(curve + ".output", "{}.{}".format(obj, attr), force=True)
                return
            _CHECKED[0] += 1
            got_t = cmds.keyframe(curve, query=True, timeChange=True) or []
            got_v = cmds.keyframe(curve, query=True, valueChange=True) or []
            if (len(got_t) == len(times) and abs(got_t[0] - times[0]) < 1e-3
                    and abs(got_t[-1] - times[-1]) < 1e-3 and abs(got_v[-1] - values[-1]) < 1e-3):
                cmds.connectAttr(curve + ".output", "{}.{}".format(obj, attr), force=True)
                return
        except RuntimeError:
            pass
        _FAST_KEYS[0] = False
        if curve and cmds.objExists(curve):
            cmds.delete(curve)
    for t, v in zip(times, values):
        cmds.setKeyframe(obj, attribute=attr, time=t, value=v)


def quake_apply(targets, p, chunk_name="Seismic Quake"):
    """Key the earthquake onto every target. One undo chunk.

    Ground pieces move by their role (plates tilt into the rift, rubble falls,
    slabs shake); any other object just shakes.
    Returns (number keyed, last frame, warnings).
    """
    ex, ez = epicenter_xz()
    data = ground_data()
    warnings, last = [], p["start"]
    keyed = 0
    # first pass: what each piece is, and when the last one goes
    pieces = []
    for index, obj in enumerate(sorted(targets)):
        if obj not in data and any(cmds.getAttr("{}.{}".format(obj, a), lock=True) for a in QUAKE_ATTRS):
            warnings.append("{} has locked channels, skipped".format(obj))
            continue
        info = dict(data.get(obj) or {"role": "object"})
        x, _, z = world_pos(obj)
        dx, dz = x - ex, z - ez
        dist = math.hypot(dx, dz)
        if info["role"] in ("object", "slab", "rift"):
            info["d"] = dist
        if dist > 1e-6:
            info["u"] = (dx / dist, dz / dist)
        else:
            a = random.Random(index).uniform(0, 2 * math.pi)
            info["u"] = (math.cos(a), math.sin(a))
        pieces.append((obj, info))
    # who melts when: small rubble first, bigger land later, partly by distance
    # from the epicenter and partly by a lumpy pattern so it's irregular
    areas = sorted(info.get("area", 0.0) for _, info in pieces)
    far = max([info.get("d", 0.0) for _, info in pieces] + [1.0])
    for _, info in pieces:
        a = info.get("area", areas[len(areas) // 2] if areas else 0.0)
        size_rank = sum(1 for x in areas if x < a) / float(max(len(areas) - 1, 1))
        info["size_rank"] = size_rank
        order = 0.5 * size_rank + 0.25 * info.get("d", 0.0) / far + 0.25 * info.get("c", 0.5)
        if info["role"] == "rift":
            order *= 0.35  # broken rubble in the rifts goes first
        info["order"] = order
    # spread evenly so every aftershock takes its share of the land
    ranked = sorted(range(len(pieces)), key=lambda i: pieces[i][1]["order"])
    for rank, i in enumerate(ranked):
        pieces[i][1]["order"] = min(rank / float(max(len(pieces), 1)), 0.999)
    triggers = melt_triggers(p)
    ends = []
    for _, info in pieces:
        info["melt"] = melt_plan(info, p, triggers)
        if info["melt"]:
            ends.append(info["melt"][3] if info["melt"][3] is not None else info["melt"][0] + info["melt"][1])
    first_melt = min([i["melt"][0] for _, i in pieces if i["melt"]] or [None]) if ends else None
    p = dict(p, tremor_end=max(ends) + 10.0 if ends else p["start"] + 120.0)
    shocks = aftershocks(p)
    cmds.undoInfo(openChunk=True, chunkName=chunk_name)
    try:
        progress_start("Animating the quake...", len(pieces))
        for pi, (obj, info) in enumerate(pieces):
            progress_step(pi, "Animating the quake: {} of {} pieces".format(pi, len(pieces)))
            if cmds.keyframe(obj, query=True, keyframeCount=True):
                rest = {a: cmds.getAttr("{}.{}".format(obj, a), time=p["start"]) for a in QUAKE_ATTRS}
            else:  # not animated yet: the plain value is the resting one (much faster)
                rest = {}
                for group in ("translate", "rotate", "scale"):
                    vals = cmds.getAttr("{}.{}".format(obj, group))
                    vals = vals[0] if isinstance(vals, list) and vals else vals
                    if not isinstance(vals, (tuple, list)) or len(vals) != 3:
                        vals = [cmds.getAttr("{}.{}{}".format(obj, group, axis)) for axis in "XYZ"]
                    for axis, v in zip("XYZ", vals):
                        rest[group + axis] = v
            cmds.cutKey(obj, attribute=QUAKE_ATTRS + ["visibility"], clear=True)
            cmds.setAttr(obj + ".visibility", 1)
            times, end = piece_times(info, p)
            curves = {a: [] for a in QUAKE_ATTRS}
            for t in times:
                off = piece_offset(t, info, p, shocks)
                for a, v in zip(QUAKE_ATTRS, off):
                    curves[a].append(rest[a] * v if a.startswith("scale") else rest[a] + v)
            for attr, values in curves.items():
                if max(values) - min(values) < 1e-6 and abs(values[0] - rest[attr]) < 1e-6:
                    continue  # this channel never moves: no curve needed
                key_curve(obj, attr, times, values)
            gone = piece_vanish(info, p)
            if gone is not None:  # lost in the abyss: hide it once it's deep down
                key_curve(obj, "visibility", [times[0], gone - 0.05, gone], [1.0, 1.0, 0.0])
            last = max(last, end)
            keyed += 1
        if p["fracture"]:
            calm = key_tsunami(p, shocks, p.get("size", 80))
            if calm:
                last = max(last, calm)
            fallen = key_liberty(p, p.get("size", 80))
            if fallen:
                last = max(last, fallen)
    finally:
        progress_end()
        cmds.undoInfo(closeChunk=True)

    # the timeline ends just after the last piece is gone
    cmds.playbackOptions(maxTime=math.ceil(last) + 5, animationEndTime=max(
        math.ceil(last) + 5, cmds.playbackOptions(query=True, animationEndTime=True)))
    return keyed, last, warnings, first_melt


# ==========================================================================
# Graph widgets
# ==========================================================================

class RippleGraph(QtWidgets.QWidget):
    """Ripple tab: one curve per object plus a row of dots."""

    DRIVER = QtGui.QColor(83, 74, 183)
    FOLLOWER = QtGui.QColor(127, 119, 221)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self.count, self.delay, self.falloff = 5, 3, 0.8
        self.curve = None  # None = sample wave

    def set_params(self, count, delay, falloff):
        self.count, self.delay, self.falloff = max(2, count), delay, falloff
        self.update()

    def set_curve(self, curve):
        self.curve = curve
        self.update()

    def _driver_value(self, t):
        if self.curve is None:  # sample: a decaying bounce
            if t < 0:
                return 0.0
            return math.sin(t / 72.0 * 4 * math.pi) * math.exp(-t / 60.0)
        frames = [f for f, _ in self.curve]
        values = [v for _, v in self.curve]
        base = values[0]
        t += frames[0]
        if t <= frames[0]:
            return 0.0
        if t >= frames[-1]:
            return values[-1] - base
        for i in range(len(frames) - 1):
            if frames[i] <= t <= frames[i + 1]:
                k = (t - frames[i]) / float(frames[i + 1] - frames[i])
                return values[i] + (values[i + 1] - values[i]) * k - base
        return 0.0

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.fillRect(self.rect(), QtGui.QColor(42, 42, 42))

        w, h = self.width(), self.height()
        left, right, top, graph_bottom = 12, w - 12, 12, h - 50
        mid = (top + graph_bottom) / 2.0
        length = 72
        if self.curve:
            length = int(self.curve[-1][0] - self.curve[0][0]) or 72
        frames = length + self.delay * (self.count - 1)
        sx = (right - left) / float(max(frames, 1))

        peak = max(abs(self._driver_value(f)) for f in range(length + 1)) or 1.0
        amp = (graph_bottom - top) / 2.0 * 0.9 / peak

        p.setPen(QtGui.QPen(QtGui.QColor(80, 80, 80), 1))
        p.drawLine(int(left), int(mid), int(right), int(mid))

        for i in reversed(range(self.count)):
            color = QtGui.QColor(self.DRIVER if i == 0 else self.FOLLOWER)
            color.setAlphaF(1.0 - i / float(self.count + 1))
            p.setPen(QtGui.QPen(color, 2.5 if i == 0 else 1.5))
            strength = self.falloff ** i
            path = QtGui.QPainterPath()
            for f in range(frames + 1):
                v = self._driver_value(f - i * self.delay) * strength
                x, y = left + f * sx, mid - v * amp
                if f == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            p.drawPath(path)

        dots_y = h - 24
        gap = (right - left - 20) / float(self.count - 1)
        p.setPen(QtGui.QPen(QtGui.QColor(80, 80, 80), 1))
        p.drawLine(int(left + 10), int(dots_y), int(right - 10), int(dots_y))
        p.setPen(QtCore.Qt.NoPen)
        for i in range(self.count):
            color = QtGui.QColor(self.DRIVER if i == 0 else self.FOLLOWER)
            color.setAlphaF(1.0 - i / float(self.count + 1))
            p.setBrush(color)
            r = max(3.0, 12.0 * self.falloff ** i)
            p.drawEllipse(QtCore.QPointF(left + 10 + i * gap, dots_y), r, r)
        p.end()


class Seismograph(QtWidgets.QWidget):
    """Seismic tab: ground movement over time at three distances, like a
    real seismograph. Ticks show when the P and S waves arrive; a trace that
    ends below its line means the ground there cracked and dropped."""

    COLORS = [QtGui.QColor(226, 94, 74), QtGui.QColor(239, 159, 39), QtGui.QColor(93, 202, 165)]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(190)
        self.params = None
        self.half = 15.0

    def set_params(self, params, half):
        self.params, self.half = params, half
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor(42, 42, 42))
        if not self.params:
            painter.end()
            return
        p = self.params
        w, h = self.width(), self.height()
        left, right = 64, w - 10
        dists = [self.half * f for f in (0.15, 0.5, 0.9)]
        names = ["near", "mid", "far"]
        start = p["start"]
        if p["fracture"] and p.get("total", True):
            end = start + p.get("duration", 240) + 40  # tremors last until the land is gone
        else:
            end = quake_end(p, dists[-1]) + 4
        p = dict(p, tremor_end=end)
        shocks = aftershocks(p)
        sx = (right - left) / float(max(end - start + 2, 1))
        band = (h - 10) / 3.0
        amp0, _, _ = quake_numbers(p)
        scale = band * 0.38 / max(amp0 * 1.4, 0.05)

        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        for i, d in enumerate(dists):
            mid = 5 + band * i + band / 2.0
            painter.setPen(QtGui.QPen(QtGui.QColor(80, 80, 80), 1))
            painter.drawLine(int(left), int(mid), int(right), int(mid))
            painter.setPen(QtGui.QColor(190, 190, 190))
            painter.drawText(6, int(mid - 2), names[i])
            painter.drawText(6, int(mid + 12), "{:.0f} u".format(d))

            t_p, t_s = arrivals(d, p)
            for t_arr, label, on in ((t_p, "P", p["use_p"]), (t_s, "S", p["use_s"])):
                if on and t_arr <= end:
                    x = left + (t_arr - start + 1) * sx
                    painter.setPen(QtGui.QPen(QtGui.QColor(130, 130, 130), 1, QtCore.Qt.DashLine))
                    painter.drawLine(int(x), int(mid - band * 0.42), int(x), int(mid + band * 0.42))
                    painter.drawText(int(x + 2), int(mid - band * 0.3), label)

            painter.setPen(QtGui.QPen(self.COLORS[i], 1.6))
            path = QtGui.QPainterPath()
            steps = int((end - start + 2) * 2)
            for s in range(steps + 1):
                t = start - 1 + s * 0.5
                rad, vert, side, _ = shake(t, d, p, 0.6, shocks)
                y = mid - (side + vert + rad) * scale
                x = left + (t - start + 1) * sx
                if s == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            painter.drawPath(path)
        painter.end()


# ==========================================================================
# Ripple tab
# ==========================================================================

class RipplePanel(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.driver, self.followers = None, []
        self.previewing = False
        self.user_presets = load_user_presets()
        self._loading_preset = False
        self._warnings = []
        self._build_ui()
        settings = load_option("settings")
        if settings:
            self._apply_settings(settings)
        self._refresh_graph()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Preset:"))
        self.preset_box = QtWidgets.QComboBox()
        self._fill_presets()
        row.addWidget(self.preset_box, 1)
        self.save_btn = QtWidgets.QPushButton("Save")
        self.save_btn.setToolTip("Save the current settings as your own preset")
        row.addWidget(self.save_btn)
        layout.addLayout(row)

        self.driver_label = QtWidgets.QLabel("Driver: (none)")
        layout.addWidget(self.driver_label)
        self.object_list = QtWidgets.QListWidget()
        self.object_list.setMaximumHeight(90)
        layout.addWidget(self.object_list)
        self.load_btn = QtWidgets.QPushButton("Load Selection")
        self.load_btn.setToolTip("First selected object = driver, the rest = followers")
        layout.addWidget(self.load_btn)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Order:"))
        self.order_box = QtWidgets.QComboBox()
        self.order_box.addItems(ORDERS)
        self.order_box.setToolTip("Which follower moves first")
        row.addWidget(self.order_box, 1)
        layout.addLayout(row)

        self.delay_slider, r1 = make_slider("Delay per object", 0, 20, 3, lambda v: "{} fr".format(v))
        self.falloff_slider, r2 = make_slider("Falloff", 10, 100, 80, lambda v: "{} %".format(v))
        layout.addLayout(r1)
        layout.addLayout(r2)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Channels:"))
        self.channel_boxes = {}
        for name in CHANNELS:
            box = QtWidgets.QCheckBox(name)
            box.setChecked(name != "Scale")
            self.channel_boxes[name] = box
            row.addWidget(box)
        layout.addLayout(row)

        self.graph = RippleGraph()
        layout.addWidget(self.graph)

        row = QtWidgets.QHBoxLayout()
        self.preview_btn = QtWidgets.QPushButton("Preview")
        self.preview_btn.setToolTip("Try the ripple and play it. Revert takes it back.")
        self.revert_btn = QtWidgets.QPushButton("Revert")
        self.apply_btn = QtWidgets.QPushButton("Apply")
        for b in (self.preview_btn, self.revert_btn, self.apply_btn):
            row.addWidget(b)
        layout.addLayout(row)

        self.status = QtWidgets.QLabel("Ready. Select a driver, then the objects to follow.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.load_btn.clicked.connect(self.load_selection)
        self.apply_btn.clicked.connect(self.apply)
        self.preview_btn.clicked.connect(self.preview)
        self.revert_btn.clicked.connect(lambda: self.revert())
        self.save_btn.clicked.connect(self.save_preset)
        self.preset_box.activated.connect(self._preset_chosen)
        self.order_box.currentIndexChanged.connect(self._order_changed)
        self.delay_slider.valueChanged.connect(self._settings_changed)
        self.falloff_slider.valueChanged.connect(self._settings_changed)
        for box in self.channel_boxes.values():
            box.toggled.connect(self._settings_changed)
            box.toggled.connect(self._refresh_curve)

    # ---- presets and settings --------------------------------------------
    def _fill_presets(self, select=None):
        self.preset_box.blockSignals(True)
        self.preset_box.clear()
        self.preset_box.addItem("Custom")
        for name in BUILTIN_PRESETS:
            self.preset_box.addItem(name)
        for name in sorted(self.user_presets):
            self.preset_box.addItem("{} (mine)".format(name), name)
        if select:
            i = self.preset_box.findText(select)
            if i >= 0:
                self.preset_box.setCurrentIndex(i)
        self.preset_box.blockSignals(False)

    def current_settings(self):
        return {
            "delay": self.delay_slider.value(),
            "falloff": self.falloff_slider.value(),
            "order": self.order_box.currentIndex(),
            "channels": [n for n, b in self.channel_boxes.items() if b.isChecked()],
        }

    def _apply_settings(self, s):
        self._loading_preset = True
        try:
            self.delay_slider.setValue(int(s.get("delay", 3)))
            self.falloff_slider.setValue(int(s.get("falloff", 80)))
            self.order_box.setCurrentIndex(int(s.get("order", 0)))
            chans = s.get("channels", ["Translate", "Rotate"])
            for name, box in self.channel_boxes.items():
                box.setChecked(name in chans)
        finally:
            self._loading_preset = False
        self._refresh_graph()

    def _preset_chosen(self, index):
        text = self.preset_box.itemText(index)
        user_name = self.preset_box.itemData(index)
        if user_name and user_name in self.user_presets:
            self._apply_settings(self.user_presets[user_name])
        elif text in BUILTIN_PRESETS:
            self._apply_settings(BUILTIN_PRESETS[text])
        else:
            return
        say(self.status, "Preset loaded: {}".format(text))

    def save_preset(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "Save preset", "Preset name:")
        name = name.strip() if ok else ""
        if not name:
            return
        if name in BUILTIN_PRESETS:
            say(self.status, "That name is a built-in preset. Try another.", error=True)
            return
        self.user_presets[name] = self.current_settings()
        try:
            save_user_presets(self.user_presets)
        except (IOError, OSError) as exc:
            say(self.status, "Couldn't save the preset file: {}".format(exc), error=True)
            return
        self._fill_presets(select="{} (mine)".format(name))
        say(self.status, "Saved preset: {}".format(name))

    def save_settings(self):
        save_option("settings", self.current_settings())

    # ---- helpers ---------------------------------------------------------
    def _attrs(self):
        attrs = []
        for name, box in self.channel_boxes.items():
            if box.isChecked():
                attrs.extend(CHANNELS[name])
        return attrs

    def _settings_changed(self, *_):
        if not self._loading_preset:
            self.preset_box.setCurrentIndex(0)  # back to "Custom"
        self._refresh_graph()

    def _order_changed(self, *_):
        self._settings_changed()
        self._refresh_list()

    def _refresh_graph(self, *_):
        count = len(self.followers) + 1 if self.driver else 5
        self.graph.set_params(count, self.delay_slider.value(), self.falloff_slider.value() / 100.0)

    def _refresh_curve(self, *_):
        if self.driver and cmds.objExists(self.driver):
            self.graph.set_curve(driver_curve(self.driver, self._attrs()))

    def _ordered_followers(self):
        return sort_followers(self.driver, self.followers, self.order_box.currentIndex())

    def _refresh_list(self):
        self.object_list.clear()
        if self.driver and all(cmds.objExists(o) for o in [self.driver] + self.followers):
            self.object_list.addItems(self._ordered_followers())
        else:
            self.object_list.addItems(self.followers)

    def _check_ready(self):
        if not self.driver:
            say(self.status, "Click Load Selection first.", error=True)
            return None
        missing = [o for o in [self.driver] + self.followers if not cmds.objExists(o)]
        if missing:
            say(self.status, "These objects no longer exist: {}. Load Selection again.".format(", ".join(missing)), error=True)
            return None
        attrs = self._attrs()
        if not attrs:
            say(self.status, "Check at least one channel.", error=True)
            return None
        return attrs

    def _run(self, chunk_name):
        attrs = self._check_ready()
        if attrs is None:
            return False
        try:
            self._warnings = ripple_apply(
                self.driver, self._ordered_followers(), attrs,
                self.delay_slider.value(), self.falloff_slider.value() / 100.0,
                chunk_name=chunk_name,
            )
        except ValueError as exc:
            say(self.status, str(exc), error=True)
            return False
        return True

    # ---- actions ---------------------------------------------------------
    def load_selection(self):
        sel = cmds.ls(selection=True, type="transform")
        if len(sel) < 2:
            say(self.status, "Select at least 2 objects: the driver first, then the followers.", error=True)
            return
        if self.previewing:
            self.revert(quiet=True)
        self.driver, self.followers = sel[0], sel[1:]
        self.driver_label.setText("Driver: {}".format(self.driver))
        self._refresh_list()
        self._refresh_curve()
        self._refresh_graph()
        say(self.status, "Loaded {} followers.".format(len(self.followers)))

    def preview(self):
        if self.previewing:
            self.revert(quiet=True)  # replace the old preview with the new settings
        if not self._run("Ripple Preview"):
            return
        self.previewing = True
        cmds.currentTime(cmds.playbackOptions(query=True, minTime=True))
        cmds.play(forward=True)
        say(self.status, "Previewing. Click Apply to keep it, or Revert to take it back.")

    def revert(self, quiet=False):
        if not self.previewing:
            if not quiet:
                say(self.status, "Nothing to revert. Click Preview first.", error=True)
            return
        cmds.play(state=False)
        cmds.undo()  # the whole preview is one undo chunk
        self.previewing = False
        if not quiet:
            say(self.status, "Preview reverted. The scene is back to how it was.")

    def apply(self):
        if self.previewing:
            cmds.play(state=False)
            self.previewing = False
            say(self.status, "Kept the preview. Ctrl+Z undoes it in one step.")
            return
        if not self._run("Ripple"):
            return
        msg = "Rippled {} objects. Ctrl+Z undoes it in one step.".format(len(self.followers))
        if self._warnings:
            msg += " " + "; ".join(self._warnings)
        say(self.status, msg)


# ==========================================================================
# Seismic tab
# ==========================================================================

class SeismicPanel(QtWidgets.QWidget):

    TARGETS = ["Shattered ground", "Selected objects", "Ground + selected"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.previewing = False
        self._loading = False
        self._build_ui()
        settings = load_option("seismic_settings_v5")
        if settings:
            self._apply_settings(settings)
        self._refresh_graph()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Preset:"))
        self.preset_box = QtWidgets.QComboBox()
        self.preset_box.addItems(["Custom"] + list(SEISMIC_PRESETS))
        row.addWidget(self.preset_box, 1)
        layout.addLayout(row)

        # ---- 1. ground ----
        title = QtWidgets.QLabel("<b>1. Ground</b>")
        layout.addWidget(title)
        row = QtWidgets.QHBoxLayout()
        self.epi_btn = QtWidgets.QPushButton("Place Epicenter")
        self.epi_btn.setToolTip("Creates a red locator where the quake starts. Move it anywhere on the ground.")
        self.shatter_btn = QtWidgets.QPushButton("Shatter Ground")
        self.shatter_btn.setToolTip("Builds the land and cracks it: jagged faults run out from the epicenter, "
                                    "with rubble in the rifts and big plates of land between them.")
        row.addWidget(self.epi_btn)
        row.addWidget(self.shatter_btn)
        layout.addLayout(row)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Map:"))
        self.map_box = QtWidgets.QComboBox()
        self.map_box.addItems(["Manhattan", "Square land"])
        self.map_box.setToolTip("Manhattan: the island with its street grid, buildings, Central Park and rivers. "
                                "Square land: open hilly land with trees.")
        row.addWidget(self.map_box, 1)
        layout.addLayout(row)
        self.size_slider, r = make_slider("Ground size", 20, 200, 80, lambda v: "{} u".format(v))
        layout.addLayout(r)
        self.pieces_slider, r = make_slider("Land detail", 20, 800, 250, str)
        self.pieces_slider.setToolTip("How finely the land is built. More = smoother hills, slower to build.")
        layout.addLayout(r)
        self.terrain_slider, r = make_slider("Terrain height", 0, 30, 6, lambda v: "{} u".format(v))
        self.terrain_slider.setToolTip("How hilly the land is. 0 = flat.")
        layout.addLayout(r)
        self.faults_slider, r = make_slider("Faults", 2, 8, 4, str)
        self.faults_slider.setToolTip("How many main cracks tear out from the epicenter. "
                                      "The land between them becomes big plates.")
        layout.addLayout(r)
        self.width_slider, r = make_slider("Rift width", 1, 12, 4, lambda v: "{} u".format(v))
        self.width_slider.setToolTip("How wide the rifts are at the epicenter (for an 80-unit ground).")
        layout.addLayout(r)
        self.grain_slider, r = make_slider("Piece size", 50, 150, 100, lambda v: "{} %".format(v))
        self.grain_slider.setToolTip("How big the broken pieces of ground are. Smaller = more pieces, "
                                     "slower to build and play.")
        layout.addLayout(r)
        self.liberty_slider, r = make_slider("Liberty size", 1, 12, 8, lambda v: "true scale" if v == 1 else "{}x".format(v))
        self.liberty_slider.setToolTip("The Statue of Liberty's size. 1 = true to scale against Manhattan "
                                       "(tiny); 8 = enlarged like the skyline so it reads clearly.")
        layout.addLayout(r)
        self.collapse_slider, r = make_slider("Collapse zone", 0, 60, 30, lambda v: "{} %".format(v))
        self.collapse_slider.setToolTip("The area around the epicenter that breaks into rubble and caves in, "
                                        "as a share of how far the faults run.")
        layout.addLayout(r)
        self.plants_slider, r = make_slider("Plants and rocks", 0, 100, 50, lambda v: "{} %".format(v))
        self.plants_slider.setToolTip("Grass, bushes and boulders on the land. 0 = bare ground.")
        layout.addLayout(r)
        self.boroughs_box = QtWidgets.QCheckBox("Add the Bronx, Queens, Brooklyn and Staten Island")
        self.boroughs_box.setChecked(True)
        self.boroughs_box.setToolTip("All five boroughs of New York (Manhattan map only). Every borough has "
                                     "buildings that collapse and sink, and sends out its own tsunami. "
                                     "Slower to build: turn off for just Manhattan.")
        layout.addWidget(self.boroughs_box)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Random seed"))
        self.seed_box = QtWidgets.QSpinBox()
        self.seed_box.setRange(0, 9999)
        self.seed_box.setValue(1)
        self.seed_box.setToolTip("Change it for a different crack pattern. Same seed = same cracks.")
        row.addWidget(self.seed_box)
        row.addStretch(1)
        layout.addLayout(row)

        # ---- 2. earthquake ----
        layout.addWidget(QtWidgets.QLabel("<b>2. Earthquake</b>"))
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Shake:"))
        self.target_box = QtWidgets.QComboBox()
        self.target_box.addItems(self.TARGETS)
        self.target_box.setToolTip("Selected objects shake but don't crack. Only ground pieces crack.")
        row.addWidget(self.target_box, 1)
        layout.addLayout(row)

        self.mag_slider, r = make_slider("Magnitude", 1, 10, 7, str)
        layout.addLayout(r)
        self.speed_slider, r = make_slider("Wave speed", 2, 80, 20,
                                           lambda v: "{:.1f} u/fr".format(v / 10.0))
        layout.addLayout(r)
        self.damp_slider, r = make_slider("Damping", 0, 100, 25, lambda v: "{} %".format(v))
        layout.addLayout(r)
        self.thr_slider, r = make_slider("Crack threshold", 5, 100, 35, lambda v: "{} %".format(v))
        layout.addLayout(r)

        row = QtWidgets.QHBoxLayout()
        self.p_box = QtWidgets.QCheckBox("P-wave")
        self.p_box.setToolTip("Arrives first: a quick push and pull, away from the epicenter.")
        self.s_box = QtWidgets.QCheckBox("S-wave")
        self.s_box.setToolTip("Arrives later: big sideways and up-down shaking.")
        self.frac_box = QtWidgets.QCheckBox("Fracture")
        self.frac_box.setToolTip("Ground pieces where the shaking is strong enough crack loose.")
        for b in (self.p_box, self.s_box, self.frac_box):
            b.setChecked(True)
            row.addWidget(b)
        layout.addLayout(row)
        self.vanish_box = QtWidgets.QCheckBox("Pieces melt away and disappear")
        self.vanish_box.setToolTip("Like a melting iceberg: pieces sink into the ground while shrinking, "
                                   "then are gone for good. Off: they sink below the ground and stay.")
        self.vanish_box.setChecked(True)
        layout.addWidget(self.vanish_box)
        self.total_box = QtWidgets.QCheckBox("Keep melting until everything is gone")
        self.total_box.setToolTip("Each aftershock melts away another batch of pieces, small ones first, "
                                  "until nothing is left. Off: only the rifts and crater melt. "
                                  "(Changing this needs Shatter Ground again.)")
        self.total_box.setChecked(True)
        layout.addWidget(self.total_box)
        self.duration_slider, r = make_slider("Collapse duration", 60, 600, 240, lambda v: "{} fr".format(v))
        self.duration_slider.setToolTip("How long the aftershocks keep coming. The last pieces melt shortly after.")
        layout.addLayout(r)

        self.graph = Seismograph()
        layout.addWidget(self.graph)
        row = QtWidgets.QHBoxLayout()
        self.beauty_btn = QtWidgets.QPushButton("Beauty View")
        self.beauty_btn.setToolTip("Sun and shadows, ambient occlusion, haze, a dusk sky and a framed camera.")
        self.plain_btn = QtWidgets.QPushButton("Plain View")
        self.plain_btn.setToolTip("Back to Maya's normal viewport and the persp camera.")
        row.addWidget(self.beauty_btn)
        row.addWidget(self.plain_btn)
        layout.addLayout(row)
        self.info = QtWidgets.QLabel("")
        self.info.setWordWrap(True)
        layout.addWidget(self.info)

        row = QtWidgets.QHBoxLayout()
        self.preview_btn = QtWidgets.QPushButton("Preview")
        self.revert_btn = QtWidgets.QPushButton("Revert")
        self.apply_btn = QtWidgets.QPushButton("Apply")
        for b in (self.preview_btn, self.revert_btn, self.apply_btn):
            row.addWidget(b)
        layout.addLayout(row)

        self.status = QtWidgets.QLabel("Step 1: Place Epicenter. Step 2: Shatter Ground. Step 3: Preview.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.epi_btn.clicked.connect(self.place_epicenter)
        self.beauty_btn.clicked.connect(self.beauty)
        self.plain_btn.clicked.connect(self.plain)
        self.shatter_btn.clicked.connect(self.shatter)
        self.preview_btn.clicked.connect(self.preview)
        self.revert_btn.clicked.connect(lambda: self.revert())
        self.apply_btn.clicked.connect(self.apply)
        self.preset_box.activated.connect(self._preset_chosen)
        for s in (self.mag_slider, self.speed_slider, self.damp_slider, self.thr_slider):
            s.valueChanged.connect(self._quake_changed)
        for b in (self.p_box, self.s_box, self.frac_box, self.vanish_box, self.total_box):
            b.toggled.connect(self._quake_changed)
        self.duration_slider.valueChanged.connect(self._quake_changed)
        self.size_slider.valueChanged.connect(self._refresh_graph)
        # the quake strength and damping scale with the ground size, so a
        # bigger continent cracks over a proportionally bigger area

    # ---- settings --------------------------------------------------------
    def params(self):
        return {
            "start": cmds.playbackOptions(query=True, minTime=True),
            "mag": self.mag_slider.value(),
            "speed": self.speed_slider.value(),
            "damping": self.damp_slider.value(),
            "threshold": self.thr_slider.value(),
            "use_p": self.p_box.isChecked(),
            "use_s": self.s_box.isChecked(),
            "fracture": self.frac_box.isChecked(),
            "vanish": self.vanish_box.isChecked(),
            "total": self.total_box.isChecked(),
            "duration": self.duration_slider.value(),
            "seed": self.seed_box.value(),
            "size": self.size_slider.value(),
        }

    def current_settings(self):
        s = self.params()
        s.pop("start")
        s.update({
            "size": self.size_slider.value(),
            "pieces": self.pieces_slider.value(),
            "terrain": self.terrain_slider.value(),
            "faults": self.faults_slider.value(),
            "width": self.width_slider.value(),
            "plants": self.plants_slider.value(),
            "collapse": self.collapse_slider.value(),
            "grain": self.grain_slider.value(),
            "liberty": self.liberty_slider.value(),
            "map": self.map_box.currentIndex(),
            "boroughs": self.boroughs_box.isChecked(),
            "target": self.target_box.currentIndex(),
        })
        return s

    def _apply_settings(self, s):
        self._loading = True
        try:
            sliders = {"mag": self.mag_slider, "speed": self.speed_slider, "damping": self.damp_slider,
                       "threshold": self.thr_slider, "size": self.size_slider,
                       "pieces": self.pieces_slider, "terrain": self.terrain_slider,
                       "faults": self.faults_slider, "width": self.width_slider,
                       "plants": self.plants_slider, "collapse": self.collapse_slider,
                       "duration": self.duration_slider, "grain": self.grain_slider,
                       "liberty": self.liberty_slider}
            for key, slider in sliders.items():
                if key in s:
                    slider.setValue(int(s[key]))
            for key, box in (("use_p", self.p_box), ("use_s", self.s_box), ("fracture", self.frac_box),
                             ("vanish", self.vanish_box), ("total", self.total_box),
                             ("boroughs", self.boroughs_box)):
                if key in s:
                    box.setChecked(bool(s[key]))
            if "seed" in s:
                self.seed_box.setValue(int(s["seed"]))
            if "target" in s:
                self.target_box.setCurrentIndex(int(s["target"]))
            if "map" in s:
                self.map_box.setCurrentIndex(int(s["map"]))
        finally:
            self._loading = False
        self._refresh_graph()

    def save_settings(self):
        save_option("seismic_settings_v5", self.current_settings())

    def _preset_chosen(self, index):
        name = self.preset_box.itemText(index)
        if name in SEISMIC_PRESETS:
            self._apply_settings(SEISMIC_PRESETS[name])
            say(self.status, "Preset loaded: {}".format(name))

    def _quake_changed(self, *_):
        if not self._loading:
            self.preset_box.setCurrentIndex(0)
        self._refresh_graph()

    def _refresh_graph(self, *_):
        p = self.params()
        half = self.size_slider.value() / 2.0
        self.graph.set_params(p, half)
        length = self.fault_length()
        if not p["fracture"]:
            text = "Fracture is off: the land only shakes."
        elif length >= half * 1.39:
            text = "Faults run to the edge of the land."
        else:
            text = ("Faults run about {:.0f} units from the epicenter; farther out the land only shakes. "
                    "(Click Shatter Ground again after changing Magnitude, Damping or Crack threshold.)").format(length)
        if not (p["use_p"] or p["use_s"]):
            text = "Turn on the P-wave or the S-wave."
        self.info.setText(text)

    # ---- actions ---------------------------------------------------------
    def beauty(self):
        island = manhattan_frame(self.size_slider.value()) if self.map_box.currentIndex() == 0 else None
        try:
            beauty_view(self.size_slider.value(), island)
            say(self.status, "Beauty View on: looking through seismic_cam. Plain View switches back.")
        except Exception as exc:
            say(self.status, "Couldn't set up Beauty View: {}".format(exc), error=True)

    def plain(self):
        plain_view()
        say(self.status, "Plain View: Maya's normal viewport and the persp camera.")

    def fault_length(self):
        """How far the faults run, from how strong the quake is."""
        half = self.size_slider.value() / 2.0
        radius = crack_radius(self.params())
        if radius is None:
            radius = half * 1.4
        return min(max(radius, half * 0.3), half * 1.4)

    def place_epicenter(self):
        loc, created = ensure_epicenter()
        cmds.select(loc)
        if created:
            say(self.status, "Epicenter placed at the centre. Move it if you like (W key), then click Shatter Ground.")
        else:
            say(self.status, "Epicenter selected. Move it (W key), then click Shatter Ground to crack around the new spot.")

    def shatter(self):
        if self.previewing:
            self.revert(quiet=True)
        ensure_epicenter()
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        _try(cmds.refresh, suspend=True)  # build first, draw once at the end
        try:
            made, plates, rifts, props, buildings = shatter_ground(
                self.size_slider.value(), self.pieces_slider.value(), self.faults_slider.value(),
                float(self.width_slider.value()), self.seed_box.value(), self.fault_length(),
                terrain=float(self.terrain_slider.value()), plants=self.plants_slider.value(),
                collapse=self.collapse_slider.value() / 100.0, grain=self.grain_slider.value() / 100.0,
                liberty=float(self.liberty_slider.value()),
                boroughs=self.boroughs_box.isChecked(),
                split=self.total_box.isChecked(),
                map_name="manhattan" if self.map_box.currentIndex() == 0 else "square")
        except Exception as exc:  # report instead of crashing the window
            import traceback
            traceback.print_exc()  # full details in the Script Editor
            say(self.status, "Couldn't shatter the ground: {}".format(exc), error=True)
            return
        finally:
            _try(cmds.refresh, suspend=False)
            QtWidgets.QApplication.restoreOverrideCursor()
        if buildings:
            what = "{} buildings and {} trees in Central Park".format(buildings, props)
        else:
            what = "{} trees, plants and rocks".format(props)
        say(self.status, "Land built: {} pieces ({} in rifts and crater), {}. "
                         "Click Preview to start the quake. (To rebuild, click Shatter Ground again.)"
            .format(made, rifts, what))

    def _targets(self):
        """Returns (targets, breakable) or None with an error shown."""
        if not cmds.objExists(EPICENTER):
            say(self.status, "Click Place Epicenter first.", error=True)
            return None
        mode = self.target_box.currentIndex()
        ground = ground_pieces()
        selected = [o for o in (cmds.ls(selection=True, type="transform") or [])
                    if o not in (EPICENTER, GROUND_GRP)]
        targets = []
        if mode in (0, 2):
            if not ground:
                say(self.status, "There's no shattered ground yet. Click Shatter Ground first.", error=True)
                return None
            if not ground_data():
                say(self.status, "The ground wasn't finished building. Click Shatter Ground again.", error=True)
                return None
            targets += ground
        if mode in (1, 2):
            extra = [o for o in selected if o not in ground]
            if mode == 1 and not selected:
                say(self.status, "Select the objects to shake first.", error=True)
                return None
            targets += extra if mode == 2 else selected
        if not (self.p_box.isChecked() or self.s_box.isChecked()):
            say(self.status, "Turn on the P-wave or the S-wave.", error=True)
            return None
        return targets, set(ground)

    def _run(self, chunk_name):
        found = self._targets()
        if found is None:
            return None
        targets, _ = found
        selection = cmds.ls(selection=True)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        _try(cmds.refresh, suspend=True)  # don't redraw thousands of times while keying
        try:
            result = quake_apply(targets, self.params(), chunk_name=chunk_name)
        except Cancelled:
            cmds.undo()  # take back the half-made animation
            say(self.status, "Preview cancelled.", error=True)
            return None
        finally:
            _try(cmds.refresh, suspend=False)
            QtWidgets.QApplication.restoreOverrideCursor()
        if selection:
            cmds.select(selection)
        return result

    def preview(self):
        if self.previewing:
            self.revert(quiet=True)
        result = self._run("Seismic Preview")
        if result is None:
            return
        keyed, last, warnings, first_melt = result
        self.previewing = True
        cmds.playbackOptions(loop="once")  # stop at the end: sunk ground stays gone
        fast_playback()
        cmds.currentTime(cmds.playbackOptions(query=True, minTime=True))
        cmds.play(forward=True)
        msg = "Quake preview on {} objects. ".format(keyed)
        if first_melt is not None:
            msg += "Pieces start melting away at frame {:.0f}; everything is gone by frame {:.0f}. ".format(
                first_melt, last)
        msg += "Apply keeps it, Revert takes it back."
        if warnings:
            msg += " " + "; ".join(warnings)
        say(self.status, msg)

    def revert(self, quiet=False):
        if not self.previewing:
            if not quiet:
                say(self.status, "Nothing to revert. Click Preview first.", error=True)
            return
        cmds.play(state=False)
        cmds.undo()
        cmds.currentTime(cmds.playbackOptions(query=True, minTime=True))
        self.previewing = False
        if not quiet:
            say(self.status, "Quake reverted. The ground is back in one piece.")

    def apply(self):
        if self.previewing:
            cmds.play(state=False)
            self.previewing = False
            say(self.status, "Kept the quake. Ctrl+Z undoes it in one step.")
            return
        result = self._run("Seismic Quake")
        if result is None:
            return
        keyed, last, warnings, first_melt = result
        msg = "Quake keyed on {} objects (all gone by frame {:.0f}). Press play to watch. " \
              "Ctrl+Z undoes it in one step.".format(keyed, last)
        if warnings:
            msg += " " + "; ".join(warnings)
        say(self.status, msg)


# ==========================================================================
# Main window
# ==========================================================================

class RippleWindow(QtWidgets.QDialog):

    def __init__(self, parent=None):
        super().__init__(parent or maya_main_window())
        self.setWindowTitle("Ripple")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Tool)
        self.setMinimumWidth(420)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.tabs = QtWidgets.QTabWidget()
        self.ripple = RipplePanel()
        self.seismic = SeismicPanel()
        self.tabs.addTab(self.ripple, "Ripple")
        self.tabs.addTab(self.seismic, "Seismic")
        layout.addWidget(self.tabs)
        tab = load_option("tab")
        if isinstance(tab, int):
            self.tabs.setCurrentIndex(tab)

    def closeEvent(self, event):
        self.ripple.save_settings()
        self.seismic.save_settings()
        save_option("tab", self.tabs.currentIndex())
        super().closeEvent(event)


_window = None


def show():
    global _window
    if _window is not None:
        try:
            _window.close()
            _window.deleteLater()
        except RuntimeError:
            pass
    _window = RippleWindow()
    _window.show()
    return _window
