"""Every tunable in one place. All pixel values are in the normalized 1366x768 game frame."""
from dataclasses import dataclass, field


@dataclass
class Keys:
    attack: str = "space"     # the main attack (Power Strike: costs MP)
    basic_attack: str = "c"   # plain attack, no MP: used while out of MP with no MP potions left (the user)
    jump: str = "shift"
    pickup: str = "z"
    hp_potion: str = "delete"  # not on the test character yet
    mp_potion: str = "end"


@dataclass
class Zones:
    """Centre-to-centre horizontal distance to a mob. Measured in runs hunt5c/hunt6b (see docs in tests)."""
    contact: float = 42        # closer than this we take touch damage -> step back
    hit_max: float = 66        # contact..hit_max: face it and hold attack
    hold_max: float = 92       # hit_max..hold_max: wait for it / take a short step
    walk_release: float = 76   # release the walk key here; the slide covers the rest
    same_level: float = 35     # a mob's bottom within this of our feet is on our level
    recover_min: float = 25    # knocked less than this: the mob is on top of us (swing both sides)
    mob_width: float = 35      # the zones above were measured on snails/Shrooms (sprite boxes ~35 px wide); a wider
                               # mob reaches us that much sooner: zones count from its edge (perion7: Stumps are 62
                               # px, we swung/stopped ~13 px late and walked into them)
    climb_slope: float = 0.3   # a mob higher than our level is still walkable-to if it rises at most this much per px
    climb_max: float = 75      # of horizontal distance, up to this high (East Rocky Mountain I: mobs up the slope at
                               # the screen's left edge, 60-80 px above our feet and 500-900 px away, never seen -
                               # the band stopped 75 px over our feet). A platform right above us stays out.
    step_down: float = 80      # mobs on lower ground up to this far below our feet count (walk off the step)
    loot_reach: float = 15     # loot within this of our centre: pick up without moving
    loot_slide_short: float = 8  # after a short walk we slide about this much more
    loot_slide_long: float = 22  # after a walk at full speed (pkg_sprites1: 16 px slide + odometer seeing ~85 %)
    loot_max: float = 120      # loot farther than this isn't worth walking to (while mobs are around)
    loot_vs_mob: float = 60    # loot by sight: a drop this close is picked before a mob in sight; farther: mob first
    loot_idle_max: float = 600  # no mob in sight: go for drops anywhere on screen (the user, pkg_sight4: 'when there
                                # are no mobs around a player would prioritize getting loot')
    loot_side: float = 45     # after the burst on the drop, step this far further across it and spam again
    loot_spread: float = 55    # one mob's drops land within this of its centre (pkg_human3: -20, +15, +60)
    switch_margin: float = 20  # switch to another mob only if it's this much closer than the target
    closer_margin: float = 40  # a closer mob (not in reach) takes over only if it's this much closer ...
    closer_ratio: float = 0.25  # ... or this share of the distance, whichever is more (session 16: 86 switches
                               # in 238 engagements on a crowded floor; was switch_margin 20 px)
    chase_max: float = 200     # contested (we keep losing mobs to others): no new target farther than this.
                               # rest10m_b: engaged at >= 200 px -> 3 kills of 48; < 200 px -> 45 of 103
    drop_same: float = 18      # loot by sight: a drop seen this close to where we aimed is that drop
    loot_near_kill: float = 40  # our mob died this close: a Z burst where we stand even if no drop is seen
    pass_reach: float = 30     # walking past a seen drop this close: spam Z on the way (the user: 'they pick up
                               # loot while walking at every opportunity')
    pass_over_min: float = 15  # looting by walking through a drop: carry on this far past it (random in [min, max])
    pass_over_max: float = 35
    pile_px: float = 30        # this many drops (pile_n) within pile_px of each other: stop and pick them all up
    pile_n: int = 3
    mob_over_loot: float = 140  # loot by sight: a mob this close is fought before drops in sight; farther ones
                                # wait until the drops (<= loot_max away) are picked up
                                # (drops at our feet hide behind our own body)


@dataclass
class Timing:
    step_s: float = 0.10            # a short step
    turn_s: float = 0.035           # tap to turn around
    back_min_s: float = 0.24        # step back from a mob that's too close: a random length in [min, max]
    back_max_s: float = 0.42        # (0.1s moved ~5px: the snail followed; 0.3 s was the old fixed step)
    back_settle_min_s: float = 0.05  # after the step, a random beat before turning back to it (it was an
    back_settle_max_s: float = 0.35  # instant 35 ms turn every time: 256 identical step+turns in 31 min)
    back_skip_p: float = 0.15       # sometimes a player just keeps swinging instead of stepping back
    back_cooldown_s: float = 1.2    # after a step back, a mob still too close gets fought, not danced around
    switch_cooldown_s: float = 1.0  # after switching target, stay on it at least this long
    closer_cooldown_s: float = 0.8  # after any switch, a closer mob takes over only after this (no flip-flop; was 0.4)
    crowd_window_s: float = 45.0    # contested = crowd_losses mobs lost to others (gone before we reached them /
    crowd_losses: int = 3           # killed by someone else / gone with no EXP) within the last crowd_window_s
    blind_swing_s: float = 0.45     # hit by something unseen: swing one side this long, then the other
    knock_s: float = 0.3            # a hit's knockback lasts about this long
    recover_s: float = 2.0          # going back to where an unseen mob hit us: give up after this
    wait_in_hold_s: float = 0.6     # in the hold zone, wait this long before stepping in
    fresh_s: float = 0.25           # only react to the target's distance if seen this recently
    keep_swinging_s: float = 1.0    # mid-fight and the target vanished: keep swinging this long
    keep_close_s: float = 1.8       # ... this long if it vanished in reach: it's behind our body / other players
                                    # (acc1 38-39.6 s: its HP bar + our damage numbers visible, sprite unmatched;
                                    # we left after 1 s, it died to our hits 0.5 s later)
    proof_s: float = 1.2            # hit it and no name/HP bar appeared (they show on the 1st hit) -> not a mob
    approach_proof_s: float = 6.0   # walking toward an unproven target this long -> give up on it
    blind_max_s: float = 3.0        # proven target unseen this long -> give up
    lost_before_reach_s: float = 1.2
    engage_timeout_s: float = 15.0
    self_missing_s: float = 0.5
    blocked_s: float = 1.0          # walking with the minimap dot frozen this long -> blocked
    blocked_avoid_s: float = 15.0
    blacklist_s: float = 10.0          # short: loot gets picked up; a long ban hid live snails
    loot_timeout_s: float = 6.0         # wait + back up + sweep ~110 px + final presses
    drop_delay_s: float = 0.9           # the dying mob fades out before its drop appears
    slide_settle_s: float = 0.2         # after stopping, wait for the slide to end before picking up
    potion_cooldown_s: float = 1.0      # between two potions (it takes a moment for the bar to show the effect)
    potion_press_s: float = 0.05
    potion_verify_s: float = 1.2        # a potion must raise its bar within this (Meat: +3 % only 0.6-0.8 s after the press)
    potion_gain: float = 0.03           # ... by at least this; 2 misses in a row = used up (the slot keeps the
    potion_fails: int = 2               # icon with a "0" when the last one is gone - session 10)
    potion_recheck_min_s: float = 20.0  # used up: one probe press every 20-40 s (restocked?)
    potion_recheck_max_s: float = 40.0
    long_walk_s: float = 0.4            # walking at least this long -> full speed -> the long slide
    swing_out_s: float = 0.3            # swinging from just outside reach this long -> a short step in
    anticipate_s: float = 0.45          # start the swing this early for a mob walking toward us (it walks into it;
                                        # perion7: Power Strike lands ~0.3-0.5 s after the press, 0.3 got face-tanked)
    approach_min: float = 15.0          # px/s: slower than this a mob counts as standing still
    wait_for_s_min: float = 35.0        # px/s: only a mob charging at least this fast is waited for; slower ones we
                                        # walk in to meet (the user, pkg_sprites5: "slightly more aggressive")
    approach_cap: float = 80.0          # px/s: no mob here walks faster (more is tracking noise)
    hidden_avoid_s: float = 3.0         # after our tag was hidden and we backed out: avoid going back there
    final_taps_min: int = 3             # after the sweep, standing still: a burst of 3-5 presses (one item each),
    final_taps_max: int = 5             # like a player spamming Z after a kill
    side_taps_min: int = 1              # the burst further across the drop (was 2-3: looting was 1/3 of pkg_sprites5)
    side_taps_max: int = 2
    pickup_gap_min_s: float = 0.06      # between Z presses: random in [min, max] (short, like spamming)
    pickup_gap_max_s: float = 0.13
    pickup_press_s: float = 0.04        # how long Z is held per press
    drop_zone_s: float = 6.0
    others_kill_wait_s: float = 0.4     # its death animation, no EXP yet: wait this long for ours (EXP lags ~0.1 s)
    kill_credit_s: float = 1.5          # EXP up counts as the target's kill only if we swung at it in reach this
                                        # recently (rain1/rain2, in a party: party members' kills raise our EXP every
                                        # ~2 s -> 'kills' of targets 400-1100 px away, walked there to 'loot')
    bar_fade_s: float = 0.5             # a dying mob's HP bar is still drawn ~0.15s after the EXP rises
    loot_memory_s: float = 20.0         # drops left behind for a fight: go back within this
    patrol_s: float = 1.0
    idle_walk_min_s: float = 2.0        # nothing to attack: walk a random 2-3 s, then stand still for a spawn
    idle_walk_max_s: float = 3.0        # (the user, after pkg_potions1's lie detector test)
    idle_looks_before_patrol: int = 3
    # jumping (keys.jump, shift). Map 10001070 Rain-Forest East of Henesys: 60 px pit walls - the user, 2026-11-02
    jump_press_s: float = 0.07          # how long jump is held per press (varied)
    jump_cooldown_s: float = 0.8        # one jump is ~0.6 s in the air: no new press before this
    step_jump_min: float = 12           # a jumpable step ahead (map px from its wall): jump at a random distance in
    step_jump_max: float = 40           # [min, max] (a running jump clears 60 px from ~20-50 px out; minimap: 16 px)
    step_jump_tries: int = 3            # this many step jumps in a row off the same platform/way -> give up (blocked)
    block_jumps: int = 1                # blocked (not moving): try this many jumps before avoiding that way
    idle_jumps: bool = True             # standing still waiting for a spawn: a few jumps now and then (the user)
    idle_jump_first_min_s: float = 2.0  # first burst this long after we stop: random in [min, max]
    idle_jump_first_max_s: float = 8.0
    idle_jump_every_min_s: float = 10.0  # then a burst every [min, max]
    idle_jump_every_max_s: float = 30.0
    idle_jump_n_min: int = 1            # jumps per burst
    idle_jump_n_max: int = 3
    idle_jump_gap_min_s: float = 0.15   # between the jumps of a burst: a pause after landing, random in [min, max]
    idle_jump_gap_max_s: float = 0.8
    phase_pause_min_s: float = 0.08     # done looting -> a random beat before walking to the next target
    phase_pause_max_s: float = 0.25     # (never mid-approach: the user, 'a human doesn't stop on the way')
    drop_look_s: float = 0.7            # loot by sight: after the death animation, look this long for drops
    drop_taps_min: int = 3              # on a drop: spam Z 3-5 times (the user: 'humans usually press Z
    drop_taps_max: int = 5              # multiple times per item'; pkg_sight4: 2-4 was 'too low, many items
                                        # missed'), short random gaps; +1 per other drop lying next to it
    taps_cap: int = 8                   # at most this many presses in one burst
    loot_check_s: float = 0.35          # after the burst: the item flies up to us; then look whether it's gone
    drop_tries: int = 2                 # bursts on one drop before giving up on it
    bad_drop_s: float = 30.0            # a drop we couldn't pick up is ignored this long
    drop_timeout_s: float = 5.0         # walking to / picking up one drop at most this long
    pass_taps_min: int = 3              # walking past a drop: 3-5 Z presses (+1 per other drop next to it) spread
    pass_taps_max: int = 5              # over a random 0.3-0.65 s, without letting go of the walk key
    pass_window_min_s: float = 0.3
    pass_window_max_s: float = 0.65


@dataclass
class Perception:
    min_align: float = 0.7          # motion look rejected if camera alignment below this
    look_frames: int = 3
    look_gap_s: float = 0.07
    settle_s: float = 0.25          # after moving, let the camera stop sliding before a look
    mob_min_w: int = 32             # motion blobs narrower than this are drops/butterflies/foliage
    mob_min_area: int = 500
    self_min_score: float = 0.66    # own name tag (high-passed), full-frame search; others <= 0.59
    self_near_score: float = 0.64   # own name tag, near last position (own median 0.91)
    library_size: int = 6
    library_score: float = 0.72
    map_id: int | None = None       # Classic World map id (42 = Snail Hunting Ground III): enables sprite detection
    unconfirmed_s: float = 0.6      # sprite mode: the template tracker alone keeps a target this long at most
    sprite_score: float = 0.65      # measured on 1000 recorded frames: every hit >= 0.65 was a real snail
    die_score: float = 0.72         # death frames where the target was (its own mob type): pkg_human5m dying
                                    # Shroom 0.74-0.91; 491 live targets max 0.673
    loot: bool = False              # --loot: pick up drops at all. OFF since session 13: a pet picks up for now
                                    # (the user reworks loot later); off = no Z, no LOOT mode, straight to the next mob
    loot_by_sight: bool = False     # --loot-sight (with --map): pick up drops seen on the ground (perception/drops.py)
                                    # instead of the sweep. OFF by default: first live run pkg_sight1 was bad
    drop_zone_px: float = 45
    blacklist_px: float = 40
    screen_per_minimap: float = 15.0  # measured: screen px per minimap px (map coordinates for loot/blacklist)


@dataclass
class Safety:
    hp_stop: float = 0.45           # no HP potions left and HP below this -> stop + alarm
    hp_potion_at: float = 0.50      # HP below this and potions in the HP potion's quickslot -> drink (the user's call, 2026-11-02)
    mp_potion_at: float = 0.10
    basic_below_mp: float = 0.025   # (only without the HUD's exact MP numbers) MP under this and no MP potions -> attack with keys.basic_attack: a Power
                                    # Strike costs ~4-6 of 275 MP (1-2 px of the 105 px bar, measured session 10)
    skill_again_mp: float = 0.045   # ...until MP affords a cast again (+1 px margin against bar misreads; was
                                    # 0.15: oom2 sat on C with 13-29 MP, enough for several casts)
    skill_stall_s: float = 1.5      # cost not measured yet: skill held this long with MP under skill_stall_below
    skill_stall_below: float = 0.15 # and the exact MP not dropping -> it isn't firing (session 16: 101 ticks of
                                    # Power Strike at 17/359 MP, chat "You don't have enough MP to use this skill")
    skill_cost_max: int = 60        # an MP drop up to this while the skill is held = one cast's cost
    leash_minimap_px: float = 120   # was 60 (map 42); perion5: fair Stumps 100-500 px away were off-limits
    leash_margin: float = 6         # new targets only well inside the leash; a fight may run this far past it


@dataclass
class Humanize:
    """No fixed intervals between actions: every press length, pause and wait is randomized."""
    jitter: float = 0.25            # each wait / press length is scaled by a random factor in 1 +- jitter
    drift: float = 0.08             # a slow session tempo: every wait also scaled by a wandering 1 +- drift
    tap_gap_s: float = 0.035        # pause after a tap (varied)
    react_min_s: float = 0.005      # pause before a new key goes down: uniform in [min, max]
    react_max_s: float = 0.030
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
    seek_spawns: bool = True        # nothing in sight: walk toward where the map spawns most mobs (2026-11-02, the
                                    # user: 'gravitate towards the most dense spawning area'; before, every idle walk
                                    # went left - patrol_dir's default - into the Rain-Forest's empty left end)
    spawn_bw: float = 300           # spawn density = sum of gaussians this wide (map px) around each spawn point
    spawn_home: float = 300         # farther than this from the densest spot: walk there instead of standing
    spawn_level: float = 80         # only spawns within this height of our feet count (our floor / its pits)


@dataclass
class Config:
    keys: Keys = field(default_factory=Keys)
    zones: Zones = field(default_factory=Zones)
    timing: Timing = field(default_factory=Timing)
    perception: Perception = field(default_factory=Perception)
    safety: Safety = field(default_factory=Safety)
    humanize: Humanize = field(default_factory=Humanize)
    nav: Nav = field(default_factory=Nav)
