"""Builds a Ripple demo scene: a bouncing, spinning driver sphere in the center
and two rings of different shapes around it, all selected and ready for
Load Selection.

WARNING: starts a new scene. Save your work first.

Run in Maya's Script Editor (Python tab):
    import sys, importlib
    sys.path.append(r"PATH/TO/YOUR/REPO")
    import make_test_scene; importlib.reload(make_test_scene); make_test_scene.build()
"""

import math
import maya.cmds as cmds


def _key(obj, attr, pairs):
    for frame, value in pairs:
        cmds.setKeyframe(obj, attribute=attr, time=frame, value=value)


def build():
    cmds.file(new=True, force=True)
    cmds.playbackOptions(minTime=1, maxTime=120)

    driver = cmds.polySphere(name="driver_sphere", radius=0.8)[0]
    _key(driver, "translateY", [(1, 0.8), (10, 4), (20, 0.8), (28, 2.5), (36, 0.8)])
    _key(driver, "rotateY", [(1, 0), (36, 360)])
    _key(driver, "scaleY", [(1, 1), (10, 1.25), (20, 0.7), (28, 1.1), (36, 1)])

    makers = [
        lambda n: cmds.polyCube(name=n, width=1, height=1, depth=1)[0],
        lambda n: cmds.polyCone(name=n, radius=0.6, height=1.2)[0],
        lambda n: cmds.polyCylinder(name=n, radius=0.5, height=1)[0],
        lambda n: cmds.polyTorus(name=n, radius=0.5, sectionRadius=0.2)[0],
        lambda n: cmds.polyPyramid(name=n, sideLength=1)[0],
        lambda n: cmds.polyPrism(name=n, length=1, sideLength=0.8)[0],
    ]

    followers = []
    index = 0
    for ring, (radius, count) in enumerate([(4, 6), (8, 10)], start=1):
        for i in range(count):
            angle = 2 * math.pi * i / count
            obj = makers[index % len(makers)]("ring{}_shape{:02d}".format(ring, i + 1))
            cmds.move(radius * math.cos(angle), 0.6, radius * math.sin(angle), obj)
            followers.append(obj)
            index += 1

    cmds.group(followers, name="followers_grp")
    cmds.select([driver] + followers)
    print("Ripple test scene ready: driver + {} followers selected.".format(len(followers)))
