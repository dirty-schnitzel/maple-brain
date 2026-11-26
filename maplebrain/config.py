"""Every tunable in one place. All pixel values are in the normalized 1366x768 game frame."""
import os
from dataclasses import dataclass, field
from pathlib import Path

CORPUS = "F:/dev/maple-corpus"  # WHERE THE RECORDINGS GO: the recording corpus (PLAN-data.md). F: (an SSD) for now,
                                # E: later (the user, 2026-11-18); never C: (this repo's drive is nearly full).
                                # Change it here, or name another folder for one command with the environment
                                # variable MAPLE_CORPUS / `record --corpus DIR` / `corpus.py --corpus DIR`.


def corpus_root() -> Path:
    """The corpus folder: `record` writes into its incoming/, tools/data/corpus.py files recordings into it."""
    return Path(os.environ.get("MAPLE_CORPUS") or CORPUS)


@dataclass
class Keys:
    attack: str = "q"         # the main attack (Power Strike: costs MP)
    basic_attack: str = "c"   # plain attack, no MP: used while out of MP with no MP potions left (the user)
    jump: str = "shift"
    pickup: str = "z"
    hp_potion: str = "delete"  # not on the test character yet
    mp_potion: str = "end"
    start: str = "f7"         # serve: starts a hunt (F1-F12)
    stop: str = "f8"          # serve: stops it
    mark: str = "f9"          # serve, platform mode, no hunt running: marks / unmarks the platform we stand on
    mode: str = "f10"         # serve, no hunt running: next mode (auto -> platform -> auto; path mode later)
    note: str = "f12"         # record: the marker key - "something made me change what I do here" (PLAN-data.md edit 9).
                              # Never sent and never acted on: its presses are in keys.jsonl like every key, the
                              # corpus lists them per map, the user writes one line each in RUN/notes.txt afterwards
    old_attacks: tuple = ("space",)   # attack keys of older recordings: only the tools reading runs/ use these

    @property
    def swing_keys(self) -> tuple:
        """Every key that means a swing in a recording (tools/combat, tools/play)."""
        return (self.attack, self.basic_attack, *self.old_attacks)


@dataclass
class Perception:
    self_min_score: float = 0.66    # own name tag (high-passed), full-frame search; others <= 0.59
    self_wide_every_s: float = 0.25 # own tag lost: the full-frame search this often (the minimap meanwhile; runs/kd2: every
                                    # frame cost 120-155 ms while hidden on ladders - the loop's 2nd-worst stall)
    self_near_score: float = 0.64   # own name tag, near last position (own median 0.91)
    map_id: int | None = None       # Classic World map id (42 = Snail Hunting Ground III); None: recognised at F7
    scene_tol: int = 4              # scene camera (scene.SceneCamera, clean maps with `assets scene`): a landmark matches
                                    # within this many levels - native PNG frames are exact (+-4); the bench's JPEG 30
    scene_diff: bool = True         # scene camera found: D = frame - expected scene -> FrameFacts.patches (step 3.1;
                                    # nothing reads them yet); tolerance = scene_tol
    mover_samples: int = 4000       # scene.MoverFollow (PLAN-moving-scenery.md design 2): opaque pixels of a mover's
                                    # picture looked at per place tried; a sample matches within scene_tol levels
    mover_near: int = 3             # ... places tried each frame: its law's prediction +- this many px
    mover_peak: tuple = (30, 15, 4.0)  # ... found = the best place's matching samples >= [0] and >= the next best
                                    # + max([1], [2] x sqrt(next best)) (the prototype's peak rule, fastpipe.py)
    mover_lost_s: float = 1.0       # ... never found, or not found for this long: every place of its period is tried
                                    # (one mover a frame), again at most this often; found by the same peak rule
    cloud_near: int = 2             # perception/clouds.py (PLAN-moving-scenery.md design 3): a followed cloud is checked
                                    # within this many px of where its speed puts it (+-cloud_near_new while it has
                                    # under 2 fixes: its speed not known yet)
    cloud_near_new: int = 14
    cloud_ok: tuple = (0.5, 150)    # ... confirmed: this share of its informative sample pixels explained by the exact
                                    # blend, of at least this many
    cloud_gone: tuple = (0.15, 400, 3)   # ... the frame shows the scene where it should be (share under [0] of >= [1]
                                    # informative pixels) on [2] checks in a row: dropped
    cloud_new: tuple = (0.6, 300)   # a new cloud (the coarse finder's candidate checked at full size): share, pixels
    cloud_whitened_px: int = 1200   # the finder runs only while this many pixels are still whitened (a^ > 0.1) where no
                                    # followed cloud explains them ...
    cloud_find_gap_s: tuple = (0.2, 5.0, 1.0, 4.0)   # ... at most every [0] s for the stay's first [1] s, then every
                                    # [2] s, doubling up to [3] while it finds nothing (step 4's gate: <= once a second)
    cloud_thick: float = 0.9        # design 4 (step 5): under a cloud thicker than this (alpha) the frame is not undone -
                                    # the pixel is not valid, "covered by cloud" (the clouds' thickest pixel is ~0.88)
    minimap_every_s: float = 1.0   # the scene camera holding and our tag seen: the minimap is read this often (the
                                    # camera's seed); every tick otherwise (step 2.6)
    lie_gpu: bool = True            # the Lie Detector look on the uploaded frame (liedetector.GpuLieLook, ~3.5 ms each
                                    # `every_s`) instead of the CPU thread (step 2.8)
    drops: bool = True              # drops on the ground (perception/drops.py, PLAN-loot.md; in shadow: FrameFacts.drops,
                                    # nothing reads them): a CUDA graph beside the fit, on clean maps
    meters: bool = True             # the HP meters over the mobs WE hit (perception/meters.py, PLAN-tracker step 5a; in
                                    # shadow: FrameFacts.meters -> the mob tracker's hp): looked for around the fit's mobs
    meter_tol: tuple = (10, 10)     # ... in a band this far around a mob's expected box (x, y px; the fit's pose frame
                                    # one off moves a meter up to ~9 px: Horny Mushroom hit1)
    meter_tie: tuple = (3, 2)       # ... a meter this close to a mob's expected box names that mob (`cand`; the rule
                                    # puts 99.6 % of single-mob meters exactly there, the rest are the fit's pose noise)


@dataclass
class Safety:
    hp_stop: float = 0.45           # no HP potions left and HP below this -> stop + alarm
    hp_potion_at: float = 0.50      # HP below this and potions in the HP potion's quickslot -> drink (the user's call, 2026-11-02)
    mp_potion_at: float = 0.10


@dataclass
class Combat:
    """Brain-v2 combat. Reach comes from the client's attack boxes for this weapon type (brain/reach.py),
    never a constant here."""
    weapon: str = "poleArm"         # attacks.json weapon type: poleArm / spear (same boxes) / swordOS / axe / ... (the
                                    # user's weapon since 2026-11-08: a polearm; --weapon)
    attack_speed: int | None = None  # the weapon's attackSpeed (2 fastest .. 9); None = the usual one for the type in
                                    # the client (polearm 8, spear 7). Sets the swing length (brain/reach.py swing_s:
                                    # polearm 0.90 s); a Booster takes 2 off. --attack-speed
    skill_mp: int = 12              # MP the attack skill needs (Power Strike lv 20: 12); below it, with no MP potions,
                                    # swing with keys.basic_attack


@dataclass
class Humanize:
    """No fixed intervals between actions: every press length, pause and wait is randomized."""
    jitter: float = 0.25            # each wait / press length is scaled by a random factor in 1 +- jitter
    drift: float = 0.08             # a slow session tempo: every wait also scaled by a wandering 1 +- drift
    tap_gap_s: float = 0.035        # pause after a tap (varied)
    react_min_s: float = 0.005      # pause before a new key goes down: uniform in [min, max]
    react_max_s: float = 0.030
    release_min_s: float = 0.0      # KeyDriver: pause before a dropped key comes up: uniform [min, max]
    release_max_s: float = 0.015
    repeat_delay_s: float = 0.5     # KeyDriver: a held key auto-repeats like a keyboard: after ~0.5 s ...
    repeat_s: float = 0.033         # ... every ~33 ms (only the most recently pressed key)
    seed: int | None = None         # set for reproducible runs/tests


@dataclass
class Nav:
    """Map geometry (nav/navmap.py) and our position on it (nav/localize.py). Map px = screen px (sprites are 1:1).
    Jump numbers measured in runs/jump/20261101_234718_2 (the user jumping around Perion for 58 s, observe mode)."""
    jump_height: float = 70         # a platform at most this far above our feet: jump up through it. Seen: 60 / 64 px
                                    # platform jumps every time; ground hops peak 64-80 px (minimap: 16 px steps)
    jump_reach: float = 85          # walking jump: lands about this far ahead (single hops 80-112 px, ~0.6 s air;
                                    # a 44 px gap 186 -> 162 crossed with 112)
    walk_speed: float = 125         # px/s walking (route costs)
    jump_speed: float = 555         # Physics.img jumpSpeed (px/s up at take-off)
    gravity: float = 2000           # Physics.img gravityAcc
    jump_vx: float = 155            # a walking jump's horizontal speed: calibrated to the hops seen (level hop ~86 px in
                                    # 0.555 s; the walk speed alone would give 69 - the reach depends on the height,
                                    # NavMap.arc)
    rope_grab: float = 80           # a rope's bottom end at most this far over our feet: jump + up grabs it (seen: 41
                                    # and 43 px from the ground - ropes 1808 / -980 - grabbed 0.3-0.4 s after take-off)
    climb_speed: float = 125        # px/s up a rope (rope 1808: 160 px in 1.25 s)
    grab_body: float = 50           # jumping at a rope we catch it about this far over our feet
    rope_leap: float = 110          # jump sideways off a rope: the next rope up to this far away is caught (seen
                                    # single leaps 80-112 px: -355 -> -275, 151 -> 252, 252 -> 362, 362 -> 470)
    leap_drop: float = 40           # ...about this much lower on it (seen 16-96)
    leap_land: float = 60           # jump off a rope onto a platform: lands about this far out (seen 48-80)
    surface_tol: float = 14         # our map y within this of a platform's surface: we stand on it (dot = 8 px steps)
    rope_tol: float = 12            # our map x within this of a rope, between platforms: on the rope
    marker_dx: float = 1.2          # our minimap marker sits this far (minimap px) left/above our feet, fitted on
    marker_dy: float = 7.25         # 7053 recorded Perion frames with each run's sub-pixel canvas origin: y on the
                                    # floors (median 2.4 px off), x on the ropes (median 1.8 px off)
    canvas_score: float = 0.4       # minimap canvas template match (Perion 0.53-0.75; Rain-Forest 0.49: small, busy)
    spawn_bw: float = 300          # spawn density = sum of gaussians this wide (map px) around each spawn point
    spawn_home: float = 300         # farther than this from the densest spot: walk there instead of standing
    spawn_level: float = 80         # only spawns within this height of our feet count (our floor / its pits)


@dataclass
class Track:
    """The tracker (maplebrain/track, PLAN-tracker.md). Placement = its design 3 / docs/state_model.md section 2,
    measured in PLAN-tracker.md measurement 3 (tools/perc/track/proto_feet.py, 918 hops)."""
    stand_tol: float = 3.0          # stand: the feet within this of a flat surface (px; mobs' feet sit on it to the
                                    # pixel, us and players 1 px under it: the name tag's offset)...
    stand_tol_slope: float = 5.0    # ... of a sloped one (a foothold not level: mobs' feet 3.6-4.4 px off a slope; the
                                    # user, 2026-11-24: "allow 5 px", PLAN-tracker step 3's answers)...
    stand_step: float = 1.0         # ...and the step since the last frame within this up or down + the surface's own
                                    # rise over the sideways step, in whole px (track/graph.py; the user, 2026-11-25)
    rope_tol: float = 7.0           # climbers: the feet within this of a rope's x, and of its ends in y (today's
                                    # SelfTracker value for our exact tag; nav/selfstate.py)
    grab_s: float = 0.1             # us: a rope we were not on is a grab only with up / down down within this before
                                    # the frame (the user, 2026-11-26: "grabbed by pressing up or down"; step 4b try 3:
                                    # L1 us the same for 0-0.5 s). No speed test - us, players (L5: the same with it)
    # ---- mobs (track/mobs.py; PLAN-tracker design 4 = the prototype tools/perc/track/proto_mobs.py, its Cfg and the
    # numbers inline in it, measurement 1). Mob speed: the kind's top speed from the client files x mob_speed_x.
    shadow: bool = True             # the Perceiver runs the mob tracker beside world.py (step 3: nothing reads it)
    mob_speed_x: float = 2.0        # Classic World's mobs move at this many times the v83 rule's top speed (measured
                                    # on 8 kinds, proto_feet.py: 1.97-1.99 x at the median; PLAN-tracker measurement 4)
    knock_v: float = 125.0          # px/s: the frame-to-frame bound of any mob (a knockback), x mob_speed_x
    solid_seen: float = 0.25        # a sighting with this share of the kind's full size seen ...
    solid_on: float = 0.3           # ... and this share of its body box on screen confirms a track (a mob)
    confirm_s: float = 0.5          # ... or sightings over this long
    tentative_s: float = 0.3        # a tentative track unseen this long is dropped (no event)
    settle_tol: float = 1.5         # a look-alike reading "stands" for the first choice when this close to a surface
    under_tol: float = 3.0          # a reading this far under the floor the track stands on / jumped from: dropped
    alt_cost: float = 2.0           # px added to a pairing that takes a look-alike pose's other reading
    facing_cost: float = 8.0        # px added to a pairing that flips the mob's facing
    other_type: float = 12.0        # px added to a pairing with a sighting of another kind
    remembered_cost: float = 3.0    # px added to a pairing with a track not seen on the last frame
    gate: float = 6.0               # px a mob seen on the last frame may be off its place, + gate_v x its bound x time
    gate_v: float = 1.5
    gate_y: tuple = (10.0, 200.0)   # px + px/s x time a walker seen on the last frame may be off in y
    gate_y_jump: tuple = (14.0, 700.0)  # ... a jumper
    mem_dy: float = 12.0            # px a remembered walker's sighting may be off in y (a jumper: mem_dy_jump)
    mem_dy_jump: float = 110.0
    mem_jump_x: float = 40.0        # px more sideways a remembered jumper may be found on another node
    mem_fly_x: float = 16.0         # px more a remembered flyer's set reaches
    mem_vx_s: float = 0.4           # a remembered track's motion is taken this long at most for the pairing cost
    dy_cap: float = 40.0            # px: the vertical part of the pairing cost is half of at most this
    ballistic_s: float = 0.1        # a track seen this recently is predicted on its own vertical motion (a hop)
    vx_s: float = 0.25              # its speed: over the sightings of this long
    vx_min_s: float = 0.05          # ... taken when they span at least this
    vy_s: float = 0.05              # its vertical speed: from the last sighting if this recent
    vote_min: float = 0.05          # a sighting's vote for its kind: its seen share, at least this
    abs_share: float = 0.4          # this share of the body's core showing the scene: the mob is not there
    set_step: int = 4               # px between the places of a possible set
    knock: float = 35.0             # px: one knockback's travel (game_rules D1: ~27 + ~4), the set's first half width
    margin: float = 6.0             # px beyond the set + half a body a sighting may be
    drawn_s: float = 4.0            # unseen with something drawn over its places: kept this long at most
    offscreen_s: float = 4.0        # unseen with nothing to check (out of view, behind the UI): kept this long
    die_revert_s: float = 0.2       # a live pose on a "dying" track this soon after its first die pose: it lives
    die_revert_px: float = 8.0      # ... within this of where it died
    die_extra_s: float = 0.1        # a dying track is gone this long after its die1 animation's length
    fly_r: float = 160.0            # a flyer's set is kept within this of its last place; past it: lost
    fly_step: int = 8               # px between a flyer's places (two directions)
    fly_start: float = 12.0         # px: a flyer's first set, either way
    jump_h: int = 96                # a jumper is looked for up to this far over its platform (game_rules C4: 89-98)
    jump_dh: int = 16               # ... every this many px
    fade_o: float = 0.9             # a sighting under this opacity is fading in (a spawn)
    fade_s: float = 0.4             # a mob last seen fading in is not checked for this long (the fade-in: 0.32 s)
    # The fade's direction (PLAN-tracker "Step 3b, try 3"; the user, 2026-11-25: "dying needs falling opacity, a spawn
    # needs rising"). Measured on the 13 sound captures: a death's die pose starts at full opacity (99.1 % >= 0.97;
    # it fades out from frame ~20), a spawn fades in over 0.82 s (+0.023 a frame, p1 0.007).
    die_full_o: float = 0.99        # a die pose at this opacity or more turns a track dying, checked first (a death
                                    # starts at full: >= 0.99 on 887 of 896; a spawn's die misread reaches 0.973)
    fade_eps: float = 0.005         # under die_full_o, from two NEIGHBOURING sightings: the opacity fallen more than
                                    # this = a death, else the live mob; on a track not seen on the frame before the
                                    # die pose is held one sighting (the user, 2026-11-25)
    fade_rise: float = 0.02         # a faint birth is "faded in" once its opacity rose more than this over its first
    fade_k: int = 3                 # ... this many sightings; else it was born by how it came into sight otherwise
    # Spawn points (PLAN-tracker "Step 3b"; track/spawns.py): a mob born faded in, traced back to its point (rule (c),
    # measured: 98.0 % of 597 faded-in births on the 13 sound captures)
    spawn_fade_s: float = 0.827     # the fade-in's length on Classic World (p90; p50 0.816; v83: 0.32 s): the time
                                    # since it appeared = its first sighting's opacity x this
    spawn_slack: float = 10.0       # px: the fit's feet against the point
    spawn_hop: float = 78.0         # px: one hop's apex (measurement 3) - a jumper first seen up to this over its node
    entry_s: float = 0.5            # a track born this soon after the first frame with a camera: "there at entry"
    edge_px: tuple = (70, 70, 10, 60)   # "came into view": the feet within this of the left / right / bottom / top
    check_share: float = 0.5        # a place can be checked when this share of its core is world (shows a mob)
    cover_share: float = 0.3        # what is over the nearest place: the box over more than this share of its core
    us_box: tuple = (-34, -80, 34, 12)  # our body around our tag (centre x, top y), for `cover`
    player_box: tuple = (-24, -70, 24, 0)   # a player's body around its tag (centre x, top y)
    # ---- drops (track/drops.py; PLAN-tracker design 5 = the prototype tools/perc/track/proto_drops.py, measurement
    # 5: the 30-minute capture unless said; each constant's measurement is in the prototype's header)
    drop_band: tuple = (-5, 6)      # a resting drop's feet y - its foothold's y (measured -4 .. +5, 1 px of slack)
    drop_new_lo: int = -4           # a REST sighting above this is no birth (a pickup hop's first frame reads -7 / -6)
    drop_y_step: float = 2.0        # no bob fit yet: |y - last y| <= this + drop_y_rate x the seconds since
    drop_y_rate: float = 8.0
    bob_t: float = 2.0              # s: the bob's period (147 drops fitted: a cosine of 5 px, rounding noise 0.29 px)
    bob_tau: float = 8.0            # s: the bob's fit forgets with this time constant
    bob_min_n: int = 40             # sightings ...
    bob_min_s: float = 1.5          # ... and seconds before the fit is trusted (3/4 of a period)
    bob_amp: tuple = (1.2, 4.5)     # px: a fit whose amplitude is outside this is not a bob (yet)
    bob_tol: float = 1.25           # px a sighting may be off the fitted bob (830,167 sightings: p99.99 1.0)
    bob_far: float = 1700.0         # px: unsighted with us farther than this, its bob may have begun anew (the client
                                    # drops far things): any height of its band, the fit learnt again
    drop_confirm_s: float = 0.25    # s of sightings before a tentative drop is a drop (drop_new)
    drop_tentative_s: float = 0.10  # a tentative drop unsighted this long is forgotten (no event)
    hop_gap: float = 0.07           # s between a pickup hop's sightings (a game frame is ~33 ms)
    hop_dx: int = 8                 # px a hop sighting may be from the last one sideways ...
    hop_up: int = 24                # ... and up
    hop_gone: int = 12              # px risen: it left (the hop is seen)
    look_abs: float = 0.50          # its place shows the scenery on more than this share of the WHOLE picture, at
                                    # every resting height and frame: not there (calib: a drop there <= 43.1 %)
    look_dy: int = 7                # px around the heights it was sighted at that the look tries
    look_edge: float = 0.7          # the look: under this share of the picture on screen = "edge"
    look_ui: float = 0.3            # ... this share not world (the UI, animated scenery) = "ui"
    look_front: float = 0.3         # ... this share under front scenery of its layer = "scenery"
    look_out: tuple = (20, 8, 40)   # px: the feet this far past the sides / over the top / under the bottom = "out"
    absent_s: float = 0.15          # s the look must say "not there" without a break (a meso's edge-on frame ~0.08 s)
    drop_life_s: float = 130.0      # s: gone this old (the user, 2026-11-21: 2 min + the server's 10 s rounds)
    in_view_s: float = 1.5          # gone this soon after its last sighting = in view (else "found gone")
    pick_s: float = 0.75            # "we took it": our pickup key DOWN at some moment from this long before its last
                                    # resting frame (185 pickups whose hop was seen: p99 0.54 s, max 0.62) ...
    pick_after_s: float = 0.02      # ... to this long after it ...
    reach_x: float = 32.0           # ... with our feet within this sideways of it then (p99 21, max 25) ...
    reach_up: float = 12.0          # ... and from this above its foothold ...
    reach_down: float = 36.0        # ... to this below it (181 of 185 within -1 .. +2)
    me_hold_s: float = 2.0          # our tag missed: where we were this recently stands for our feet
    from_s: tuple = (0.6, 1.8)      # s: from_mob = a death (its first die pose) this long before the first resting
    from_mid_s: float = 1.39        # sighting (p5 1.09, p50 1.39, p95 1.54); several: the one nearest the usual delay
    from_dx: float = 110.0          # px: ... within this sideways of the drop (|landing - death| max 107) ...
    from_up: float = 100.0          # ... from this above its foothold (a mob killed in the air) ...
    from_down: float = 88.0         # ... to this below it (it lands on the foothold under 85 px above the mob)
    landed_s: tuple = ((0.1, 0.25), (0.4, 0.6))     # "landed in view": its place was on screen in both windows
    landed_px: tuple = (30, 60, 10)                 # ... this far inside the sides / under the top / over the bottom
    pet_box: tuple = (-20, -40, 20, 0)  # a pet's body around its tag (35-45 px high: proto_players' col_body)
    # ---- the HP meter (track/mobs.py `_meters`; PLAN-tracker step 5a): a meter teaches its mob's hp only when it names
    # ONE sighting (perception's `cand`) and no other track stands over that mob - design 1: a meter over two
    # overlapping mobs teaches nothing. Overlapping = the body boxes' x ranges meet (a remembered track: anywhere it can
    # be) with the feet within meter_same_dy px up or down.
    meter_same_dy: float = 40.0
    # ---- other players (track/players.py; PLAN-tracker design 6 = the prototype tools/perc/track/proto_players.py,
    # measurement 7: its constants)
    player_cover_s: float = 2.0     # a player whose tag is not found is kept this long while its place is in view
                                    # (the user, 2026-11-24, question 5: was 1 s)
    tag_gate: float = 16.0          # px a tag seen on the last frame may have moved (+ tag_vx / tag_vy x the time unseen)
    tag_vx: float = 260.0
    tag_vy: float = 800.0
    tag_w_tol: int = 1              # px: "the same width" = the same name (78 % of whole sightings exact, 1 % 1-2 px)
    tag_join: int = 6               # px: two boxes on one row this close are pieces of one tag (a ladder's rail)
    tag_confirm: int = 3            # whole sightings before a track's width counts
    tag_min_seen: int = 6           # sightings before a track gets a class
    tag_edge: int = 6               # px: a box this close to the screen's border / a UI rectangle is cut there
    body_tall: int = 55             # px: what stands on a tag reaches this far over it = a character (a pet ~40) -
                                    # D's blob test (a pattern on a character's clothes); the class uses pet_line
    pet_q: int = 75                 # a track is a pet when this percentile of its body heights over the stay (whole,
    pet_line: int = 50              # alone sightings; else every reading) is under pet_line px. Measured (step 4b try
                                    # 2, L5's tracks of their own name): pets 35-41 px, players 57-120 (p50 68); a
                                    # player's attack stance reads 10-22 px between the legs on up to ~20 % of its
                                    # sightings - p75 keeps it 64-68; the user: slack for larger pets, always shorter
    tag_medal_h: int = 21           # a tag box this tall grew UP (a medal): feet = its bottom - 18; any other height
                                    # grew down (descenders, 19-22 px) or not at all: feet = its top - 1 (the user,
                                    # 2026-11-26, on try 2's measurement)
    body_reach: int = 120           # px over the tag read for the body, in 2 body_half + 1 columns over its centre ...
    body_half: int = 8
    body_gap: int = 8               # ... upward until a break of more than this many rows
    # Clean sightings teach, crowded ones only follow (PLAN-tracker design 1; the user, 2026-11-26): a tag is ALONE
    # when no other tag (or our own) is within alone_gap px of it on its rows and no other tag's owner's body could
    # stand in its column: another tag's centre within alone_dx px sideways and from alone_dy[0] px over it to
    # alone_dy[1] px under it (the body column reads body_reach px up; a body is ~70 px tall). Only alone sightings
    # teach a track its name's width, its body's height and its class.
    alone_gap: int = 12
    alone_dx: int = 32              # body_half (8) + a player's half width (player_box: 24)
    alone_dy: tuple = (-120, 70)
    split_rest: int = 20            # px: a box split with one track: the rest is another tag's piece from this wide
                                    # on; narrower, the box is a wider tag over the track (not split)
    body_settled: int = 30          # a pet / player track with this many alone body readings is not asked again
                                    # (the ms: the body question costs ~0.4 ms a frame live - step 4b try 2)
    ours_list_s: float = 2.0        # our tag taken from the tag list only this long after our own tag was last found
    mob_tag_n: int = 20             # a mob kind's own tag ("Lv. N name") box is known after this many sightings
    log_rows: tuple = (602, 14, 6, 1363, 1369, 1000)   # the message log's tag boxes: first row's top y, pitch, rows,
                                    # right edge range, the x a line's centre is right of (fixed on the screen)


@dataclass
class Config:
    keys: Keys = field(default_factory=Keys)
    perception: Perception = field(default_factory=Perception)
    safety: Safety = field(default_factory=Safety)
    humanize: Humanize = field(default_factory=Humanize)
    nav: Nav = field(default_factory=Nav)
    track: Track = field(default_factory=Track)
    combat: Combat = field(default_factory=Combat)
