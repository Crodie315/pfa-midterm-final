# Ripple: Overlap and Earthquake Tools for Maya

**Demo video (2:49):** [Watch on YouTube](https://youtu.be/KxQjwTTZ4yI)

Ripple is a tool window inside **Autodesk Maya** (tested in **Maya 2025.1 on Windows**; Python with PySide6, built into Maya, nothing to install). It has two tabs:

- **Ripple (the chore from my pitch):** takes the animation on one "driver" object and passes it to the other selected objects, each one a little later and a little weaker, so their motion ripples through the group in one click. Without the tool this is 20–40 minutes of copying keys and shifting them in the Graph Editor.
- **Seismic:** builds Manhattan, cracks it into pieces and sends an earthquake through it: rifts, collapsing buildings, the Statue of Liberty toppling, tsunami waves, and (in the Manhattan version) a spaceship strike that sets it all off, ending on an alien cat saying "Crodie is coming."

---

## Install and run (from a fresh download)

You only need Maya.

**1. Get the files.** On this GitHub page click **Code → Download ZIP**, then unzip it anywhere (or `git clone` the repo). Keep all the files together in one folder.

**2. Drag one file into Maya's viewport:**

| Drag this file | What happens |
|---|---|
| `open_ripple_demo.mel` | Starts a **new scene** with a demo setup (a bouncing sphere and 16 shapes around it, all selected) and opens the Ripple window. **Start here.** Save your work first. |
| `open_ripple.mel` | Opens the Ripple window in your current scene. |

Drag the file from File Explorer and drop it onto Maya's main viewport (the big 3D view). The window opens; nothing else to type.

**If dragging doesn't work** (some Maya setups block it): open **Windows → General Editors → Script Editor**, click the **Python** tab, paste this one line, change the folder in quotes to **your** unzipped folder (for a ZIP it ends in `-main`), and press **Ctrl+Enter**:

```python
import sys, importlib; sys.path.append(r"C:\Users\YOU\Downloads\pfa-midterm-main"); import ripple_manhattan; importlib.reload(ripple_manhattan); ripple_manhattan.show()
```

To copy your folder path: open the folder in File Explorer, click the address bar, Ctrl+C. Keep the whole command on one line (spaces at the start give "unexpected indent").

---

## Use it: the Ripple tab (the chore)

1. After `open_ripple_demo.mel`, everything is already selected. Click **Load Selection**: the sphere becomes the driver, the 16 shapes the followers.
2. Set **Delay** to about **4 fr** (at 0 they all move together).
3. Pick **Order → Distance from driver**, so the inner ring moves before the outer ring.
4. Click **Preview**: the ripple is applied and the timeline plays. **Revert** takes it back; change a slider and Preview again.
5. Click **Apply** to keep it. One **Ctrl+Z** undoes the whole thing.
6. Try a **Preset** (Floppy Tail, Wave Pop, Domino Spin, Heavy Rope) or **Save** your own.

**On your own scene:** animate one object, select it **first**, shift-select the objects that should follow, then do the steps above.

## Use it: the Seismic tab

1. Click the **Seismic** tab, then **Place Epicenter** (a red locator at the centre; move it with **W** if you like).
2. Click **Shatter Ground** and wait until the cursor is normal: Manhattan is built and cracked.
3. Click **Beauty View** (lighting, haze and the camera `seismic_cam`), then **Preview**. Watch through the Beauty View camera: the ship flies in and fires, the city shakes, collapses and sinks, the tsunami spreads, then the screen fades to black and the cat's ship flies up to the camera.
4. **Revert** takes it all back; **Apply** keeps it.

## The files

| File | What it is |
|---|---|
| `ripple_manhattan.py` | **The main tool** (opened by the `.mel` launchers): both tabs; Manhattan with the Statue of Liberty, the spaceship strike, the cat finale, captions and voice. Fast enough to demo. |
| `ripple.py` | The same window with **all five boroughs of New York City** (Bronx, Queens, Brooklyn, Staten Island, from real shorelines). Much heavier: building it can take several minutes. Open it with the line above, using `ripple` instead of `ripple_manhattan`. |
| `make_test_scene.py` | Builds the Ripple demo scene. |
| `crodie_voice.wav` | The alien's voice clip (loaded automatically on the timeline). |
| `open_ripple.mel`, `open_ripple_demo.mel` | Drag-and-drop launchers. |

---

## What it does in detail

**The spaceship strike** (`ripple_manhattan.py`, checkbox *Spaceship strike starts it*, on by default): an original heavy gunship (armoured spine with a tapered nose and glass cockpit, layered hull plates, two engine pods with blue exhaust, twin nose cannons, a belly turret, antennas and surface detail) flies in over the harbour nose-first, banking as it turns (frames 1-34), turns to face the city, charges its engines and fires a slow, pulsing bolt with a glowing trail from its belly turret (frame 50). The bolt takes 36 frames to cross. At impact (frame 86) a white-hot flash swells and fades, a point light lights up the city, a ring of dust races out across the ground, and a mushroom cloud (a flared stem and a boiling cap) rises, glows orange, cools to grey smoke and drifts away. The ship watches the hit, then banks away. The quake, the building collapse, the melting and the tsunami all start at the impact frame. Revert takes the strike and the quake back in one step.

**The finale** (`ripple_manhattan.py`, part of the strike): like a scene after a film's closing credits. As soon as the last tsunami wave dies away, the picture fades to black and cuts to a new shot through the same Beauty View camera: low over the open sea beyond the city's south end, looking out at the sunset horizon. The timeline ends when the cat finishes his line. A second gunship appears on the horizon, flies straight at the audience, rolls level and stops just in front of the lens. A green cat alien stands on the ship's nose, made like a polished 3D toy: its head and body are each one sculpted smooth shape (a wide cat head with puffy cheeks, a rounded muzzle and a soft chin; a pear-shaped body with a round tummy), with a cheeky expression (sly half-lidded yellow-green eyes with slit pupils glancing to the side, one eyebrow raised and one lowered, a lopsided smirk with a little fang, and a cocky head tilt), rounded ears with pink insides, a pink nose, whiskers, tabby stripes on the forehead, a pale muzzle and tummy, a darker back, two antennae with glossy green balls, stubby legs with toes, and a smooth curled tail with a darker tip that swishes. Its materials have a soft satin sheen, like vinyl. One paw rests on its tummy; with the other it dribbles an orange basketball on the hull (the ball spins and squashes on each bounce, the arm pumps, the knees give a little), and while dribbling it says "Crodie is coming." The mouth opens and closes with each syllable, and a synthesized alien voice clip, `crodie_voice.wav`, plays on the Time Slider if it is in the same folder as the script (replace it with your own recording under the same name to change the voice). Clicking Beauty View again after Preview keeps this animated camera.

**Captions** (checkbox *Captions*, on by default): closed captions run along the bottom of the Beauty View camera for the whole strike: sound cues in [brackets] (engines growing louder, the cannon charging, the bolt crackling, the blast, the ground splitting, the Statue of Liberty toppling, sirens, crashing waves, aftershocks, silence, the ship approaching, purring and a basketball bouncing) and the alien's line, "ALIEN [in a warbling voice]: Crodie is coming." Each one shows only while that moment is on screen.

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

---

## How I tested it

- Downloaded the repo as a ZIP into a new folder and followed only this README in **Maya 2025.1 on Windows**.
- **Ripple tab:** demo scene, Load Selection, Delay 4, Distance order, Preview, Revert, Apply, Ctrl+Z; presets; my own scene with a tail chain.
- **Seismic tab:** Place Epicenter, Shatter Ground, Beauty View, Preview through the whole timeline (strike, collapse, tsunami, fade, cat finale); Revert and Preview again.
- **Full city** (`ripple.py`): built and played once with lighter settings (Land detail 400, Collapse zone 20%).
- Recorded the result (video link at the top).

## What doesn't work yet

- **Ripple** copies keys from the driver's own channels. A driver moved only by constraints or expressions (no keys) won't ripple. Apply replaces keys the followers already had on the checked channels.
- **Revert** uses Maya's undo, so do Revert before other work in the scene. **Shatter Ground can't be undone** with Ctrl+Z (the pieces are built with Maya's API); click it again to rebuild.
- **Shatter** cracks the landscape the tool builds, not your own mesh.
- **Speed:** the full five-borough city (`ripple.py`) takes several minutes to build and plays slower than real time in the viewport. The Manhattan version is much faster. Use a playblast to see the real speed.
- **Captions** are solid 3D text when Maya can build it; otherwise they fall back to viewport text labels (visible in the viewport and playblasts, but not in a render).
- The **alien voice** is a synthesized alien-language clip, not real speech; the English line is in the captions. You can replace `crodie_voice.wav` with your own recording.
- The cat is built from simple shapes, so there's no real fur.
- Only tested in Maya 2025.1 on Windows.

## What I'd build next

1. **Ripple on any animation:** read constrained or expression-driven motion by sampling the driver frame by frame, so it works on rigs, not only keyed objects.
2. **Shatter your own mesh:** crack any ground the artist models, not only the generated map.
3. **Speed for the full city:** bake the quake to an Alembic cache so it plays in real time and renders fast.
4. **A "Make movie" button** that playblasts the Beauty View camera with sound in one click.
5. **Real fur** for the cat with XGen for final renders.

---

## Peer run

**Classmate:** I asked two classmates to test the tool from a fresh download. One was ill and the other couldn't reply before the deadline, so no classmate feedback is included here.

**My own fresh-download run (Nov 2, Maya 2025.1, Windows):** I downloaded the repo as a ZIP into a new folder (`E:\xz\pfa-midterm-final-main`), restarted Maya, opened a new scene, and followed only this README. Before my fix, the README told users to paste a long Python line and edit a folder path by hand. That path pointed to my own folder (`E:\pfa-midterm`), so it broke for anyone who downloaded the repo somewhere else, and a pasted line with spaces in front of it gave an "unexpected indent" error.

**What I fixed:** I added two drag-and-drop launchers, `open_ripple_demo.mel` and `open_ripple.mel`. Each one finds the folder it was dropped from, adds it to Maya's Python path, and opens the tool, so nobody has to type or edit a path. I rewrote the install steps around them and kept the Python line only as a fallback. I then re-ran the fresh-download test: dragging `open_ripple_demo.mel` into Maya built the demo scene and opened the Ripple window, and Load Selection → Delay 4 → Preview rippled the 16 shapes after the sphere.

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
