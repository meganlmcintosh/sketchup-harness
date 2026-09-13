"""Australian residential defaults. Every value can be overridden in plan.yaml.

Sources are common Australian practice for project and custom homes, not a
substitute for the NCC or an engineer: use them for concept and sketch design.
"""

# Finishes become SketchUp materials. The DXF importer creates one material per
# distinct colour, so every finish needs a unique RGB; spec.py enforces this.
FINISHES: dict[str, dict] = {
    "paint_white": {"name": "Paint - Natural White", "rgb": (238, 236, 228)},
    "ceiling_white": {"name": "Ceiling - White", "rgb": (247, 247, 244)},
    "face_brick": {"name": "Face Brick - Red Blend", "rgb": (156, 84, 62)},
    "render_light": {"name": "Render - Off White", "rgb": (226, 220, 206)},
    "cladding_grey": {"name": "Cladding - Grey", "rgb": (160, 166, 168)},
    "concrete": {"name": "Concrete", "rgb": (178, 176, 170)},
    "timber_floor": {"name": "Floor - Timber", "rgb": (176, 132, 90)},
    "carpet": {"name": "Floor - Carpet", "rgb": (148, 143, 136)},
    "tiles_light": {"name": "Floor - Tiles Light", "rgb": (220, 218, 211)},
    "tiles_wet_wall": {"name": "Wall - Tiles", "rgb": (232, 232, 229)},
    "glass": {"name": "Glass", "rgb": (168, 198, 218), "alpha": 0.35},
    "frame_dark": {"name": "Frame - Dark Aluminium", "rgb": (52, 52, 55)},
    "door_white": {"name": "Door - White", "rgb": (244, 243, 239)},
    "door_timber": {"name": "Door - Timber", "rgb": (160, 112, 70)},
    "roof_dark": {"name": "Roof - Metal Dark Grey", "rgb": (58, 60, 63)},
    "roof_tile": {"name": "Roof - Terracotta Tile", "rgb": (168, 92, 62)},
    "fascia": {"name": "Fascia and Gutter", "rgb": (70, 72, 75)},
    "bench_stone": {"name": "Benchtop - Stone", "rgb": (230, 228, 222)},
    "joinery_white": {"name": "Joinery - White", "rgb": (250, 250, 248)},
    "joinery_timber": {"name": "Joinery - Timber", "rgb": (186, 150, 108)},
    "fabric_grey": {"name": "Fabric - Grey", "rgb": (122, 126, 130)},
    "fabric_sand": {"name": "Fabric - Sand", "rgb": (200, 186, 160)},
    "appliance_steel": {"name": "Appliance - Stainless", "rgb": (196, 198, 200)},
    "ceramic_white": {"name": "Sanitaryware - White", "rgb": (252, 252, 252)},
    "metal_black": {"name": "Metal - Black", "rgb": (30, 30, 32)},
    "timber_deck": {"name": "Decking - Timber", "rgb": (140, 100, 68)},
    "stair_timber": {"name": "Stair - Timber", "rgb": (150, 108, 72)},
    "balustrade": {"name": "Balustrade", "rgb": (40, 40, 42)},
    "plant_green": {"name": "Plant - Green", "rgb": (92, 128, 80)},
    "garage_door": {"name": "Garage Door - Steel", "rgb": (110, 112, 115)},
    "linen": {"name": "Bedding - Linen", "rgb": (236, 232, 222)},
    "timber_dark": {"name": "Furniture - Dark Timber", "rgb": (100, 72, 50)},
    "rug_wool": {"name": "Rug - Wool", "rgb": (182, 170, 150)},
    "pot_terracotta": {"name": "Pot - Terracotta", "rgb": (180, 100, 70)},
    "car_paint": {"name": "Car - Paint", "rgb": (74, 92, 112)},
}

# Stairs (NCC Part 3.9 style limits for houses, used for warnings).
STAIR = {
    "riser_target": 180,
    "riser_max": 190,
    "riser_min": 115,
    "going_min": 240,
    "going_max": 355,
    "two_r_plus_g": (550, 700),
    "max_risers_per_flight": 18,
    "headroom": 2000,
    "balustrade_height": 1000,
}

# Wall build-ups: overall thickness in mm, and which finish faces each side.
WALL_TYPES: dict[str, dict] = {
    # 110 brick + 40 cavity + 90 stud + 10 plasterboard
    "brick_veneer": {"thickness": 250, "outside": "face_brick", "inside": "paint_white"},
    # 110 brick + 50 cavity + 110 brick + render
    "double_brick": {"thickness": 280, "outside": "face_brick", "inside": "paint_white"},
    # 75 AAC panel + 25 cavity + 90 stud + 10 plasterboard, rendered
    "rendered_panel": {"thickness": 200, "outside": "render_light", "inside": "paint_white"},
    # cladding + battens + 90 stud + 10 plasterboard
    "clad_frame": {"thickness": 140, "outside": "cladding_grey", "inside": "paint_white"},
    # 90 stud + plasterboard both sides
    "stud_internal": {"thickness": 110, "outside": "paint_white", "inside": "paint_white"},
    # 70 stud + plasterboard both sides
    "stud_internal_70": {"thickness": 90, "outside": "paint_white", "inside": "paint_white"},
    # 190 block + render
    "block": {"thickness": 200, "outside": "render_light", "inside": "paint_white"},
}

STOREY = {
    "height": 2440,  # FFL to ceiling. Common upgrades: 2590, 2740.
    "ground_floor": 300,  # slab zone below ground FFL
    "upper_floor": 300,  # joists + flooring + ceiling below an upper FFL
}

# Openings. Hinged door "width"/"height" are the leaf size, as Australian plans
# label them (820 door); the hole in the wall adds the frame, so an 820 x 2040
# leaf needs an 880 wide opening with its head at 2100. Every other opening is
# sized by its frame, as window schedules list them (1810 x 1210).
DOOR_FRAME = 30  # added to each jamb of a hinged door's leaf width
DOOR_HEAD = 60  # added to a hinged door's leaf height: frame head plus clearance
HINGED_DOORS = ("door", "entry_door", "cavity_slider")
OPENINGS: dict[str, dict] = {
    "door": {"width": 820, "height": 2040},
    "entry_door": {"width": 920, "height": 2040},
    "cavity_slider": {"width": 820, "height": 2040},
    "sliding_door": {"width": 2110, "height": 2100},
    "bifold_door": {"width": 3000, "height": 2100},
    "garage_door": {"width": 4800, "height": 2100},
    "window": {"width": 1210, "height": 1210, "head": 2100},
    "opening": {"width": 900, "height": 2100},  # doorless cased opening
}

# Room-name keywords to default floor finishes (first match wins).
ROOM_FLOORS: list[tuple[tuple[str, ...], str]] = [
    (("bath", "ens", "wc", "toilet", "powder", "laundry", "ldry"), "tiles_light"),
    (("bed", "robe", "wir", "study", "rumpus", "theatre", "media"), "carpet"),
    (("garage", "carport", "alfresco", "porch", "patio", "verandah", "store"), "concrete"),
    (("deck", "balcony"), "timber_deck"),
]
DEFAULT_FLOOR = "timber_floor"

PLAN = {
    "scale": 100,  # 1:100 on A3 suits most houses
    "sheet": "A3",
    "cut_height": 1200,  # plan section height above FFL
}
