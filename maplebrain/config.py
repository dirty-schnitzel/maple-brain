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
    minimap_every_s: float = 1.0   # the scene camera holding and our tag seen: the minimap is read this often (the
                                    # camera's seed); every tick otherwise (step 2.6)
    lie_gpu: bool = True            # the Lie Detector look on the uploaded frame (liedetector.GpuLieLook, ~3.5 ms each
                                    # `every_s`) instead of the CPU thread (step 2.8)
    drops: bool = True              # drops on the ground (perception/drops.py, PLAN-loot.md; in shadow: FrameFacts.drops,
                                    # nothing reads them): a CUDA graph beside the fit, on clean maps


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
class Config:
    keys: Keys = field(default_factory=Keys)
    perception: Perception = field(default_factory=Perception)
    safety: Safety = field(default_factory=Safety)
    humanize: Humanize = field(default_factory=Humanize)
    nav: Nav = field(default_factory=Nav)
    combat: Combat = field(default_factory=Combat)
