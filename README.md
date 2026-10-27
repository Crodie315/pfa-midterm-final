# Ripple: Overlap and Earthquake Tools for Maya

Ripple is a Maya window with two tabs:

- **Ripple:** takes the animation on one "driver" object and passes it to the other selected objects, each one a little later and a little weaker, so their motion ripples through the group in one click.
- **Seismic:** builds Manhattan (or open land) and (hills, grass, soil, rock, plants) and sends an earthquake through it. Jagged rifts tear outward from the epicenter, rubble crumbles into the chasms, and the big plates of land between them tilt and sink, in the style of the film *2012*.

- **App:** Autodesk Maya (tested in Maya 2025.1)
- **Language:** Python with PySide6 (built into Maya 2025, nothing to install). Older Maya versions with PySide2 are also supported.

---

## Install and run

You need Maya. No other installs.

**1. Get the files.** Click **Code → Download ZIP** on this GitHub page and unzip it, or clone the repo. Note the folder path, for example `E:\pfa-midterm`.

The folder contains:
- `ripple.py`: the tool
- `make_test_scene.py`: builds a demo scene to try it on

**2. Open Maya's Script Editor.** Go to **Windows → General Editors → Script Editor**, then click the **Python** tab (not MEL).

> Run everything inside **Maya's Script Editor**, not in a Windows terminal or a separate Python window. The tool needs Maya's own Python.

To find your folder path: open the folder in File Explorer, click the address bar, and copy it (Ctrl+C).

**3. Paste this ONE line and press Ctrl+Enter.** Replace `E:\pfa-midterm` with your folder path, keeping the `r"..."` around it. This replaces the current scene, so save your work first.

```python
import sys, importlib; sys.path.append(r"E:\pfa-midterm"); import make_test_scene; importlib.reload(make_test_scene); make_test_scene.build(); import ripple; importlib.reload(ripple); ripple.show()
```

> Keep it on one line. If you split it into several lines with spaces at the start, Python stops with "unexpected indent".

You should see a sphere in the middle, 16 shapes in two rings around it (all selected), and the **Ripple** window.

**4. Use it.**
1. With everything still selected, click **Load Selection**. The sphere becomes the driver and the 16 shapes are listed as followers.
2. Set **Delay** to about 4 fr. At 0, every shape moves at the same moment and there's no wave.
3. Pick **Order → Distance from driver**. The inner ring will move before the outer ring.
4. Click **Preview**. The ripple is applied and the timeline plays.
5. Click **Revert** to take it back, change a slider, and Preview again.
6. Click **Apply** to keep it. One **Ctrl+Z** undoes the whole thing.
7. Try a **Preset** such as Wave Pop, or click **Save** to keep your own settings as a preset.

**Using it on your own scene:** animate one object, select it **first**, then shift-select the objects that should follow. Then follow step 4.

**5. Seismic tab: make an earthquake.**
1. Click the **Seismic** tab at the top of the Ripple window.
2. Click **Place Epicenter**. A red locator appears at the centre. Move it with the **W** key if you want the quake to start somewhere else.
3. Pick a **Map**: **Manhattan** (the island with its street grid, buildings, Central Park and the rivers) or **Square land** (open hills with trees). Click **Shatter Ground**. The map is built and cracked along jagged faults. Use the sliders below to change it. This takes a few seconds, and switches the viewport to clean shaded view.
4. Pick a **Preset** such as Strong Quake, or set Magnitude, Wave speed, Damping, and Crack threshold yourself. The seismograph and the line under it update as you drag.
5. Click **Preview**. Keying takes a few seconds, then the timeline plays once. The status line tells you the frames to watch. The main shock arrives, the crater and rifts crack open, and the small broken pieces start **melting away like an iceberg**: each one sinks into the ground while shrinking and slumping, then disappears. Aftershocks keep shaking the whole map, and **each aftershock melts another batch**, bigger pieces later, until nothing is left. The timeline ends right after the last piece is gone.
6. **Revert** takes it back, **Apply** keeps it, and one **Ctrl+Z** undoes an Apply.
7. To shake the test-scene shapes too, select them and set **Shake → Ground + selected**.

---

## Two versions

| File | What it shows | Launch line (Script Editor, Python tab) |
|---|---|---|
| `ripple.py` | **New York City:** all five boroughs (checkbox), real shorelines, tsunami from every coast | `import sys, importlib; sys.path.append(r"E:\pfa-midterm"); import ripple; importlib.reload(ripple); ripple.show()` |
| `ripple_manhattan.py` + `crodie_voice.wav` | **Manhattan + Statue of Liberty + spaceship strike + alien finale:** a spaceship flies in and fires at the epicenter; the impact flash, a ground surge and a mushroom cloud set off the quake, the collapse and the tsunami | `import sys, importlib; sys.path.append(r"E:\pfa-midterm"); import ripple_manhattan; importlib.reload(ripple_manhattan); ripple_manhattan.show()` |

Both use the same window and steps: Place Epicenter → Shatter Ground → Beauty View → Preview.

**The spaceship strike** (`ripple_manhattan.py`, checkbox *Spaceship strike starts it*, on by default): an original heavy gunship (armoured spine with a tapered nose and glass cockpit, layered hull plates, two engine pods with blue exhaust, twin nose cannons, a belly turret, antennas and surface detail) flies in over the harbour nose-first, banking as it turns (frames 1-34), turns to face the city, charges its engines and fires a slow, pulsing bolt with a glowing trail from its belly turret (frame 50). The bolt takes 36 frames to cross. At impact (frame 86) a white-hot flash swells and fades, a point light lights up the city, a ring of dust races out across the ground, and a mushroom cloud (a flared stem and a boiling cap) rises, glows orange, cools to grey smoke and drifts away. The ship watches the hit, then banks away. The quake, the building collapse, the melting and the tsunami all start at the impact frame. Revert takes the strike and the quake back in one step.

**The finale** (`ripple_manhattan.py`, part of the strike): like a scene after a film's closing credits. As soon as the last tsunami wave dies away, the picture fades to black and cuts to a new shot through the same Beauty View camera: low over the open sea beyond the city's south end, looking out at the sunset horizon. The timeline ends when the cat finishes his line. A second gunship appears on the horizon, flies straight at the audience, rolls level and stops just in front of the lens. A green cat alien stands on the ship's nose, made like a polished 3D toy: its head and body are each one sculpted smooth shape (a wide cat head with puffy cheeks, a rounded muzzle and a soft chin; a pear-shaped body with a round tummy), with a cheeky expression (sly half-lidded yellow-green eyes with slit pupils glancing to the side, one eyebrow raised and one lowered, a lopsided smirk with a little fang, and a cocky head tilt), rounded ears with pink insides, a pink nose, whiskers, tabby stripes on the forehead, a pale muzzle and tummy, a darker back, two antennae with glossy green balls, stubby legs with toes, and a smooth curled tail with a darker tip that swishes. Its materials have a soft satin sheen, like vinyl. One paw rests on its tummy; with the other it dribbles an orange basketball on the hull (the ball spins and squashes on each bounce, the arm pumps, the knees give a little), and while dribbling it says "Crodie is coming." The mouth opens and closes with each syllable, and a synthesized alien voice clip, `crodie_voice.wav`, plays on the Time Slider if it is in the same folder as the script (replace it with your own recording under the same name to change the voice). Clicking Beauty View again after Preview keeps this animated camera.

**Captions** (checkbox *Captions*, on by default): closed captions run along the bottom of the Beauty View camera for the whole strike: sound cues in [brackets] (engines growing louder, the cannon charging, the bolt crackling, the blast, the ground splitting, the Statue of Liberty toppling, sirens, crashing waves, aftershocks, silence, the ship approaching, purring and a basketball bouncing) and the alien's line, "ALIEN [in a warbling voice]: Crodie is coming." Each one shows only while that moment is on screen.

## What works now

### Ripple tab
- **Load Selection:** first selected object = driver, the rest = followers. Works with any mix of shapes.
- **Delay** and **Falloff** sliders.
- **Translate, Rotate, and Scale** channels.
- **Each object keeps its own place.** Ripple adds the driver's *change* to each object's own starting value, so nothing snaps onto the driver.
- **Order menu:** selection order, distance from driver (spreads outward like a ripple in water), or left to right along X. The follower list shows the order.
- **Live graph:** a sample wave, then the driver's real curve after Load Selection; redraws while you drag the sliders.
- **Preview / Revert:** Preview applies the ripple and plays the timeline; Revert takes the preview back; Apply keeps it.
- **Presets:** four built-in presets (Floppy Tail, Wave Pop, Domino Spin, Heavy Rope), plus **Save** for your own. Saved presets are stored in `ripple_presets.json` in your Maya user folder.
- **Remembers your settings** (delay, falloff, order, channels) between Maya sessions, using `optionVar`.
- **Copies the driver's tangent types** (spline, linear, and so on), so followers move with the same feel.
- **One Ctrl+Z** undoes the whole Apply.
- **Error messages** instead of crashes: fewer than 2 objects, no keys on the driver, no channels checked, locked channels, objects deleted after loading, nothing to revert.

### Seismic tab
- **Manhattan map:** a simplified outline of the island (tapering to the Battery, wide around 14th Street, narrow up to Inwood), turned 29° like the real street grid, with the Hudson and East River around it and concrete seawall over dark schist where the land is cut. About 250 buildings stand on the grid, sized as a share of the island's length so proportions hold at any map size: glass curtain-wall towers with floor bands, stone towers with cornices and Art Deco setbacks Downtown and in Midtown (tallest about 5% of the island's length), brick walk-ups with rooftop water tanks in the Villages and Harlem, and four landmark-style towers (Empire State, Chrysler, Flatiron and a 432 Park-style supertall, about 7%). Central Park is grass with trees. Each building rides on the piece of ground under it, so it shakes, sinks and disappears with that ground.
- **Rippling rivers and a tsunami:** the water always moves (rings of ripples from the epicenter, a slow swell, and a drifting ripple pattern in its colour), over a deep-water body so sinking ground can't be seen from the side. When the quake hits, **the sea first draws back from the shore**; then eight stretches of Manhattan's coast (the Battery, Downtown and Midtown on both sides, the Upper West Side, Harlem and Inwood) each send out **a set of three tsunami fronts**, one after another and each lower than the last (100%, 75%, 50%): 24 fronts in all. The biggest go with the main shock (exaggerated on purpose: taller than the towers), smaller sets with later aftershocks, and they cross as they spread. Each front is an arc of breaking wave with three crests, tallest in front (100%, 70%, 45%), the leading one curling into a foam lip over a lighter, see-through face. Fronts rise out of the sea and sink back under it as they die, so they never smear across the water. Preview creates them and Revert takes them away.
- **All five boroughs** (checkbox *Add the Bronx, Queens, Brooklyn and Staten Island*, on by default): every borough, Manhattan included, is drawn from its real shoreline (latitude/longitude traced from maps of New York City, with the Rockaway peninsula), so the rivers fall where they really are: the Harlem River keeps the Bronx apart from Manhattan, the East River runs between Manhattan and Brooklyn/Queens, and Brooklyn and Queens share their land border. Each piece of cracked ground is cut exactly to the coastline. Each borough has its own street grid and buildings, two to a block with different heights: brick and stone blocks in the Bronx, Brooklyn and Queens, towers at Downtown Brooklyn, Long Island City and Flushing, and small pitched-roof houses among trees on Staten Island and the Rockaways. Every building is parented to the ground under it, so it shakes, collapses, sinks and disappears like Manhattan's. Each borough sends three sets of graded tsunami waves out from three stretches of its own coast. Turn the checkbox off for Manhattan alone (faster).
- **Playback speed for the whole city:** coarser rubble, ground pieces cut to the coast (no hidden pieces under the water), lighter anti-aliasing and ambient occlusion, and Preview switches on Maya's parallel evaluation and cached playback, so after the first play the animation replays smoothly.
- **The Statue of Liberty:** on Liberty Island in its real spot, about 2.8 km southwest of the Battery, and **true to scale** against Manhattan: 93 m from the ground to the torch on a 21.6 km island, so it is tiny next to the exaggerated skyline (select `seismic_liberty` and press F to zoom to it). Fort Wood's star, the granite pedestal, the robed figure with crown, tablet and torch. During the quake it trembles; when the first wave from the Battery reaches it, the torch arm snaps down, the statue topples over away from Manhattan and sinks, and the pedestal and island go under after it.
- **Piece size:** a slider (50–150%) for how big the broken pieces of ground are. Smaller looks more like crumbling ground but means more pieces, so building and playback get slower.
- **Beauty View:** a warm low sun with shadows, a cool sky fill, ambient occlusion, anti-aliasing, haze, a dusk-sky background and a camera (`seismic_cam`) framing the island from over the Hudson. Turned on by Shatter Ground; **Plain View** goes back to Maya's normal viewport and puts your background colours back.
- **Place Epicenter:** a red locator marks where the quake starts; move it anywhere.
- **Faults like a disaster film:** 2–8 jagged faults run out from the epicenter, with side branches. Rifts are widest at the epicenter and narrow toward their tips.
- **Three kinds of ground** (all real meshes, cut with Voronoi cells):
  - **Rubble** inside the rifts and in the **collapse zone** around the epicenter: many small pieces that crumble into the chasm, so a crater caves in at the centre.
  - **Land blocks:** the land between two faults is split into an inner and an outer block, each one solid mesh, so it breaks like land, not like glass. Each block tilts on a hinge at its far edge when the crack reaches it, so the land steps down into the crater and rifts like terraces.
  - **Slabs:** land beyond the faults, in large pieces that only shake.
- **Real-looking terrain:** smooth rolling hills and valleys with a few rocky ridges. Six Lambert materials follow the land: grass in the valleys, dry grass and soil on the slopes, grey rock up high and on steep ground. Broken walls show a band of brown topsoil over darker bedrock. (Real materials, so they show in the viewport, playblasts and renders.)
- **Trees, plants and rocks:** low-poly pine trees and leafy trees (brown trunks, green crowns), bushes, grass tufts and boulders, placed inside each piece by the terrain (trees, bushes and grass low down, rocks high up and on steep ground). They ride along with the ground and go when it goes.
- **Scales with the continent:** shaking strength and how far it travels grow with the ground size, so a bigger continent cracks over a proportionally bigger area.
- **Wave arrival by real distance:** each piece starts moving at *distance ÷ wave speed*, so the quake visibly travels outward.
- **Two wave types, like real earthquakes:** the **P-wave** arrives first and pushes along the line from the epicenter; the **S-wave** is slower (1.7× later) and shakes sideways and up and down.
- **Melting like an iceberg:** when its shock reaches a piece, it sinks straight down into the ground, slowly at first, while slumping flat, then disappears for good (its trees, plants and rocks go with it). Smaller pieces melt faster.
- **Aftershocks take it piece by piece:** after the main shock, aftershocks arrive every 22–42 frames and travel across the map, on top of a constant rumble. Each one sets off the next batch of melting: broken rubble first, then small pieces, then the big land, partly by distance from the epicenter and partly by a lumpy random pattern, so it's irregular. The shaking only stops when the last piece is gone. The seismograph shows the tremors.
- **Controls:** **Pieces melt away and disappear** (off: they sink below the ground and stay), **Keep melting until everything is gone** (off: only the rifts and crater melt), and **Collapse duration** (how long the aftershocks keep coming).


## Known limits

- Apply replaces any keys the followers already had on the checked channels.
- Ripple copies keys from the driver's own channels. A driver animated by constraints or expressions, with no keys, won't ripple.
- Revert uses Maya's undo, so do Revert before doing other work in the scene.
- **Shatter Ground can't be undone with Ctrl+Z** (the pieces are built with Maya's API, which isn't recorded in undo). Click Shatter Ground again to rebuild, or delete `seismic_ground_grp` and `seismic_props_grp`. Shattering also clears the undo history.
- Shatter cracks a landscape made by the tool, not your own mesh.
- Objects you place yourself (like the test-scene shapes) don't sit on the hills automatically; they may float above or sink into the terrain.
- With many pieces, Shatter Ground, Preview, and Apply take a few seconds, and playback in the viewport may be slower than real time. Use a playblast to see the real speed.
- Preview sets Maya's playback to play once. Set it back to looping in the time slider's playback options if you want.

---

## Peer run

**Classmate:** ____

> ____ (their three sentences: what they did, what happened, what confused them or broke)

**What I'll fix next week:** ____

---

## Original pitch

### The chore it ends
In my animation class I often need many things to move one after another: a tail or hair chain swinging (overlapping action), or a group of objects popping, bouncing, or spinning in a wave. Today I key one object, copy its keys to every other object by hand, shift each one a few frames later in the Graph Editor, and adjust the values so each object keeps its own position and the motion fades. For 5–10 objects this takes about 20–40 minutes, and I redo it every time I change the main motion.

### Why it's advanced
Works on any selection, keeps each object in its own place, smart ordering, a live graph, preview before committing, presets, remembered settings, error handling, and one-step undo.

### The three weeks
- **Oct 13:** window opens with every control, Load Selection fills the lists.
- **Oct 20:** Apply works with delay, falloff, one-step undo, and error messages; the graph redraws with the sliders.
- **Oct 26:** Order menu, Preview/Revert, presets, saved settings; tested on a tail rig and a mixed-shape scene.

### Smallest version that still counts
Load Selection, Delay and Falloff, and Apply rippling Translate and Rotate in selection order as one undoable step.

### Update after the Oct 20 checkpoint
After seeing the tool, my professor pointed out that the outward motion and its direction look like seismic waves. Following that suggestion I kept Ripple as-is and added a **Seismic** tab. My first version broke the ground into even shards, which looked like glass; I reworked it so the land breaks like a landscape in a disaster film: a few jagged rifts, rubble collapsing into them, and big plates of land tilting in, on terrain with soil, rock and plants.

### Riskiest part
Keeping every object in its own place (adding the driver's change rather than copying its values, with scale fading toward 1), restoring keys reliably for Revert, and drawing the custom graph.
