# plan.yaml reference

A project is a folder `projects/<name>/` holding one `plan.yaml`. Everything the
harness produces is generated from that file, so edit the file, never the
outputs. `./bin/plan reference` prints the live list of wall types, openings,
finishes and catalogue items, which is authoritative if this page drifts.

```bash
./bin/plan new smith-house                   # start from the template
./bin/plan check projects/smith-house        # validate, list rooms and areas
./bin/plan build projects/smith-house        # DXFs, PDF + PNG sheets, manifest
./bin/plan build projects/smith-house --grid # sheets with a 1 m grid (for tracing)
./bin/plan sketchup projects/smith-house     # build, then import into SketchUp
```

## Conventions

- **Units.** Bare numbers are millimetres. Any length may instead be a string
  with a unit: `"3.6 m"`, `"360 cm"`, `"3600 mm"`.
- **Axes.** x runs east, y runs north, z up. Put the origin at the
  building's south-west corner, so coordinates are positive.
- **Directions** are compass words (`north`, `east`, `south`, `west`) or a
  compass bearing in degrees (0 north, 90 east).
- **Australian defaults** apply unless overridden: ceilings 2440, brick
  veneer 250 thick, 820 x 2040 internal doors, window heads at 2100,
  1:100 plans on A3. See `floorplan/au_defaults.py`.
- **Errors** name the exact place, e.g. `storeys[1].openings[3].at: no wall
  within 250 mm of [5200, 8500]`.

## Top level

```yaml
project:
  name: Smith House            # title block, SketchUp component names
  address: 1 Example St, Ballarat VIC
  client: J Smith              # optional
  north: 15                    # degrees clockwise from plan-up to true north (north arrow)
settings:                      # optional
  scale: 100                   # preferred plan scale; sheets step down to fit
  sheet: A3                    # A4 | A3 | A2 | A1
  cut_height: 1200             # plan section height above each floor
finishes: {}                   # optional: add or override finishes
wall_types: {}                 # optional: add or override wall build-ups
storeys: []                    # at least one, bottom up
roof: []                       # optional
```

### finishes and wall_types

```yaml
finishes:
  spotted_gum: { name: "Floor - Spotted Gum", rgb: [150, 104, 66] }
  glass_tint: { name: "Glass - Grey", rgb: [120, 130, 135], alpha: 0.4 }
wall_types:
  rammed_earth: { thickness: 300, outside: render_light, inside: render_light }
```

Every finish needs a **distinct RGB**: SketchUp's DXF importer makes one
material per colour, and the import step names materials by colour. The
spec refuses duplicates.

## storeys

```yaml
storeys:
  - name: Ground Floor
    level: 0          # FFL above datum. Optional after the first storey:
                      # derived as the storey below's level + height + this floor
    height: 2700      # FFL to ceiling (default 2440)
    floor: 300        # floor structure below FFL (default 300)
    walls: []
    openings: []
    rooms: []
    separators: []
    slab_extensions: []
    stairs: []
    items: []
```

### walls

```yaml
walls:
  - id: EXT                    # optional; needed for `wall:` openings
    type: brick_veneer
    closed: true               # a loop; the last point joins the first
    align: outside             # which face the points trace (below)
    points: [[0, 0], [12000, 0], [12000, 9000], [0, 9000]]
  - { type: stud_internal, points: [[4000, 250], [4000, 5000]] }
```

`align` says what the points describe:

| align     | walls         | the points are...                                        |
| --------- | ------------- | -------------------------------------------------------- |
| `centre`  | any (default) | the centreline                                           |
| `outside` | closed        | the outside face; the wall grows inwards (overall sizes) |
| `inside`  | closed        | the inside face; the wall grows outwards (survey sizes)  |
| `left`    | open          | the right face; the wall lies left of the drawing direction |
| `right`   | open          | the left face; the wall lies right of the drawing direction |

Corners are mitred; walls can run at any angle, and corners sharper than
about 26 degrees are refused. Internal walls can stop at a face or run into
another wall; overlaps merge. Rooms are found from the enclosed areas, so
walls must actually meet: end an internal wall *on* the inner face of the
wall it joins (e.g. at 250 for brick veneer traced `outside`). A closed
wall's outline must be a simple shape (no crossings); repeated points are
ignored.

Wall types: `brick_veneer` 250, `double_brick` 280, `rendered_panel` 200,
`clad_frame` 140, `block` 200, `stud_internal` 110, `stud_internal_70` 90.

### openings

```yaml
openings:
  - { type: entry_door, at: [6000, 0] }                  # nearest wall, centred on this point
  - { type: window, at: [2000, 0], width: 1810 }         # 1810 x 1210, head 2100
  - { type: window, wall: EXT, offset: 7500, width: 610, height: 610, sill: 1500 }
  - { type: door, at: [4000, 2500], width: 720, into: WC, hinge: right }
```

| type            | default size | notes                                              |
| --------------- | ------------ | -------------------------------------------------- |
| `door`          | 820 x 2040   | hinged; width/height are the **leaf**, hole adds 60 |
| `entry_door`    | 920 x 2040   | hinged, timber                                     |
| `cavity_slider` | 820 x 2040   | leaf size; `hinge` picks the pocket side           |
| `sliding_door`  | 2110 x 2100  | frame size, two glazed panels                      |
| `bifold_door`   | 3000 x 2100  | frame size                                         |
| `garage_door`   | 4800 x 2100  | frame size                                         |
| `window`        | 1210 x 1210  | frame size; `head` (default 2100) or `sill`        |
| `opening`       | 900 x 2100   | a cased opening, no joinery                        |

Placement: `at: [x, y]` snaps to the nearest wall whose face is within
250 mm; or `wall: <id>` + `offset:` (distance along the wall as drawn, from
its first point, to the opening's centre). An opening must fit inside one
straight run of wall, clear of the corners (the wall's thickness in from each
one), and its head must be below the ceiling. Overlapping openings are
warned about.

Door swing: `into: <room name>` (or `outside`). By default external doors open
inwards and internal doors open into the smaller room. `hinge: left|right`
is seen from the room the door opens into, facing the door.

### rooms, separators, slab_extensions

```yaml
rooms:
  - { name: Kitchen / Living, at: [6000, 6000] }          # any point inside the room
  - { name: Bed 1, at: [2000, 2000], floor: timber_floor }
  - { name: Ensuite, at: [1000, 7000], walls: tiles_wet_wall, label_at: [900, 7300] }
separators:
  - [[4055, 4000], [7750, 4000]]     # splits an open area into two rooms, draws nothing
slab_extensions:
  - [[5000, -1500], [7000, -1500], [7000, 0], [5000, 0]]   # porch, alfresco, deck
```

- A room is the enclosed area containing `at`. Two rooms in one area need a
  separator between them (open-plan boundaries); `at` must be inside the
  room, not on the separator line.
- Default floors by name: wet areas (bath, ensuite, WC, laundry) tiles; bed,
  robe, study, rumpus, media carpet; garage, alfresco, porch, patio concrete;
  deck, balcony decking; everything else timber. Wet areas get tiled walls.
- Areas are measured inside the walls, excluding stair voids.
- A `slab_extensions` polygon adds slab outside the walls; name it as a room
  (e.g. `Porch`) to label it. External doors still open inwards.

### stairs

```yaml
stairs:
  - { type: straight, start: [7250, 4300], direction: north, width: 1000 }
  - { type: l_shaped, start: [1000, 500], direction: east, width: 900, turn: left, landing_at: 6 }
  - { type: u_shaped, start: [1000, 500], direction: north, width: 1000, turn: right, gap: 100 }
```

A stair rises from its storey to the next. `start` is the centre of the
bottom riser; `direction` is the way you face walking up. Risers are
calculated from the storey-to-storey rise (at most 190 each), `going`
defaults to 250, and warnings flag NCC-style limits (riser 115-190, going
240-355, 2R+G 550-700, at most 18 risers a flight). `landing_at` is the
number of risers before the landing (default half).

The floor above gets a void wherever headroom over the stair would be under
2000, with a glass balustrade along its open edges (none where the void
meets a wall). Stairs are modelled as a folded slab, open underneath: the
space under the flight is usable.

### items: furniture, joinery and fixtures

```yaml
items:
  - { type: bed, size: queen, room: Bed 1, against: west }
  - { type: bedside_table, room: Bed 1, against: west, offset: 900 }
  - { type: kitchen_bench, room: Kitchen, against: north, offset: 400, length: 3600,
      sink: 1800, cooktop: 800, overheads: false }
  - { type: dining_table, seats: 6, at: [2200, 11000], facing: east }
```

Two ways to place an item:

- `room` + `against: <side>`: the item's back goes on the room's wall facing
  that way (`north`, `south`, `east`, `west`, or a compass bearing such as
  `60` for an angled wall; the longest wall facing within 45° of it is
  used), and it faces into the room. It is centred along that wall unless
  `offset` is given: the distance from the wall's **west end** (or its
  **south end** for a wall running north-south) to the item's nearest edge.
  `gap` holds it off the wall.
- `at: [x, y]` + `facing`: the item's centre at that point, its front facing
  that way (default north; a bearing works too).

Offsets inside an item (`sink`, `cooktop`) are measured from the same end,
to the appliance's centre. Placement warns when an item runs into a wall,
past the end of its wall, or out of its room.

| type | parameters (defaults) | size, notes |
| ---- | --------------------- | ----------- |
| `bed` | `size` queen: single, king_single, double, queen, king | mattress + 80 wide, + 100 long |
| `bedside_table` | | 450 x 400 with lamp |
| `robe` | `length` 1800 | built-in, 600 deep, sliding doors |
| `tallboy` | | 900 x 450 |
| `desk` | `length` 1400 | 700 deep plus chair (1200 total) |
| `bookshelf` | `length` 900 | 350 deep, 1800 high |
| `sofa` | `seats` 3, `chaise` left/right | 700 per seat + 400 arms, 950 deep |
| `armchair` | | 1100 x 950 |
| `coffee_table` | `length` 1200 | 600 deep |
| `tv_unit` | `length` 1800 | 450 deep with a 65" screen |
| `rug` | `length` 2400, `depth` 1700 | |
| `dining_table` | `seats` 6: 4, 6, 8 | chairs included (depth + 700) |
| `kitchen_bench` | `length` 3000, `overheads` true, `sink`, `cooktop` | 900 high, 600 deep, overheads 350 deep |
| `kitchen_island` | `length` 2400, `depth` 1000, `stools` 3, `sink`, `cooktop` | stools on the front (+430) |
| `fridge` | | 900 wide space |
| `pantry` | `length` 600 | 600 deep, full height |
| `toilet` | | 380 x 690 |
| `vanity` | `length` 900, `basins` 1 | 460 deep, wall hung, mirror |
| `shower` | `width` 900, `depth` 900 | tray, front glass screen |
| `bath` | `length` 1675, `width` 760 | |
| `laundry_trough` | | 600 x 500 |
| `washing_machine`, `dryer` | | 600 x 650 |
| `car` | | 4800 x 1850 |
| `plant` | | 700 diameter |

### roof

```yaml
roof:
  - { type: hip, over: First Floor, pitch: 22.5, eaves: 450 }
  - { type: gable, over: Ground Floor, outline: [[0, 0], [6000, 0], [6000, 9000], [0, 9000]],
      ridge: north-south }
  - { type: skillion, over: Ground Floor, outline: [[...]], down: south, pitch: 5, eaves: 150 }
  - { type: flat, over: Garage, parapet: 400 }
```

| key | meaning |
| --- | ------- |
| `type` | `hip` (default), `gable`, `skillion`, `flat` |
| `over` | the storey it sits on (default: the top storey); it starts at that storey's ceiling |
| `outline` | plan outline before eaves; default is the storey's walls |
| `pitch` | degrees (hip/gable 22.5, skillion 5) |
| `eaves` | overhang past the outline (450; flat 0) |
| `fascia` | depth of the fascia band (250; flat roofs: their thickness, 300) |
| `ridge` | gable only: `east-west`, `north-south`, or the ridge's compass bearing (default: along the longest side) |
| `down` | skillion only: the low side |
| `parapet` | flat only: parapet height |
| `finish` | default `roof_dark`; `roof_tile` is terracotta |

Any outline works. A rectilinear one (L, T, U, offset boxes, at any
rotation) is roofed as its wings, which overlap so hips run into valleys
where they meet; a skillion or flat roof covers any shape with one plane; an
outline with angled walls gets a hip end per convex piece and a warning
(give one `outline` per wing, overlapping, for a cleaner result). Roofs over
the same storey merge; a roof over a lower storey stops where it meets a
higher one (a porch skillion against a two-storey wall). A warning names any
part of a storey left open to the sky.

## What a build writes (projects/<name>/out/)

| file | contents |
| ---- | -------- |
| `model.dxf` | the 3D model: one block per storey element, doors/windows/furniture as blocks |
| `plan-<storey>.dxf` | 2D drafting per storey, layered (A-WALL, A-DOOR, A-GLAZ, A-FURN, A-ANNO-DIMS...) |
| `plan-roof.dxf` | roof plan with hips, ridges, valleys, falls |
| `plan-*.pdf`, `plan-*.png` | A3 sheets at scale with title block and area schedule |
| `sketchup.json` | what the SketchUp import needs that DXF can't carry |
| `<name>.skp` | the SketchUp model (after `bin/plan sketchup`) |
| `views/*.png` | an image of each SketchUp scene (after `bin/plan sketchup`) |

In SketchUp each storey gets tags `<Storey> - Structure`, `- Doors & Windows`,
`- Stairs`, `- Furniture` and `- Plan` (the flat 2D plan), plus `Roof`.
Scenes: `3D`, `<Storey> - 3D` (everything above hidden) and `<Storey> - Plan`.
Doors, windows and furniture are components named like a schedule
("Window 1810 x 1210 (250 wall)", "Bed - Queen"). Re-running replaces the
previous import of the same project: its components, tags and scenes, plus
any unused component or scene carrying one of those exact names (leftovers
of an undone run). Anything else drawn in the model is left alone. Keep one
project per model: the .skp lives with the project.
