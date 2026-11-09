"""Decisions. Brain.step(observation) -> actions. No I/O, no wall clock (time comes in as obs.t), so every
behaviour can be tested with hand-made observations.

Priorities, highest first:
  1. safety: HP too low -> Stop
  2. can't see ourselves -> release; back out the way we came (we probably walked behind a foreground object)
  3. blocked (walking but the minimap dot is frozen) -> avoid that direction for a while
  4. a kill (EXP went up) is counted; if our target is the one that died -> next mob in reach, else SEEK
  5. mobs in reach outrank a target that isn't (always when we're taking damage)
  6. an unproven target must prove itself (HP bar / EXP): not while hitting (proof_s), not while approaching
     (approach_proof_s) -> blacklist + forget
  7. fight the target by distance zone, acting only on a fresh sighting
  LOOT (after a kill with nothing else in reach, or when 'the target' turned out to be loot):
  wait for the drop to appear (death animation) -> walk toward it measuring how far we actually moved
  (camera shift + our screen movement; the minimap is too coarse) -> stop, let the slide end -> tap pickup.
"""
from dataclasses import dataclass, field

from ..config import Config
from ..humanize import Humanizer
from ..geometry import bottom, cx
from ..perception.perceiver import Observation
from .actions import Forget, Hold, Learn, Look, Release, Stop, Tap, Track, Untrack


@dataclass
class Target:
    rel_dx: float
    seen_at: float
    engaged_at: float
    points_at_engage: int | None         # HUD EXP points when engaged (None: unreadable then)
    hit_since: float | None = None
    hold_since: float | None = None
    hold_wait: float = 0.0               # this time's wait in the hold zone (varied)
    proof_s: float = 0.0                 # this target's proof time (varied)
    bar_seen: bool = False
    kill_at: float | None = None         # EXP went up while fighting it (its HP bar fades a moment later)
    swung_at: float | None = None        # last tick we were swinging with it in reach (EXP can only be its kill then)
    proven: bool = False
    learned: bool = False
    below: bool = False                  # last seen on lower ground (we're up on a step): walk down to it first
    swing_out_since: float | None = None  # swinging from just outside reach (the slide should bring us in)
    ground: list = field(default_factory=list)   # [(t, its position along the ground)] - fresh sightings, ~0.5 s
    swing_out_wait: float = 0.3
    dying_at: float | None = None        # its death animation was seen (killed - by us if EXP follows)
    sprite_at: float | None = None       # last tick its own sprite was found where it should be
    wide: float = 0.0                    # half its width beyond a snail's: the zones count from its edge


@dataclass
class Brain:
    cfg: Config
    hz: Humanizer | None = None              # randomizes every wait (no fixed intervals)
    navmap: object = None                    # nav.navmap.NavMap of the map (--map): steps to jump up
    mode: str = "SEEK"
    target: Target | None = None
    held: str | None = None
    facing: str | None = None
    start_dot: tuple | None = None
    dot_hist: list = field(default_factory=list)   # first minimap readings, until they're steady
    me_seen_at: float | None = None
    self_lost_logged: bool = False
    last_walk_dir: str | None = None
    backouts: int = 0
    last_backout: float = -1e9
    walk_ref: tuple | None = None
    blocked: dict = field(default_factory=dict)        # direction -> until
    drop_zones: list = field(default_factory=list)     # (until, map_x) where a mob died: its loot lies there
    not_mobs: list = field(default_factory=list)       # (until, map_x) things hit with no name/HP bar: loot, scenery
    idle_looks: int = 0
    patrol_dir: str = "left"
    prev_hp_raw: float | None = None
    loot_rel: float = 0.0                 # where the drop is, relative to where we were when it fell
    loot_since: float = 0.0
    loot_stop_at: float | None = None     # when we stopped next to it (pick up once the slide ends)
    loot_wait: float = 0.0                # death animation to wait out before the drop exists
    loot_taps: int = 0
    final_taps: int = 4
    loot_dir: int | None = None           # +1 sweep right, -1 left
    loot_phase: str = "wait"            # walk / settle / burst
    loot_wps: list = field(default_factory=list)   # stops (relative to where looting began)
    loot_wp: int = 0
    loot_origin: float | None = None
    loot_next_tap: float = 0.0
    loot_single: bool = False             # one item we hit, not a dead mob's spread of drops
    loot_walk_since: float | None = None  # when the current loot walk began (long walk -> long slide)
    loot_near: bool = False               # loot by sight: our mob died right next to us (drops hide behind us)
    loot_tw: float = 0.0                  # loot by sight: the drop we go for, as an odometer position
    loot_tw_since: float = 0.0
    loot_tries: int = 0
    loot_got: int = 0                     # drops picked up (gone after a burst) this LOOT
    loot_check_at: float = 0.0
    loot_look: float = 0.0
    loot_pass_to: float = 0.0
    bad_drops: list = field(default_factory=list)      # (until, odometer x) drops we couldn't pick up
    passed: list = field(default_factory=list)         # (until, odometer x) drops we spammed Z at walking past:
                                                       # still there later -> stop on it next time
    pass_taps: int = 0                                 # Z presses left in the walking-past burst
    pass_next: float = 0.0
    pass_gap: float = 0.1
    drop_bursts: list = field(default_factory=list)    # (until, odometer x) every burst on a drop: standing on it
                                                       # our body hides it, so 'gone' may only mean 'covered'
    last_back_off: float = -1e9
    back_settle_until: float = -1e9   # after a step back: a beat before turning to the mob again
    back_cooldown: float = 0.0
    last_switch: float = -1e9
    damaged: bool = False
    swing_until: float = -1e9               # blind swing at something unseen that hits us
    swing_dir: str = "right"
    swing_count: int = 0
    last_walk_t: float = -1e9
    odo: float = 0.0
    odo_hist: list = field(default_factory=list)
    hit_t: float = -1e9
    hit_odo: float = 0.0
    recover_until: float = -1e9
    knock_until: float = -1e9
    switch_cooldown: float = 0.0
    closer_cooldown: float = 0.0
    loot_settle: float = 0.0
    pending_loot: list = field(default_factory=list)  # (until, map_x, drop_ready_at): drops left for a fight
    walked_for_loot: float = 0.0
    last_px: float | None = None
    moved: float = 0.0                    # how far we actually moved since the last tick (screen px)
    patrol_check: tuple | None = None     # (direction, dot_x) of the last patrol step, to detect walls
    idle_walk_until: float | None = None  # nothing to attack: walk until then, then stand still and wait for a spawn
    pause_until: float = -1e9             # a human pause at a phase boundary (after looting): no new walk-in before
    jump_ready: float = -1e9              # no jump press before this (still in the air)
    step_key: tuple | None = None         # (platform, direction) of the step we're walking at
    step_trigger: float | None = None     # jump when the step is this close (random per approach)
    step_tries: int = 0                   # step jumps at it in a row (failed ones land us back here)
    block_jumps_done: int = 0             # jumps tried against the current block (reset once we move)
    idle_jump_at: float | None = None     # standing for a spawn: next idle jump then
    idle_jumps_left: int = 0              # ...of this burst
    idle_hop_dir: str = "left"            # idle jumps move one way per burst (the user: jump moving a direction)
    idle_hop_until: float = -1e9          # hold that direction until we've landed
    last_damage_look: float = -1e9
    damaged_at: float = -1e9
    stats: dict = field(default_factory=lambda: {
        "engagements": 0, "kills": 0, "level_ups": 0, "not_a_mob": 0, "chain": 0, "reach_switches": 0, "closer_switches": 0,
        "lost": 0, "gave_up": 0, "timeouts": 0, "back_offs": 0, "short_steps": 0, "blocked": 0,
        "backouts": 0, "self_lost": 0, "looks": 0, "patrols": 0, "loot_pickups": 0, "loot_gave_up": 0, "blind_swings": 0,
        "potions": 0, "waits": 0, "others_kills": 0, "foreign_exp": 0, "walk_pickups": 0, "basic_switches": 0, "potions_out": 0,
        "jumps": 0, "step_jumps": 0, "block_jumps": 0, "idle_jumps": 0, "spawn_walks": 0})
    skill_hold: list | None = None     # [since, MP then]: holding the skill key at low MP, MP not dropping since
    skill_min_mp: int = 0              # learned: the skill didn't fire below this MP (0 = not learned yet)
    skill_cost: int = 0                # measured MP per cast (0 = not measured yet)
    cast_costs: list = field(default_factory=list)      # the last few MP drops while the skill was held
    prev_mp: int | None = None
    attack_key: str | None = None      # the key swings use now: keys.attack, or keys.basic_attack while out of MP
    potion_ready: dict = field(default_factory=dict)   # "HP"/"MP" -> earliest time for the next potion
    potion_check: dict = field(default_factory=dict)   # "HP"/"MP" -> [tap_t, level at the tap, peak since]
    potion_fails: dict = field(default_factory=dict)   # "HP"/"MP" -> presses in a row that did nothing
    potions_out: dict = field(default_factory=dict)    # "HP"/"MP" -> next probe time: used up (icon shows "0")
    lost_to_others: list = field(default_factory=list)  # times we lost a target to other players (crowding)
    contested: bool = False                             # many of those lately: no far chases (zones.chase_max)
    stop_probed: bool = False                           # HP under hp_stop while 'used up': one last probe press done
    events: list = field(default_factory=list)          # human-readable log lines from the last step

    def __post_init__(self):
        if self.hz is None:
            self.hz = Humanizer(self.cfg.humanize.jitter, self.cfg.humanize.seed, self.cfg.humanize.drift)
        if self.attack_key is None:
            self.attack_key = self.cfg.keys.attack

    # ------------------------------------------------------------------ helpers
    def _say(self, obs, msg):
        self.events.append(f"{obs.t:7.2f}s {msg}")

    def _hold(self, key):
        self.held = key
        if key in ("left", "right"):
            self.facing = key
        return [Hold(key)]

    def _release(self):
        self.held = None
        return [Release()]

    def _turn(self, direction):
        if self.facing == direction:
            return []
        self.facing, self.held = direction, None
        return [Release(), Tap(direction, self.cfg.timing.turn_s)]

    def _allowed(self, obs, direction, slack=0.0):
        """May we walk this way? Not into an avoided direction, nor further off the leash. `slack` widens the leash
        (a fight already going: +) or narrows it (choosing a new target: -) so the two never disagree at its edge
        (pkg_sprites6 66-95 s: dot 63 'go', dot 64 'too far' - 26 engage/drop cycles)."""
        if self.blocked.get(direction, -1) > obs.t:
            return False
        dot, start = obs.dot, self.start_dot
        leash = self.cfg.safety.leash_minimap_px + slack
        if dot is None or start is None or abs(dot[0] - start[0]) <= leash:
            return True
        return (direction == "right") == (dot[0] < start[0])          # off the leash: only back toward start

    def _map_x(self, obs, rel):
        """A screen offset from us -> map coordinate (stays put while we move). None if the minimap dot is unknown."""
        return None if obs.dot is None else obs.dot[0] * self.cfg.perception.screen_per_minimap + rel

    def _in_zone(self, obs, zones, rel, radius):
        m = self._map_x(obs, rel)
        return m is not None and any(abs(m - z[1]) < radius for z in zones)

    def _fair(self, obs, b, px):
        """May `b` be fought? Not where a mob just died (its loot) or where something was proven not a mob -
        unless it shows an HP bar."""
        if b in obs.bar_mobs or self._sprite_mode():
            return True             # sprite mode: a shape match is a live mob, never a drop (perion5 49/73 s: Stumps
        rel = cx(b) - px            # walking near where another died were 'drop zone', ignored ~0.4-0.8 s)
        p = self.cfg.perception
        return not (self._in_zone(obs, self.drop_zones, rel, p.drop_zone_px) or
                    self._in_zone(obs, self.not_mobs, rel, p.blacklist_px))

    def _pickable(self, obs, b, px):
        """May `b` be chosen as a new target? Fair, and reachable: next to us, fighting us, or the way to it is
        neither blocked nor past the leash."""
        cfg = self.cfg
        if not self._fair(obs, b, px):
            return False                                   # loot where a mob died / something proven not a mob
        if abs(cx(b) - px) <= cfg.zones.hold_max:         # next to us: no walking needed, avoided or not
            return True
        if b in obs.bar_mobs and abs(cx(b) - px) <= cfg.zones.hold_max * 2:
            return True                                    # fighting us: it comes our way, we wait for it
        if self.contested and abs(cx(b) - px) > cfg.zones.chase_max and b not in obs.bar_mobs:
            return False                                   # crowded: a far mob is someone else's kill by the time we're there
        return self._allowed(obs, "left" if cx(b) < px else "right", slack=-cfg.safety.leash_margin)

    def _fighting_us(self, obs, tg) -> bool:
        """The target fights back: it shows an HP bar, or (sprite mode, no bars) we have hit it."""
        return obs.target_has_bar or (self._sprite_mode() and tg.hit_since is not None)

    def _engage(self, obs, box, why):
        px = obs.me[0]
        self.mode = "ENGAGE"
        self.target = Target(rel_dx=cx(box) - px, seen_at=obs.t, engaged_at=obs.t, points_at_engage=obs.exp_points,
                             proven=box in obs.bar_mobs or self._sprite_mode(),   # sprite matched = a mob
                             proof_s=self.hz.vary(self.cfg.timing.proof_s),
                             wide=max(0.0, (box[2] - self.cfg.zones.mob_width) / 2))
        self.stats["engagements"] += 1
        self._say(obs, f"{why}: target at dx {self.target.rel_dx:+.0f}")
        return [Track(box)]

    def _go_loot(self, obs, rel, why, dying=True):
        """Go pick up the drop `rel` px from us (LOOT mode), unless it's too far to bother.
        `dying`: a mob just died there, so its drop appears only after the death animation."""
        acts = self._disengage(obs, why)
        if not self.cfg.perception.loot:                # looting off (a pet picks up): on to the next mob
            if dying:
                self._phase_pause(obs)
            return acts
        if self._sight() and dying:                     # drops are looked for, wherever they fell
            acts += self._start_loot(obs, rel, self.hz.vary(self.cfg.timing.drop_delay_s))
            self.loot_near = abs(rel) <= self.cfg.zones.loot_near_kill
            return acts
        if abs(rel) > self.cfg.zones.loot_max:
            return acts
        return acts + self._start_loot(obs, rel, self.hz.vary(self.cfg.timing.drop_delay_s) if dying else 0.0,
                                       single=not dying)

    def _start_loot(self, obs, rel, wait, single=False):
        """`single`: one item we hit (no spread of drops around it): a missed one lies behind us, not further on."""
        self._say(obs, f"loot at dx {rel:+.0f} -> " + ("waiting for the drop, then picking it up" if wait > 0 else "picking it up"))
        self.mode = "LOOT"
        self.loot_rel, self.loot_since, self.loot_stop_at, self.walked_for_loot = rel, obs.t, None, 0.0
        self.loot_wait, self.loot_taps, self.loot_dir, self.loot_phase = wait, 0, None, "wait"
        self.loot_single, self.loot_walk_since = single, None
        self.loot_near, self.loot_tries, self.loot_got = False, 0, 0
        self.loot_origin = self._map_x(obs, 0.0)                     # map x where looting began
        return []

    def _phase_pause(self, obs):
        """A randomized moment between two phases (done looting -> next target), where a player would 'think'.
        The user: pauses belong after a kill/loot/hit or while wandering - never on the way to a target."""
        tm = self.cfg.timing
        self.pause_until = obs.t + self.hz.between(tm.phase_pause_min_s, tm.phase_pause_max_s)

    def _pickup_gap(self):
        tm = self.cfg.timing
        return self.hz.between(tm.pickup_gap_min_s, tm.pickup_gap_max_s)

    def _leave_loot(self, obs, rel, ready_at):
        """Remember a drop we can't pick up now (a fight comes first); SEEK comes back for it."""
        if not self.cfg.perception.loot:
            return
        m = self._map_x(obs, rel)
        if m is not None:
            self.pending_loot.append((obs.t + self.cfg.timing.loot_memory_s, m, ready_at))

    def _disengage(self, obs, why, counter=None):
        if counter:
            self.stats[counter] += 1
        self._say(obs, f"ENGAGE -> SEEK: {why}")
        self.mode, self.target = "SEEK", None
        return self._release() + [Untrack()]

    # ------------------------------------------------------------------ step
    def step(self, obs: Observation) -> list:
        self.events = []
        if obs.lie_detector:            # the game's anti-bot test (pkg_potions1): hands off at once, the user answers
            self._say(obs, "LIE DETECTOR on screen -> hands off")
            return self._release() + [Stop("LIE DETECTOR on screen - answer it yourself")]
        self._pick_attack(obs)
        if self.contested:
            self._update_contested(obs)
        acts = self._potions(obs) + self._step(obs)
        return acts + self._walk_pickup(obs, acts)

    def _walk_pickup(self, obs, acts) -> list:
        """Walking past a drop we see: spam a few Z on the way, like a player (the user: 'they pick up loot while
        walking at every opportunity, spamming a few Zs ... when they pass the item'). The walk key stays down
        (a pickup tap doesn't release it). A burst starts only while walking and is tapped out even if we stop;
        swinging cancels it."""
        cfg, z, tm, t = self.cfg, self.cfg.zones, self.cfg.timing, obs.t
        if not self._sight() or obs.me is None or self._swinging() or \
                any(isinstance(a, Stop) for a in acts):
            self.pass_taps = 0                                  # swinging / stopped: no more Z
            return []
        if any(isinstance(a, Tap) for a in acts):
            return []                                           # (a turn or a pickup this tick already)
        px, feet = obs.me
        self.passed = [p for p in self.passed if p[0] > t]
        if self.pass_taps == 0:
            if self.held not in ("left", "right"):
                return []                                       # a burst starts only while walking past; once
                                                                # started it's finished (a player stopping still
                                                                # taps out the burst)
            near = [d for d in obs.drops if abs(cx(d) - px) <= z.pass_reach and -z.same_level <= bottom(d) - feet <= 12
                    and not any(abs(self.odo + cx(d) - px - p[1]) < z.drop_same and p[0] - tm.bad_drop_s + 3.0 > t
                                for p in self.passed)]                # (one burst per drop per pass)
            if not near:
                return []
            for d in near:
                self.passed.append((t + tm.bad_drop_s, self.odo + cx(d) - px))
            others = sum(1 for d in obs.drops if abs(cx(d) - cx(near[0])) <= z.pile_px) - 1
            n = min(tm.taps_cap, self.hz.count(tm.pass_taps_min, tm.pass_taps_max) + max(0, others))
            self.pass_taps, self.pass_next = n, t
            self.pass_gap = self.hz.between(tm.pass_window_min_s, tm.pass_window_max_s) / max(1, n - 1)
            self.stats["walk_pickups"] += 1
            self._say(obs, f"walking past a drop at dx {cx(near[0]) - px:+.0f} -> {n} x {cfg.keys.pickup} on the way")
        if t < self.pass_next:
            return []
        self.pass_taps -= 1
        self.pass_next = t + self.hz.vary(self.pass_gap)
        return [Tap(cfg.keys.pickup, tm.pickup_press_s)]

    def _pick_attack(self, obs) -> None:
        """Out of MP and no MP potions -> swing with the plain attack (no MP) instead of the skill; back to the skill
        once there's MP for a cast (the user: 'when I gain enough mana to power strike it should be space, until
        OOM again'). A held swing switches keys on the next hold (one key-up/key-down, like any key change).
        With the HUD's exact MP (session 16) the skill's cost is measured: each cast takes it off the number while
        the skill is held. Unknown yet -> the skill held at low MP with MP not dropping = it isn't firing ("You
        don't have enough MP to use this skill", 101 ticks of Power Strike at 17/359 MP): that MP + 1 is the least
        a cast needs. No exact MP at all -> the old share thresholds (basic_below_mp / skill_again_mp)."""
        cfg, s = self.cfg, self.cfg.safety
        skill, basic = cfg.keys.attack, cfg.keys.basic_attack
        if not basic or basic == skill or self.attack_key not in (skill, basic):
            self.attack_key = skill
            if not basic or basic == skill:
                return
        mp, prev = obs.mp_now, self.prev_mp
        self.prev_mp = mp
        if mp is not None and prev is not None and self.held == skill and 0 < prev - mp <= s.skill_cost_max:
            self.cast_costs = (self.cast_costs + [prev - mp])[-5:]          # one cast's MP off the number
            cost = sorted(self.cast_costs)[len(self.cast_costs) // 2]
            if cost != self.skill_cost:
                self._say(obs, f"{skill} costs {cost} MP (measured)")
            self.skill_cost = cost
            self.skill_hold = None
        need = self.skill_cost or self.skill_min_mp                   # MP a cast needs (0: not known yet)
        if (self.held == skill and not self.skill_cost and mp is not None and obs.mp < s.skill_stall_below
                and not self._have("MP", obs)):
            if self.skill_hold is None or mp < self.skill_hold[1]:
                self.skill_hold = [obs.t, mp]
            elif obs.t - self.skill_hold[0] >= self.hz.vary(s.skill_stall_s):
                self.skill_min_mp = max(self.skill_min_mp, mp + 1)
                self.skill_hold = None
                self.attack_key = basic
                self.stats["basic_switches"] += 1
                self._say(obs, f"{skill} held at MP {mp} and MP isn't dropping -> not enough MP to cast: "
                               f"plain attack ({basic}); skill again from {self.skill_min_mp} MP")
                return
        elif self.held != skill:
            self.skill_hold = None
        if mp is not None and need:
            out_of_mp, enough = mp < need, mp >= need
        else:
            out_of_mp, enough = obs.mp < s.basic_below_mp, obs.mp >= s.skill_again_mp
        what = f"MP {mp}" if mp is not None else f"MP {obs.mp:.0%}"
        if self.attack_key == skill and out_of_mp and not self._have("MP", obs):
            self.attack_key = basic
            self.stats["basic_switches"] += 1
            self._say(obs, f"{what}{f' < {need} for a cast' if need and mp is not None else ''}, no MP potions "
                           f"-> plain attack ({basic})")
        elif self.attack_key != skill and (enough or self._have("MP", obs)):
            self.attack_key = skill
            self._say(obs, f"{what} -> skill attack again ({skill})")

    def _swinging(self) -> bool:
        return self.held is not None and self.held in (self.cfg.keys.attack, self.cfg.keys.basic_attack)

    def _have(self, kind, obs) -> bool:
        """Potions of this kind left: an item in the slot and not found used up (the slot keeps its icon with a
        '0' when the last potion is gone, so a filled slot alone doesn't prove anything)."""
        slot = obs.hp_potions if kind == "HP" else obs.mp_potions
        if bool(slot) and kind in self.potion_check:
            return True                                     # a press is being judged: don't give up before the verdict
        return bool(slot) and kind not in self.potions_out

    def _potions(self, obs) -> list:
        """Drink like a player in a fight: HP (MP) under hp_potion_at (mp_potion_at) and an item in that potion's
        quickslot -> tap its key; a randomized pause before the next one (the bar needs a moment to fill).
        Each press must raise the bar; potion_fails presses in a row that don't = used up (no more presses, the
        45 % stop / plain attack apply), then one probe press every potion_recheck_* s in case of a restock."""
        cfg, tm, t, out = self.cfg, self.cfg.timing, obs.t, []
        for kind, level, slot, at, key in (
                ("HP", obs.hp, obs.hp_potions, cfg.safety.hp_potion_at, cfg.keys.hp_potion),
                ("MP", obs.mp, obs.mp_potions, cfg.safety.mp_potion_at, cfg.keys.mp_potion)):
            chk = self.potion_check.get(kind)
            if chk is not None:
                chk[2] = max(chk[2], level)
                if t - chk[0] < tm.potion_verify_s:
                    continue                                    # wait for the bar before judging / pressing again
                del self.potion_check[kind]
                if chk[2] >= chk[1] + tm.potion_gain:
                    self.potion_fails[kind] = 0
                    if kind == "HP":
                        self.stop_probed = False
                    if self.potions_out.pop(kind, None) is not None:
                        self._say(obs, f"{kind} potion worked -> {kind} potions available again")
                else:
                    self.potion_fails[kind] = self.potion_fails.get(kind, 0) + 1
                    if self.potion_fails[kind] >= tm.potion_fails and kind not in self.potions_out:
                        self.stats["potions_out"] += 1
                        self._say(obs, f"{kind} potion did nothing {self.potion_fails[kind]}x -> {kind} potions used up")
                    if self.potion_fails[kind] >= tm.potion_fails:
                        self.potions_out[kind] = t + self.hz.between(tm.potion_recheck_min_s, tm.potion_recheck_max_s)
            if level >= at or not slot or t < self.potion_ready.get(kind, -1.0):
                continue
            if kind in self.potions_out:
                last_chance = kind == "HP" and level < cfg.safety.hp_stop and not self.stop_probed
                if t < self.potions_out[kind] and not last_chance:
                    continue
                if last_chance:
                    self.stop_probed = True                 # about to stop: one more press first (session 16:
                    #                                         a slow Meat read 'did nothing' -> stopped with 49 left)
                self.potions_out[kind] = t + self.hz.between(tm.potion_recheck_min_s, tm.potion_recheck_max_s)
                self._say(obs, f"{kind} {level:.0%} -> probe press ({key}): restocked?")
            else:
                self._say(obs, f"{kind} {level:.0%} -> potion ({key})")
            self.potion_ready[kind] = t + self.hz.vary(tm.potion_cooldown_s)
            self.potion_check[kind] = [t, level, level]
            self.stats["potions"] += 1
            out.append(Tap(key, tm.potion_press_s))
        return out

    def _step(self, obs: Observation) -> list:
        cfg, t = self.cfg, obs.t
        if self.prev_hp_raw is not None and obs.hp_raw < self.prev_hp_raw - 0.005:
            self.damaged_at = t
        self.prev_hp_raw = obs.hp_raw
        damaged = t - self.damaged_at < 0.6                  # remembered briefly (a Look re-asks in the same tick)
        self.damaged = damaged

        # 1. safety: with HP potions we fight on and drink at hp_potion_at; none left -> stop at hp_stop
        if obs.hp < cfg.safety.hp_stop and not self._have("HP", obs):
            return self._release() + [Stop(f"HP {obs.hp:.0%} below {cfg.safety.hp_stop:.0%} and no HP potions left")]

        # 2. can't see ourselves
        if obs.me is None:
            if self.me_seen_at is None:
                return []
            missing = t - self.me_seen_at
            acts = []
            if missing > cfg.timing.self_missing_s:
                acts += self._release()
                if not self.self_lost_logged:
                    self._say(obs, f"can't see own name tag for {missing:.1f}s -> keys released")
                    self.stats["self_lost"] += 1
                    self.self_lost_logged = True
                if self.last_walk_dir and self.backouts < 3 and t - self.last_backout > 0.6:
                    back = "right" if self.last_walk_dir == "left" else "left"
                    self.backouts += 1
                    self.last_backout, self.facing = t, back
                    self.stats["backouts"] += 1
                    self._say(obs, f"hidden? backing out {back} ({self.backouts}/3)")
                    acts.append(Tap(back, 0.25))
            return acts
        if self.self_lost_logged:
            self._say(obs, f"found own name tag again after {t - self.me_seen_at:.1f}s")
            self.self_lost_logged = False
            if self.backouts and self.last_walk_dir:          # don't walk straight back behind it - briefly
                avoid = self.hz.vary(cfg.timing.hidden_avoid_s)  # (15 s cut off half the floor: pkg_sprites3)
                self.blocked[self.last_walk_dir] = max(self.blocked.get(self.last_walk_dir, -1), t + avoid)
                self._say(obs, f"avoiding {self.last_walk_dir} for {avoid:.1f}s (where we were hidden)")
        self.moved = 0.0
        if self.last_px is not None and obs.scene_dx is not None:
            self.moved = (obs.me[0] - self.last_px) - obs.scene_dx          # camera follows us
        self.last_px = obs.me[0]
        self.odo += self.moved                                              # where we are along the ground
        self.odo_hist = [h for h in self.odo_hist if h[0] > t - 1.0] + [(t, self.odo)]
        self.me_seen_at, self.backouts = t, 0
        if self.start_dot is None and obs.dot is not None:   # the leash's centre: a steady reading, not the first
            self.dot_hist = (self.dot_hist + [obs.dot])[-5:]  # (pkg_sprites6 began with a misread (3.9, 81.5))
            if len(self.dot_hist) == 5 and all(abs(d[0] - obs.dot[0]) <= 1.5 and abs(d[1] - obs.dot[1]) <= 1.5
                                               for d in self.dot_hist):
                self.start_dot = obs.dot
        if self.held in ("left", "right"):
            self.last_walk_dir, self.last_walk_t = self.held, t
        px, feet = obs.me

        # 3. blocked: holding a walk key while the minimap dot doesn't move
        if self.held in ("left", "right") and obs.dot is not None:
            if self.walk_ref is None or self.walk_ref[2] != self.held or abs(obs.dot[0] - self.walk_ref[1]) >= 0.6:
                if self.walk_ref is not None:                  # moved (or turned): a new block gets new jump tries
                    self.block_jumps_done = 0
                self.walk_ref = (t, obs.dot[0], self.held)
            elif t - self.walk_ref[0] > cfg.timing.blocked_s and self._block_jump_ok(obs, self.held):
                return self._block_jump(obs, "minimap x frozen")
            elif t - self.walk_ref[0] > cfg.timing.blocked_s:
                d = self.held
                self.blocked[d] = t + cfg.timing.blocked_avoid_s
                self.stats["blocked"] += 1
                self.walk_ref = None
                self._say(obs, f"blocked walking {d} (minimap x frozen) -> avoiding {d} for {cfg.timing.blocked_avoid_s:.0f}s")
                if self.mode == "ENGAGE":
                    return self._disengage(obs, "target is past an obstacle")
                return self._release()                     # (LOOT: the wall ends the walk; burst where we are)
        elif self.held in ("left", "right"):
            # no minimap reading (pkg_sight1: the inventory window lay over it, 93 % of ticks): our own movement
            # instead - holding a walk key without moving (pkg_sight1 130 s: 5 s against a step)
            if self.walk_ref is None or self.walk_ref[2] != self.held or abs(self.odo - self.walk_ref[1]) >= 4:
                if self.walk_ref is not None:
                    self.block_jumps_done = 0
                self.walk_ref = (t, self.odo, self.held)
            elif t - self.walk_ref[0] > cfg.timing.blocked_s and self._block_jump_ok(obs, self.held):
                return self._block_jump(obs, "not moving")
            elif t - self.walk_ref[0] > cfg.timing.blocked_s:
                d = self.held
                self.blocked[d] = t + cfg.timing.blocked_avoid_s
                self.stats["blocked"] += 1
                self.walk_ref = None
                self._say(obs, f"blocked walking {d} (not moving) -> avoiding {d} for {cfg.timing.blocked_avoid_s:.0f}s")
                if self.mode == "ENGAGE":
                    return self._disengage(obs, "target is past an obstacle")
                return self._release()
        else:
            self.walk_ref = None

        if self.mode == "SEEK":
            acts = self._seek(obs, px)
        elif self.mode == "LOOT":
            acts = self._loot(obs, px, damaged)
        else:
            acts = self._fight(obs, px, damaged)
        return acts + self._step_jump(obs, acts)

    # ------------------------------------------------------------------ crowding
    def _lost_one(self, obs):
        """A target lost to other players. Several within crowd_window_s = contested: only mobs within chase_max
        are chosen (far ones die before we get there); calm again once the losses age out."""
        self.lost_to_others.append(obs.t)
        self._update_contested(obs)

    def _update_contested(self, obs):
        tm, t = self.cfg.timing, obs.t
        self.lost_to_others = [x for x in self.lost_to_others if x > t - tm.crowd_window_s]
        now = len(self.lost_to_others) >= tm.crowd_losses
        if now != self.contested:
            self.contested = now
            self._say(obs, f"{len(self.lost_to_others)} mobs lost to others in {tm.crowd_window_s:.0f}s -> contested: "
                           f"only mobs within {self.cfg.zones.chase_max:.0f} px" if now else
                           "no mobs lost to others lately -> far mobs are fair game again")

    # ------------------------------------------------------------------ LOOT
    def _loot(self, obs, px, damaged):
        cfg, z, tm, t = self.cfg, self.cfg.zones, self.cfg.timing, obs.t
        reach = [b for b in obs.known_mobs if abs(cx(b) - px) <= (z.hold_max if damaged else z.hit_max)
                 and self._fair(obs, b, px)]
        if reach:                                                        # fighting beats picking up
            self.mode = "SEEK"
            self._leave_loot(obs, self.loot_rel - self.walked_for_loot, self.loot_since + self.loot_wait)
            return self._release() + self._engage(obs, min(reach, key=lambda b: abs(cx(b) - px)),
                                                  "mob in reach -> leaving the loot for now")
        if damaged:                                                      # hit by something we can't see
            self.mode = "SEEK"
            self._leave_loot(obs, self.loot_rel - self.walked_for_loot, self.loot_since + self.loot_wait)
            self._say(obs, "hit by something unseen -> leaving the loot for now")
            return self._release()
        if self._sight():
            # mobs before loot (the user, perion4: 'compete with these bots'; 12-15 s walked 555 px to a drop past a
            # Stump in sight). Drops are private in Classic World: they wait; SEEK collects them when no mob is
            # around. Only a drop right at our feet is taken first.
            mobs = [b for b in obs.known_mobs if self._pickable(obs, b, px)]
            if mobs and not any(abs(cx(d) - px) <= z.loot_vs_mob for d in obs.drops):
                self.mode = "SEEK"
                return self._release() + self._engage(obs, min(mobs, key=lambda b: abs(cx(b) - px)),
                                                      "mob in sight -> mobs before loot")
            return self._loot_sight(obs, px)
        if t - self.loot_since > tm.loot_timeout_s:
            self.stats["loot_gave_up"] += 1
            self._say(obs, f"couldn't get onto the loot (walked {self.walked_for_loot:+.0f} of "
                           f"{self.loot_rel:+.0f}) -> SEEK")
            self.mode = "SEEK"
            self._phase_pause(obs)
            return self._release()
        if t - self.loot_since < self.loot_wait:                        # still dying: nothing has dropped yet
            return self._release()
        if self.held in ("left", "right"):
            self.walked_for_loot += self.moved
        pos, c, spread = self.walked_for_loot, self.loot_rel, z.loot_spread   # all relative to where looting began
        if self.loot_dir is None:        # like a player: onto the drop, spam Z; a little further across, spam Z
            d = self.loot_dir = 1 if (c > z.loot_reach or (abs(c) <= z.loot_reach and self.facing != "left")) else -1
            if abs(c - pos) <= z.loot_reach:                             # on it already: check both sides too
                self.loot_wps = [pos, c + z.loot_side * d, c - z.loot_side * d]
            elif self.loot_single:                                       # overshot it? then it's behind us
                self.loot_wps = [c, c - z.loot_side * d]
            else:                                                        # walking in covers the near side
                self.loot_wps = [c, c + z.loot_side * d]
            self.loot_wp, self.loot_phase, self.loot_next_tap = 0, "walk", t
            self.stats["loot_pickups"] += 1
            self._say(obs, f"looting: onto the drop at dx {c:+.0f}, spam {cfg.keys.pickup}, then "
                           f"{z.loot_side:.0f} px further across")
        acts = []
        if self.loot_phase == "walk":
            rem = self.loot_wps[self.loot_wp] - pos
            key = "right" if rem > 0 else "left"
            long_walk = self.loot_walk_since is not None and t - self.loot_walk_since >= tm.long_walk_s
            if abs(rem) <= (z.loot_slide_long if long_walk else z.loot_slide_short) or not self._allowed(obs, key):
                self.loot_walk_since = None
                if not self._allowed(obs, key):                          # a wall: burst here, skip what's past it
                    self.loot_wps = self.loot_wps[:self.loot_wp + 1]
                self.loot_phase, self.loot_stop_at = "settle", t
                self.loot_settle = self.hz.vary(tm.slide_settle_s)
                lo, hi = (tm.final_taps_min, tm.final_taps_max) if self.loot_wp == 0 else (tm.side_taps_min, tm.side_taps_max)
                self.loot_taps, self.final_taps = 0, self.hz.count(lo, hi)
                return self._release()
            if self.loot_walk_since is None:
                self.loot_walk_since = t
            acts += self._hold(key)
            if abs(pos - c) <= spread + z.loot_reach and t >= self.loot_next_tap:   # running over the drop
                self.loot_next_tap = t + self._pickup_gap()
                acts.append(Tap(cfg.keys.pickup, tm.pickup_press_s))
            return acts
        if self.loot_phase == "settle":
            if t - self.loot_stop_at < self.loot_settle:
                return self._release()
            self.loot_phase = "burst"
            self.loot_next_tap = max(self.loot_next_tap, t)
        if t < self.loot_next_tap:                                       # one item per press: pace them
            return []
        self.loot_taps += 1
        self.loot_next_tap = t + self._pickup_gap()
        if self.loot_taps >= self.final_taps:
            self.loot_wp += 1
            if self.loot_wp < len(self.loot_wps):
                self.loot_phase = "walk"
            else:
                self.mode = "SEEK"
                self._phase_pause(obs)
                if self.loot_origin is not None:                         # we swept up what lay around there too
                    centre = self.loot_origin + c
                    self.pending_loot = [p for p in self.pending_loot if abs(p[1] - centre) > spread]
        return self._release() + [Tap(cfg.keys.pickup, tm.pickup_press_s)]

    # ------------------------------------------------------------------ LOOT by sight
    def _sight(self) -> bool:
        return self._sprite_mode() and self.cfg.perception.loot and self.cfg.perception.loot_by_sight

    def _lootable(self, obs, px) -> list:
        """Drops seen on the ground worth walking to: in range, not given up on, not past a wall/the leash.
        (Classic World: other players' drops are invisible to us, so every drop seen is ours.)"""
        z, t = self.cfg.zones, obs.t
        self.bad_drops = [b for b in self.bad_drops if b[0] > t]
        self.drop_bursts = [b for b in self.drop_bursts if b[0] > t]
        out = []
        for d in obs.drops:
            rel = cx(d) - px
            if not -z.same_level <= bottom(d) - obs.me[1] <= 12:
                continue                                   # not on our floor: can't stand on it
            reach = z.loot_vs_mob if obs.known_mobs else z.loot_idle_max   # no mob around: loot comes first
            if abs(rel) > reach or any(abs(self.odo + rel - b[1]) < z.drop_same for b in self.bad_drops):
                continue
            if sum(abs(self.odo + rel - b[1]) < z.drop_same for b in self.drop_bursts) >= self.cfg.timing.drop_tries:
                continue                                   # bursts there twice already: it doesn't come up
            if any(abs(self.odo + rel - p[1]) < z.drop_same and p[0] - self.cfg.timing.bad_drop_s + 1.0 > t
                   for p in self.passed):
                continue                                   # just Z'd it walking past: picked up items fly up to us
                                                           # and are still 'seen' a moment - give it a second
            if abs(rel) > z.loot_reach and not self._allowed(obs, "left" if rel < 0 else "right"):
                continue
            out.append(d)
        return out

    def _give_up_drop(self, obs, why):
        self.bad_drops.append((obs.t + self.cfg.timing.bad_drop_s, self.loot_tw))
        self.stats["loot_gave_up"] += 1
        self._say(obs, f"drop at dx {self.loot_tw - self.odo:+.0f}: {why} -> leaving it")
        self.loot_phase = "choose"
        return self._release()

    def _loot_sight(self, obs, px):
        """Like a player: walk onto a drop we see, stop, spam Z 2-4 times, look: gone -> the next one; none left
        -> done. No Z on empty ground, none while walking (it doesn't pick anything up while moving)."""
        cfg, z, tm, t = self.cfg, self.cfg.zones, self.cfg.timing, obs.t
        if self.loot_phase == "wait":
            self.loot_phase = "choose"
            self.loot_look = self.hz.vary(tm.drop_look_s)
        if self.loot_phase == "choose":
            drops = self._lootable(obs, px)
            if not drops:
                if t - self.loot_since < self.loot_wait + self.loot_look and not self.loot_got:
                    return self._release() if self.held is not None else []      # still falling / settling
                if self.loot_near and not self.loot_got and self.loot_tries == 0:
                    self.loot_tries, self.loot_tw, self.loot_tw_since = 1, self.odo, t   # drops at our feet
                    self._say(obs, f"our mob died next to us, no drop in sight -> {cfg.keys.pickup} where we stand")
                    self.loot_check_at = -1.0                                     # no look after this burst
                    return self._burst_here(obs)
                self._say(obs, f"no (more) drops in sight -> SEEK ({self.loot_got} picked up)")
                self.mode = "SEEK"
                self._phase_pause(obs)
                if self.held in ("left", "right"):          # walked through the last one: walk on, same way
                    self.patrol_dir, self.idle_walk_until = self.held, None
                    return []
                return self._release()
            d = min(drops, key=lambda d: abs(cx(d) - px))
            rel = cx(d) - px
            self.loot_tw, self.loot_tw_since, self.loot_tries = self.odo + rel, t, 0
            pile = sum(abs(cx(e) - cx(d)) <= z.pile_px for e in obs.drops) >= z.pile_n
            again = any(abs(self.loot_tw - p[1]) < z.drop_same for p in self.passed)
            if pile or again or abs(rel) <= z.loot_reach:
                self.loot_phase, self.loot_walk_since = "walk", None          # stop on it, spam Z, look
                why = "a pile" if pile else "still there after walking past it" if again else "right here"
                self._say(obs, f"drop at dx {rel:+.0f} ({why}) -> stopping on it")
            else:                                                            # walk through it, Z on the way
                self.loot_phase = "pass"
                self.loot_pass_to = self.loot_tw + (1 if rel > 0 else -1) * self.hz.between(z.pass_over_min,
                                                                                          z.pass_over_max)
                self._say(obs, f"drop seen at dx {rel:+.0f} -> walking through it")
        if t - self.loot_tw_since > tm.drop_timeout_s:
            return self._give_up_drop(obs, "taking too long")
        if self.loot_phase == "pass":
            rem = self.loot_pass_to - self.odo
            key = "right" if rem > 0 else "left"
            if (rem > 0) != (self.loot_pass_to > self.loot_tw) or abs(rem) < 4:     # past it: the next one
                self.loot_phase = "choose"
                self.loot_got += 1
                return self._loot_sight(obs, px)
            if not self._allowed(obs, key):
                return self._give_up_drop(obs, "past a wall / the leash")
            return self._hold(key)
        if self.loot_phase == "walk":
            seen = [d for d in obs.drops if abs(self.odo + cx(d) - px - self.loot_tw) < z.drop_same]
            if seen:                                                     # aim at where we see it now
                near = min(seen, key=lambda d: abs(self.odo + cx(d) - px - self.loot_tw))
                self.loot_tw = self.odo + cx(near) - px
            rem = self.loot_tw - self.odo
            key = "right" if rem > 0 else "left"
            long_walk = self.loot_walk_since is not None and t - self.loot_walk_since >= tm.long_walk_s
            walking = self.held in ("left", "right")
            if abs(rem) <= z.loot_reach or (walking and abs(rem) <= (z.loot_slide_long if long_walk
                                                                     else z.loot_slide_short)):
                return self._burst_here(obs)
            if not self._allowed(obs, key):
                return self._give_up_drop(obs, "past a wall / the leash")
            if self.loot_walk_since is None:
                self.loot_walk_since = t
            return self._hold(key)
        if self.loot_phase == "settle":
            if t - self.loot_stop_at < self.loot_settle:
                return self._release() if self.held is not None else []
            self.loot_phase = "burst"
            self.loot_next_tap = max(self.loot_next_tap, t)
        if self.loot_phase == "burst":
            if t < self.loot_next_tap:
                return []
            self.loot_taps += 1
            self.loot_next_tap = t + self._pickup_gap()
            if self.loot_taps >= self.final_taps:
                self.drop_bursts.append((t + tm.bad_drop_s, self.loot_tw))
                if self.loot_check_at == -1.0:                           # the burst at our feet: done, look again
                    self.loot_phase, self.loot_check_at = "choose", 0.0
                    self.loot_near = False
                else:
                    self.loot_phase, self.loot_check_at = "check", t + self.hz.vary(tm.loot_check_s)
            return self._release() + [Tap(cfg.keys.pickup, tm.pickup_press_s)]
        if self.loot_phase == "check":
            if t < self.loot_check_at:
                return []
            left = [d for d in obs.drops if abs(self.odo + cx(d) - px - self.loot_tw) < z.drop_same]
            if not left:
                self.loot_got += 1
                self.stats["loot_pickups"] += 1
                self.loot_phase = "choose"
                return self._loot_sight(obs, px)
            self.loot_tries += 1
            if self.loot_tries >= tm.drop_tries:
                return self._give_up_drop(obs, f"still there after {self.loot_tries} bursts")
            self.loot_phase, self.loot_walk_since = "walk", None          # step closer if needed, then again
            return self._loot_sight(obs, px)
        return self._release()

    def _burst_here(self, obs):
        """Stop where we are; once the slide ends, spam Z 2-4 times (short random gaps)."""
        tm = self.cfg.timing
        self.loot_settle = self.hz.vary(tm.slide_settle_s) if self.held in ("left", "right") else 0.0
        self.loot_phase, self.loot_stop_at, self.loot_walk_since = "settle", obs.t, None
        rel = self.loot_tw - self.odo
        others = sum(1 for d in obs.drops if obs.me is not None
                     and abs(cx(d) - obs.me[0] - rel) <= self.cfg.zones.pile_px) - 1
        self.loot_taps = 0
        self.final_taps = min(tm.taps_cap, self.hz.count(tm.drop_taps_min, tm.drop_taps_max) + max(0, others))
        return self._release()

    # ------------------------------------------------------------------ hit by something unseen
    def _unseen_hit(self, obs):
        cfg, z, tm, t = self.cfg, self.cfg.zones, self.cfg.timing, obs.t
        if self.damaged and self.damaged_at > self.hit_t + 0.25:                 # a new hit
            self.hit_t = self.damaged_at
            before = [o for (tt, o) in self.odo_hist if tt <= self.damaged_at - 0.1]
            self.hit_odo = before[-1] if before else self.odo                  # where we stood when it hit us
            self.recover_until = t + self.hz.vary(tm.recover_s)
            self.knock_until = t + self.hz.vary(tm.knock_s)
            self.swing_count, self.swing_until = 0, -1e9
            self.stats["blind_swings"] += 1
            self._say(obs, f"hit by something unseen (HP {obs.hp:.0%}) -> back to where it hit us, swing there")
        if t >= self.recover_until:
            return None
        if t < self.knock_until:                                                # still being knocked back
            return self._release()
        rel = self.hit_odo - self.odo
        if abs(rel) >= z.recover_min and self.swing_count == 0:
            d = "left" if rel < 0 else "right"
            if abs(rel) > z.hit_max - 8 and self._allowed(obs, d):
                return self._hold(d)                                            # walk back toward the spot
            return self._turn(d) + self._hold(self.attack_key)                  # the spot is in reach: swing
        # not moved by the hit: it's on top of us, either side
        other = "right" if self.swing_dir == "left" else "left"
        if self.swing_count == 0:
            if self.last_walk_dir and t - self.last_walk_t < 0.8:             # walked past it: it's behind us
                first = "right" if self.last_walk_dir == "left" else "left"
            else:
                first = self.facing or "right"
            self.swing_dir, self.swing_count = first, 1
            self.swing_until = t + self.hz.vary(tm.blind_swing_s)
        elif t >= self.swing_until and self.swing_count == 1:
            self.swing_dir, self.swing_count = other, 2
            self.swing_until = t + self.hz.vary(tm.blind_swing_s)
        if t < self.swing_until:
            return self._turn(self.swing_dir) + self._hold(self.attack_key)
        self.recover_until = t
        return None

    # ------------------------------------------------------------------ SEEK
    def _sprite_mode(self) -> bool:
        """The map's mobs are found by their sprites on every frame (run --map): motion looks add nothing."""
        return self.cfg.perception.map_id is not None

    def _walk_on(self, obs):
        """Nothing in sight: walk on like a player scanning the floor for a random 2-3 s (a wall or the leash turns
        us around), then stand still and wait for a spawn. pkg_potions1: pacing wall to wall for 57 s on an empty
        floor got us a lie detector test."""
        tm = self.cfg.timing
        home = self._spawn_way(obs)
        if home is not None:                    # far from where the mobs spawn: head there first, no standing
            self.idle_walk_until = None         # (arrived: the usual 2-3 s walk on, then stand)
            if self.held != home:
                self.stats["patrols"] += 1
                self.stats["spawn_walks"] += 1
                self._say(obs, f"no mobs in sight -> walking {home}, toward the densest spawns "
                               f"(map x {self.navmap.spawn_center(obs.map_pos[1]):.0f}, we're at {obs.map_pos[0]:.0f})")
            self.patrol_dir = home
            return self._hold(home)
        if self.idle_walk_until is None:
            self.idle_walk_until = obs.t + self.hz.between(tm.idle_walk_min_s, tm.idle_walk_max_s)
        if obs.t >= self.idle_walk_until:
            if self.idle_walk_until > -1e8:
                self.stats["waits"] += 1
                self._say(obs, "nothing to attack -> standing still, waiting for a spawn")
                self.idle_walk_until = -1e9                             # said once per idle spell
                self.idle_jump_at = obs.t + self.hz.between(tm.idle_jump_first_min_s, tm.idle_jump_first_max_s)
                self.idle_jumps_left = 0
            if obs.t < self.idle_hop_until:                             # mid-hop: keep moving that way
                return self._hold(self.idle_hop_dir)
            return (self._release() if self.held is not None else []) + self._idle_jump(obs)
        for d in (self.patrol_dir, "right" if self.patrol_dir == "left" else "left"):
            if self._allowed(obs, d):
                if self.held != d:
                    self.stats["patrols"] += 1
                    self._say(obs, f"no mobs in sight -> walking {d}")
                self.patrol_dir = d
                return self._hold(d)
        # both avoided (a wall at each end of an empty floor): walk away from the wall we met last
        walls = {k: v for k, v in self.blocked.items() if v > obs.t and k in ("left", "right")}
        if not walls:
            return self._release()
        d = "right" if max(walls, key=walls.get) == "left" else "left"
        if self.held != d:
            self.stats["patrols"] += 1
            self._say(obs, f"walls both ways -> walking {d}, away from the last one")
        self.patrol_dir = d
        return self._hold(d)

    def _spawn_way(self, obs) -> str | None:
        """Nothing in sight: the way to the map's densest spawn area if we're farther than cfg.nav.spawn_home from
        it and may walk that way; else None (stay: walk on / stand as usual). The user (2026-11-02, Rain-Forest):
        'gravitate towards the most dense spawning area' - rain_base: every idle walk went left (patrol_dir's
        default), 2nd minute spent past the left portal where nothing spawns."""
        c = self.cfg.nav
        if not c.seek_spawns or self.navmap is None or obs.map_pos is None:
            return None
        home = self.navmap.spawn_center(obs.map_pos[1])
        if home is None or abs(home - obs.map_pos[0]) <= c.spawn_home:
            return None
        d = "right" if home > obs.map_pos[0] else "left"
        return d if self._allowed(obs, d) else None

    def _idle_jump(self, obs) -> list:
        """Standing for a spawn: now and then a burst of 1-3 jumps, each moving one way (hold the direction, jump,
        keep holding until we land) - the user: 'jump a few times when no monsters are around', 'moving a certain
        direction when jumping'. Bursts go back and forth so we stay put; never into an avoided way / off the leash."""
        tm, t = self.cfg.timing, obs.t
        if not tm.idle_jumps or self.idle_jump_at is None or t < self.idle_jump_at or t < self.jump_ready:
            return []
        nv = self.cfg.nav
        home = self.navmap.spawn_center(obs.map_pos[1]) if (nv.seek_spawns and self.navmap is not None
                                                             and obs.map_pos is not None) else None
        if self.idle_jumps_left > 0 and home is not None and                 (home > obs.map_pos[0]) == (self.idle_hop_dir == "left") and                 abs(home - obs.map_pos[0]) > nv.spawn_home - nv.jump_reach:   # one more hop leaves the spawns
            self.idle_jumps_left = 0
            self.idle_jump_at = t + self.hz.between(tm.idle_jump_every_min_s, tm.idle_jump_every_max_s)
            return []
        if self.idle_jumps_left <= 0:                                   # a new burst: turn around from the last one
            self.idle_jumps_left = self.hz.count(tm.idle_jump_n_min, tm.idle_jump_n_max)
            back = "right" if self.idle_hop_dir == "left" else "left"
            if home is not None and abs(home - obs.map_pos[0]) > nv.jump_reach:
                back = "right" if home > obs.map_pos[0] else "left"     # off-centre: hop toward the spawns
            self.idle_hop_dir = back if self._allowed(obs, back) else self.idle_hop_dir
            if not self._allowed(obs, self.idle_hop_dir):
                self.idle_jump_at = t + self.hz.between(tm.idle_jump_every_min_s, tm.idle_jump_every_max_s)
                return []
            self._say(obs, f"idle -> {self.idle_jumps_left} jump(s) {self.idle_hop_dir}")
        self.idle_jumps_left -= 1
        self.stats["idle_jumps"] += 1
        acts = self._hold(self.idle_hop_dir) + self._jump(obs)
        self.idle_hop_until = self.jump_ready                           # hold the way until we've landed
        self.idle_jump_at = self.jump_ready + (self.hz.between(tm.idle_jump_gap_min_s, tm.idle_jump_gap_max_s)
                                               if self.idle_jumps_left > 0
                                               else self.hz.between(tm.idle_jump_every_min_s,
                                                                    tm.idle_jump_every_max_s))
        return acts

    def _jump(self, obs) -> list:
        """Press jump (the walk key, if held, stays down: a running jump). Airborne until jump_ready."""
        tm = self.cfg.timing
        self.jump_ready = obs.t + self.hz.vary(tm.jump_cooldown_s)
        self.stats["jumps"] += 1
        return [Tap(self.cfg.keys.jump, self.hz.vary(tm.jump_press_s))]

    def _step_jump(self, obs, acts) -> list:
        """Walking at a step our jump clears (the map's footholds: a wall rising <= jump_height to a higher floor):
        jump at a random 12-40 px from it, still holding the walk key. Map 10001070's 60 px pit walls."""
        cfg, tm, t = self.cfg, self.cfg.timing, obs.t
        if self.navmap is None or obs.platform is None or obs.map_pos is None or t < self.jump_ready or \
                self.held not in ("left", "right") or \
                any(isinstance(a, (Tap, Release, Stop, Look)) for a in acts):
            return []
        d = 1 if self.held == "right" else -1
        if (obs.platform, d) != self.step_key:
            self.step_key, self.step_trigger, self.step_tries = (obs.platform, d), None, 0
        s = self.navmap.step_ahead(obs.platform, obs.map_pos[0], d)
        if s is None or not 4 < s[1] <= cfg.nav.jump_height or s[0] < -20:          # (x is 16 px coarse)
            return []
        dist, rise = s
        if dist > tm.step_jump_max + 40:
            self.step_tries = 0                                     # walked away from it: a fresh approach
            return []
        if self.step_trigger is None:
            self.step_trigger = self.hz.between(tm.step_jump_min, tm.step_jump_max)
        if dist > self.step_trigger:
            return []
        if self.step_tries >= tm.step_jump_tries:
            self.blocked[self.held] = t + cfg.timing.blocked_avoid_s
            self.stats["blocked"] += 1
            self._say(obs, f"{self.step_tries} jumps didn't get us up the {rise:.0f} px step {self.held} -> "
                           f"avoiding {self.held}")
            self.step_tries = 0
            if self.mode == "ENGAGE":
                return self._disengage(obs, "target is past a step we can't jump")
            return self._release()
        self.step_tries += 1
        self.step_trigger = None
        self.stats["step_jumps"] += 1
        self._say(obs, f"step up {rise:.0f} px {dist:.0f} px ahead ({self.held}) -> jump")
        return self._jump(obs)

    def _block_jump(self, obs, why) -> list:
        """Blocked: jump once (walk key still down) before giving up on that way - a step the map doesn't know /
        no minimap reading. The block timer restarts; still stuck after it -> avoided as before."""
        self.block_jumps_done += 1
        self.walk_ref = None
        self.stats["block_jumps"] += 1
        self._say(obs, f"blocked walking {self.held} ({why}) -> jump")
        return self._jump(obs)

    def _block_jump_ok(self, obs, d) -> bool:
        """Blocked walking: worth a jump? Not past cfg.timing.block_jumps tries, and not at a wall the map says is
        too high (or the map's edge)."""
        if self.block_jumps_done >= self.cfg.timing.block_jumps or obs.t < self.jump_ready:
            return False
        if self.navmap is not None and obs.platform is not None and obs.map_pos is not None:
            s = self.navmap.step_ahead(obs.platform, obs.map_pos[0], 1 if d == "right" else -1)
            if s is not None and s[0] <= 40 and s[1] > self.cfg.nav.jump_height:
                return False
        return True

    def _seek(self, obs, px):
        cfg, t = self.cfg, obs.t
        if self.patrol_check is not None and obs.dot is not None:          # did the last patrol step move us?
            d, before = self.patrol_check
            self.patrol_check = None
            if abs(obs.dot[0] - before) < 0.5:
                self.blocked[d] = t + cfg.timing.blocked_avoid_s
                self.stats["blocked"] += 1
                self.patrol_dir = "right" if d == "left" else "left"
                self._say(obs, f"patrol {d} didn't move us (wall) -> avoiding {d}, turning around")
        self.drop_zones = [z for z in self.drop_zones if z[0] > t]
        self.not_mobs = [z for z in self.not_mobs if z[0] > t]
        self.pending_loot = [p for p in self.pending_loot if p[0] > t]
        # hit, and no mob visible near us (standing still = no motion; at our feet = inside our own body mask).
        # The knockback throws us either way, but the mob stays where we were hit: go back there and swing at it
        # (a hit shows its HP bar, and then it's fought like any other). No knockback: swing both sides.
        if not [b for b in obs.known_mobs if abs(cx(b) - px) <= cfg.zones.hold_max and self._fair(obs, b, px)]:
            acts = self._unseen_hit(obs)
            if acts is not None:
                return acts
        if self.pending_loot and obs.dot is not None and not obs.bar_mobs and not self._sight():  # left for a fight
            here = self._map_x(obs, 0.0)
            ok_loot = [p for p in self.pending_loot if abs(p[1] - here) <= cfg.zones.loot_max
                       and self._allowed(obs, "left" if p[1] < here else "right")]
            if ok_loot:
                p = min(ok_loot, key=lambda p: abs(p[1] - here))
                self.pending_loot.remove(p)
                self._say(obs, "back to a drop left behind for a fight")
                return self._release() + self._start_loot(obs, p[1] - here, max(0.0, p[2] - t))

        ok = lambda b: self._pickable(obs, b, px)          # noqa: E731
        pool = [b for b in obs.known_mobs if ok(b)]
        if self._sprite_mode():                     # every frame is checked for mobs: no stopping to look
            # loot near us beats a far mob (pkg_sight2 41 s: a drop 7 px away, walked ~500 px to a Shroom; on a
            # crowded map some mob is nearly always in sight, so drops were only taken on an empty screen).
            # A mob close by, or one fighting us (HP bar), still comes first.
            close = [b for b in pool if abs(cx(b) - px) <= cfg.zones.mob_over_loot or b in obs.bar_mobs]
            if self._sight() and not close and t >= self.pause_until and self._lootable(obs, px):
                self.idle_walk_until = None                 # (no stop: walking on into the loot is the point)
                return self._start_loot(obs, 0.0, 0.0) + self._loot_sight(obs, px)
            if pool:
                self.idle_walk_until = None                 # the next idle spell gets a fresh short walk
                pick = min(pool, key=lambda b: abs(cx(b) - px))
                if t < self.pause_until and abs(cx(pick) - px) > cfg.zones.hold_max and not self.damaged:
                    return self._release() if self.held is not None else []   # just finished looting: a beat
                return self._engage(obs, pick, f"SEEK -> ENGAGE ({len(pool)} candidates, HP {obs.hp:.0%})")
            return self._walk_on(obs)
        if not pool and obs.moving is None:
            self.stats["looks"] += 1
            return self._release() + [Look()]
        if not pool and obs.moving is not None and (obs.look_align or 0) >= cfg.perception.min_align:
            pool = [b for b in obs.moving if ok(b)]
        if pool:
            self.idle_looks = 0
            pick = min(pool, key=lambda b: abs(cx(b) - px))
            return self._engage(obs, pick, f"SEEK -> ENGAGE ({len(pool)} candidates, HP {obs.hp:.0%})")
        if obs.moving is None or (obs.look_align or 0) < cfg.perception.min_align:
            return self._release()                         # unsteady look: try again next tick, no counting
        self.idle_looks += 1
        if self.idle_looks < cfg.timing.idle_looks_before_patrol:
            return self._release()
        self.idle_looks = 0
        for d in (self.patrol_dir, "right" if self.patrol_dir == "left" else "left"):
            if self._allowed(obs, d):
                self.patrol_dir = d                                       # keep sweeping this way until we can't
                self.stats["patrols"] += 1
                self._say(obs, f"no mobs -> patrol {d}")
                self.facing = d
                if obs.dot is not None:
                    self.patrol_check = (d, obs.dot[0])
                return self._release() + [Tap(d, cfg.timing.patrol_s)]
        self._say(obs, "no mobs and both directions blocked -> waiting")
        return self._release()

    # ------------------------------------------------------------------ ENGAGE
    @staticmethod
    def _speed_known(tg) -> bool:
        return len(tg.ground) >= 3 and tg.ground[-1][0] - tg.ground[0][0] >= 0.2

    def _approach(self, tg) -> float:
        """How fast the target walks toward us (px/s along the ground; our own walking is taken out by the odometer),
        0 if it stands still or moves away. pkg_sprites3/4: snails closed 40-50 px/s while we swung, into contact."""
        tm = self.cfg.timing
        if not self._speed_known(tg):
            return 0.0
        (t0, x0), (t1, x1) = tg.ground[0], tg.ground[-1]
        v = (x1 - x0) / (t1 - t0) * (1 if tg.rel_dx < 0 else -1)
        return min(v, tm.approach_cap) if v >= tm.approach_min else 0.0

    def _fight(self, obs, px, damaged):
        cfg, z, tm, t = self.cfg, self.cfg.zones, self.cfg.timing, obs.t
        tg = self.target
        acts = []

        # 4. kill confirmed by the game
        # kills come from the HUD's EXP points only (exact; the bar moves 1 px per ~15 points, perion6): up = we
        # got EXP from it (shared by damage dealt), down (e.g. 10000 -> 3) = a level-up. Unreadable: no verdict.
        if tg.points_at_engage is None:
            tg.points_at_engage = obs.exp_points
        pts, before = obs.exp_points, tg.points_at_engage
        in_reach = abs(tg.rel_dx) - tg.wide <= z.hold_max
        if self._swinging() and in_reach:
            tg.swung_at = t
        killed = pts is not None and before is not None and pts != before
        if killed and not in_reach and (tg.swung_at is None or t - tg.swung_at > tm.kill_credit_s):
            # EXP from elsewhere: a party member's kill (shared EXP) or a mob we hit earlier - not this target
            self.stats["foreign_exp"] += 1
            self._say(obs, f"EXP points {before} -> {pts} while not hitting the target (dx {tg.rel_dx:+.0f}) "
                           f"-> not our kill (party share / another mob)")
            tg.points_at_engage, killed = pts, False
        if killed:
            level_up = pts < before
            self.stats["kills"] += 1
            self.stats["level_ups"] += level_up
            self._say(obs, f"kill confirmed - EXP points {before} -> {pts}{' (LEVEL UP)' if level_up else ''} "
                           f"(#{self.stats['kills']}, HP {obs.hp:.0%})")
            tg.points_at_engage, tg.proven, tg.kill_at = pts, True, t

        if obs.target is not None:
            tg.rel_dx, tg.seen_at = cx(obs.target) - px, t
            tg.wide = max(0.0, (obs.target[2] - z.mob_width) / 2)
            if obs.target_src == "sprite":
                tg.sprite_at = t
                tg.proven = True
            tg.ground = [g for g in tg.ground if g[0] > t - 0.5] + [(t, self.odo + tg.rel_dx)]
        if obs.target_has_bar:
            tg.proven = tg.bar_seen = True
        if tg.bar_seen and not tg.learned:                         # learn looks only from an HP bar (sure)
            tg.learned = True
            acts.append(Learn())

        # the target is the one that died: its bar is gone at the kill, or fades within a moment of it
        # (sprite mode, no HP bars: EXP up and its live sprite no longer found - it plays its death animation;
        # still found = the EXP came from another mob we hit, the target fights on)
        alive = obs.target_src == "sprite" if self._sprite_mode() else obs.target_has_bar
        died = not alive and tg.kill_at is not None and t - tg.kill_at <= tm.bar_fade_s
        if died:
            if obs.dot is not None:
                self.drop_zones.append((t + tm.drop_zone_s, self._map_x(obs, tg.rel_dx)))
            others = [b for b in obs.known_mobs if abs(cx(b) - (px + tg.rel_dx)) > 25 and abs(cx(b) - px) <= z.hold_max * 1.5
                      and self._fair(obs, b, px)]
            if others:
                self.stats["chain"] += 1
                self._leave_loot(obs, tg.rel_dx, t + tm.drop_delay_s)
                return acts + self._engage(obs, min(others, key=lambda b: abs(cx(b) - px)), "target died -> next mob in reach")
            return acts + self._go_loot(obs, tg.rel_dx, "target died, nothing else in reach")

        # its death animation where it stood: stop swinging at once. EXP follows -> our kill (above, with loot);
        # none -> another player's kill: their drop, not ours to sweep (pkg_human5m: 18 x 1 s of swinging at the
        # spot + a Z sweep over their loot, in front of them)
        if obs.target_dying and tg.dying_at is None:
            tg.dying_at = t
        if tg.dying_at is not None and tg.kill_at is None:
            if t - tg.dying_at < self.hz.vary(tm.others_kill_wait_s):
                return acts + (self._release() if self.held is not None else [])
            self.stats["others_kills"] += 1
            if obs.dot is not None:
                self.drop_zones.append((t + tm.drop_zone_s, self._map_x(obs, tg.rel_dx)))   # its drops lie there
            self._phase_pause(obs)
            self._lost_one(obs)
            return acts + self._disengage(obs, "target killed by someone else (death animation, no EXP) -> moving on")

        # 5. mobs in reach outrank a target that isn't in reach (always when we're being hit)
        dist = abs(tg.rel_dx) - tg.wide                          # to its edge (a Stump is ~27 px wider than a snail)
        if dist > z.hit_max:
            # another mob must be clearly closer than the target (two mobs at the same distance = flip-flop)
            not_target = lambda b: (abs(cx(b) - (px + tg.rel_dx)) > 25            # noqa: E731
                                    and abs(cx(b) - px) < dist - z.switch_margin and self._fair(obs, b, px))
            in_path = lambda b: (cx(b) - px) * tg.rel_dx > 0 and abs(cx(b) - px) <= z.hold_max  # noqa: E731
            in_reach = [b for b in obs.known_mobs                             # in reach, or in the way
                        if (abs(cx(b) - px) <= z.hit_max or in_path(b)) and not_target(b)]
            if not in_reach and damaged:
                near = obs.known_mobs + (obs.moving or [])
                in_reach = [b for b in near if abs(cx(b) - px) <= z.hold_max and not_target(b)]
                if (not in_reach and obs.moving is None and t - self.last_damage_look > 1.5
                        and not self._sprite_mode()):
                    self.last_damage_look = t                                  # something unseen is hitting us: look
                    self.stats["looks"] += 1
                    return acts + self._release() + [Look()]
            if in_reach and t - self.last_switch < self.switch_cooldown:
                in_reach = []                                                  # just switched: settle on it first
            if in_reach:
                self.stats["reach_switches"] += 1
                self.last_switch, self.switch_cooldown = t, self.hz.vary(tm.switch_cooldown_s)
                why = "taking damage -> fighting the mob next to us" if damaged else "mob in reach -> fighting it first"
                return acts + self._release() + self._engage(obs, min(in_reach, key=lambda b: abs(cx(b) - px)), why)
            # always the closest mob (the user, perion1: "the other bots walk straight to the nearest mob and hit
            # it"; we chased far targets at dx +-560 past closer ones): any fair mob clearly closer than the target
            # we're walking to becomes the target, whichever side it's on. switch_margin + a short settle time
            # keep two mobs at about the same distance from flip-flopping.
            margin = max(z.closer_margin, z.closer_ratio * dist)          # clearly closer: no switching to and fro
            closer = [b for b in obs.known_mobs if not_target(b) and abs(cx(b) - px) < dist - margin
                      and self._pickable(obs, b, px)]
            if closer and t - self.last_switch >= self.closer_cooldown:
                pick = min(closer, key=lambda b: abs(cx(b) - px))
                self.stats["closer_switches"] += 1
                self.last_switch, self.closer_cooldown = t, self.hz.vary(tm.closer_cooldown_s)
                return acts + self._release() + self._engage(
                    obs, pick, f"closer mob at dx {cx(pick) - px:+.0f} -> switching from dx {tg.rel_dx:+.0f}")

        # 6. an unproven target has to prove it's a mob
        unproven_hit = tg.hit_since is not None and not tg.proven and t - tg.hit_since > tg.proof_s
        unproven_walk = tg.hit_since is None and not tg.proven and t - tg.engaged_at > tm.approach_proof_s
        if unproven_hit or unproven_walk:
            if obs.dot is not None:
                self.not_mobs.append((t + tm.blacklist_s, self._map_x(obs, tg.rel_dx)))
            self.stats["not_a_mob"] += 1
            how = f"hit for {tg.proof_s:.1f}s, no name/HP bar appeared" if unproven_hit else f"chased {tm.approach_proof_s:.0f}s, never proven"
            if unproven_hit and not self._sprite_mode():       # we were standing at it: it's loot -> pick it up
                return acts + [Forget()] + self._go_loot(obs, tg.rel_dx, f"not a mob - loot or scenery ({how})",
                                                         dying=False)
            if unproven_hit:                                   # sprite mode: it IS a mob - someone else's (no bar,
                self._phase_pause(obs)                         # no EXP for us): no Z sweep over their drop
                return acts + [Forget()] + self._disengage(obs, f"no HP bar for us ({how}) - someone else's mob")
            return acts + [Forget()] + self._disengage(obs, f"not a mob ({how}) -> ignored there")

        unseen = t - tg.seen_at
        hidden_ok = tm.keep_close_s if abs(tg.rel_dx) - tg.wide <= z.hit_max else tm.keep_swinging_s
        if self._sprite_mode() and tg.hit_since is not None and unseen > hidden_ok:
            # we were fighting it and its sprite is gone: it died (maybe by
            # another player's hand - no EXP for us) or left. Stop swinging; pick up what may lie there.
            self._phase_pause(obs)                     # no EXP: not our kill, its drop (if any) isn't ours
            self._lost_one(obs)
            return acts + self._disengage(obs, "target gone (died or left), no EXP for us -> not looting there")
        if tg.hit_since is not None and unseen > tm.blind_max_s:
            return acts + self._disengage(obs, f"gave up - target unseen {unseen:.1f}s", "gave_up")
        if tg.hit_since is None and unseen > tm.lost_before_reach_s:
            self._lost_one(obs)
            return acts + self._disengage(obs, f"lost target before reaching it (dx {tg.rel_dx:+.0f})", "lost")
        if t - tg.engaged_at > tm.engage_timeout_s:
            return acts + self._disengage(obs, "timeout on this target", "timeouts")

        # 7. fight by distance zone - only on a fresh sighting
        direction = "left" if tg.rel_dx < 0 else "right"
        away = "right" if direction == "left" else "left"
        if unseen > tm.fresh_s:
            if tg.hit_since is not None and unseen < hidden_ok:
                return acts + self._hold(self.attack_key)            # mid-fight, lost sight briefly: keep swinging
            if tg.hit_since is None and not damaged:
                # missed for a moment on the way in: a player doesn't stop - walk on to where it should be
                # (pkg_idle1: stood ~0.7 s each time, then 'lost target before reaching it')
                if self.held == direction:
                    tg.rel_dx -= self.moved                         # dead reckoning: we came closer
                    if abs(tg.rel_dx) - tg.wide > z.walk_release and self._allowed(obs, direction, slack=cfg.safety.leash_margin):
                        return acts + self._hold(direction)
                if abs(tg.rel_dx) - tg.wide <= z.hit_max:           # it was in reach (hidden behind us): swing there
                    return acts + self._turn(direction) + self._hold(self.attack_key)
            return acts + self._release()                           # no step-backs / steps on an old position

        if obs.target is not None and obs.me is not None:
            tg.below = bottom(obs.target) - obs.me[1] > z.same_level
        if tg.below and self._allowed(obs, direction):        # on lower ground: a swing passes over its head
            if self.held != direction:
                self._say(obs, f"target on lower ground (dx {tg.rel_dx:+.0f}) -> stepping down to it")
            return acts + self._hold(direction)
        if t < self.back_settle_until:                       # just stepped back: a beat, then turn and fight
            return acts
        if dist < z.contact and t - self.last_back_off > self.back_cooldown and self._allowed(obs, away):
            self.last_back_off, self.back_cooldown = t, self.hz.vary(tm.back_cooldown_s)
            if self.hz.chance(tm.back_skip_p):               # not every time: sometimes a player just keeps hitting
                self._say(obs, f"too close (dx {tg.rel_dx:+.0f}) -> keep swinging this time")
            else:
                self.stats["back_offs"] += 1
                self._say(obs, f"too close (dx {tg.rel_dx:+.0f}) -> step back")
                self.facing = away
                self.back_settle_until = t + self.hz.between(tm.back_settle_min_s, tm.back_settle_max_s)
                return acts + self._release() + [Tap(away, self.hz.between(tm.back_min_s, tm.back_max_s))]
        if dist <= z.hit_max:                                    # (also: too close again right after a step back)
            if tg.hit_since is None:
                tg.hit_since = t
                self._say(obs, f"in reach (dx {tg.rel_dx:+.0f}) -> hitting")
            tg.hold_since = None
            return acts + self._turn(direction) + self._hold(self.attack_key)
        attack = self.attack_key
        coming = self._approach(tg)                          # px/s it walks toward us (0: still / going away)
        lead = coming * tm.anticipate_s                      # it covers this much while our swing comes out
        if coming and dist <= z.hit_max + lead and self.held not in ("left", "right"):
            tg.hold_since = None                             # it walks into the swing: start swinging now
            return acts + self._turn(direction) + self._hold(attack)
        if dist <= z.walk_release + lead and (self.held == direction or self._swinging()):
            # walking in: attack now - the swing stops the walk and the slide carries us into reach (the user:
            # "seamlessly walk to it and hit"; pkg_sprites3 stood 0.7-1.6 s at ~90 px and got face-tanked)
            if self.held == direction:
                tg.swing_out_since = t
            elif tg.swing_out_since is None:
                tg.swing_out_since = t
            elif t - tg.swing_out_since > tg.swing_out_wait and self._allowed(obs, direction):
                tg.swing_out_since, tg.swing_out_wait = t, self.hz.vary(tm.swing_out_s)    # slid short: step in
                self.stats["short_steps"] += 1
                return acts + self._release() + [Tap(direction, tm.step_s)] + self._hold(attack)
            return acts + self._hold(attack)
        tg.swing_out_since = None
        if dist <= z.hold_max and coming >= tm.wait_for_s_min:   # it's charging: face it and let it come
            if self.held is not None:
                acts += self._release()
            return acts + self._turn(direction)
        measuring = self._fighting_us(obs, tg) and not self._speed_known(tg)   # does it charge? (~0.2 s)
        if dist <= z.hold_max and not measuring and self._allowed(obs, direction):
            return acts + self._hold(direction)                  # just out of reach: walk in, no waiting
            # (pkg_idle1: 6 of 9 stops were 0.4-0.8 s waits here after a step back, then a step)
        if dist <= z.hold_max:
            acts += self._turn(direction)
            if self.held is not None:
                acts += self._release()
            if tg.hold_since is None:
                tg.hold_since, tg.hold_wait = t, self.hz.vary(tm.wait_in_hold_s)
            elif t - tg.hold_since > tg.hold_wait and self._allowed(obs, direction):
                self.stats["short_steps"] += 1
                tg.hold_since, tg.hold_wait = t, self.hz.vary(tm.wait_in_hold_s)
                acts.append(Tap(direction, tm.step_s))
            return acts
        tg.hold_since = None
        if not self._allowed(obs, direction, slack=cfg.safety.leash_margin):
            if self._fighting_us(obs, tg) and dist <= z.hold_max * 2:     # it fights us and comes our way: wait
                return acts + self._turn(direction) + self._release()
            return acts + self._disengage(obs, "target is past the leash / an obstacle")
        if dist > z.walk_release:
            return acts + self._hold(direction)
        return acts + self._release()
