"""Brain scenarios with hand-made observations and a fake clock. Each one is a behaviour seen (or wanted) live."""
import pytest

from maplebrain.brain.actions import Forget, Hold, Learn, Look, Release, Stop, Tap, Track, Untrack
from maplebrain.brain.brain import Brain
from maplebrain.config import Config
from maplebrain.perception.perceiver import Observation

ATTACK = Config().keys.attack
BASIC, PICKUP = Config().keys.basic_attack, Config().keys.pickup
HP_POTION, MP_POTION = Config().keys.hp_potion, Config().keys.mp_potion
PX, FEET = 680.0, 579.0


def mob(dx, w=35, h=50):
    """A mob box whose centre is dx px from us, standing on our ground line."""
    return (int(PX + dx - w / 2), int(FEET - h), w, h)


def obs(t, *, me=True, hp=1.0, hp_raw=None, exp=0.20, dot=(100.0, 90.0), bar=(), lib=(), target=None,
        target_bar=False, moving=None, align=0.95, scene_dx=0.0):
    o = Observation(t=t, me=(PX, FEET) if me else None, hp=hp, hp_raw=hp if hp_raw is None else hp_raw,
                    exp_points=round(exp * 10000),         # scenarios give EXP as a share; the brain sees points
                    dot=dot, bar_mobs=list(bar), known_mobs=list(bar) + list(lib), target=target,
                    target_src="bar" if target_bar else ("track" if target else "none"), target_has_bar=target_bar,
                    moving=moving, look_align=align if moving is not None else None, scene_dx=scene_dx)
    return o


def kinds(actions):
    return [type(a).__name__ for a in actions]


def engaged(brain, t, box, **kw):
    """Put the brain in ENGAGE on `box` (seen via a look)."""
    acts = brain.step(obs(t, moving=[box], **kw))
    assert any(isinstance(a, Track) for a in acts)
    return acts


@pytest.fixture(params=["exact", 1, 2, 3])
def brain(request):
    """Each scenario runs once with fixed timings and with randomized timings (3 fixed seeds: reproducible)."""
    cfg = Config()
    if request.param == "exact":
        cfg.humanize.jitter = 0.0
    else:
        cfg.humanize.seed = request.param
    return Brain(cfg)


def longest(brain, secs):
    """The longest a randomized wait of nominal `secs` can be."""
    return secs * (1 + brain.cfg.humanize.jitter)


# ---------------------------------------------------------------- safety
def test_low_hp_stops(brain):
    acts = brain.step(obs(0, hp=0.40))
    assert isinstance(acts[-1], Stop)


def test_seek_with_nothing_known_asks_for_a_look(brain):
    assert kinds(brain.step(obs(0))) == ["Release", "Look"]


# ---------------------------------------------------------------- fighting
def test_walks_to_far_target_then_hits_without_stopping_first(brain):
    """The user (pkg_sprites3): 'hesitant before hitting a target upon reaching it, causing face tanking again,
    it should seamlessly walk to it and hit'. The swing ends the walk; the slide carries us into reach."""
    engaged(brain, 0.0, mob(-300))
    assert brain.step(obs(0.1, target=mob(-300)))[-1] == Hold("left")       # far: walk
    assert brain.step(obs(0.2, target=mob(-70)))[-1] == Hold(ATTACK)      # at the release point: attack
    acts = brain.step(obs(0.3, target=mob(-60)))
    assert acts[-1] == Hold(ATTACK) and Release() not in acts             # (slid into reach) keep attacking


def test_standing_just_out_of_reach_walks_in_at_once(brain):
    """pkg_sprites3 66.0s: stopped at dx -91 and waited 1.6 s in the 'hold zone'; the snail walked into us."""
    engaged(brain, 0.0, mob(-88))
    acts = brain.step(obs(0.1, target=mob(-88)))
    assert acts[-1] == Hold("left")


def test_swinging_from_just_outside_reach_steps_in(brain):
    engaged(brain, 0.0, mob(-300))
    brain.step(obs(0.1, target=mob(-300)))
    t, acts = 0.2, []
    while t < 1.2:                                       # the slide fell short: the snail stays at -72
        acts += brain.step(obs(t, target=mob(-72)))
        t += 0.05
    assert Tap("left", brain.cfg.timing.step_s) in acts
    assert acts[-1] == Hold(ATTACK)


def back_steps(brain, acts, key="left"):
    tm = brain.cfg.timing
    return [a for a in acts if isinstance(a, Tap) and a.key == key and tm.back_min_s <= a.secs <= tm.back_max_s]


def test_contact_range_steps_back_but_hit_zone_edge_does_not(brain):
    brain.cfg.timing.back_skip_p = 0.0
    engaged(brain, 0.0, mob(60))
    assert brain.step(obs(0.1, target=mob(45)))[-1] == Hold(ATTACK)        # 45px: hit, don't dance (was 50px)
    acts = brain.step(obs(0.2, target=mob(30)))
    assert back_steps(brain, acts)                                           # 30px: contact -> step away


def flips(acts):
    """Direction changes in a sequence of actions (each one is a visible turn of the character)."""
    dirs = [a.key for a in acts if isinstance(a, (Tap, Hold)) and a.key in ("left", "right")]
    return sum(1 for a, b in zip(dirs, dirs[1:]) if a != b)


def test_too_close_steps_back_once_then_fights_instead_of_dancing(brain):
    """pkg_loot1 86-88s: 'too close -> step back' every tick = left-right-left-right 7 times, never attacking.
    The 0.1s tap moved ~5px and the snail followed. (No HP was lost at dx 34-41.)"""
    brain.cfg.timing.back_skip_p = 0.0
    engaged(brain, 0.0, mob(60))
    brain.step(obs(0.1, target=mob(60), target_bar=True))
    seen, t = [], 0.2
    while t < 1.2:                                                           # the snail stays on top of us
        seen += brain.step(obs(t, target=mob(38), target_bar=True))
        t += 0.1
    steps = [a for a in seen if isinstance(a, Tap) and a.key == "left"]
    assert len(steps) == 1 and steps[0].secs >= 0.24                         # one real step, not a twitch
    assert flips(seen) <= 2                                                  # step away, turn back: that's all
    assert seen[-1] == Hold(ATTACK)                                         # then stand and fight


def test_steps_back_again_after_the_cooldown(brain):
    brain.cfg.timing.back_skip_p = 0.0
    engaged(brain, 0.0, mob(60))
    brain.step(obs(0.1, target=mob(38), target_bar=True))
    acts = brain.step(obs(0.1 + longest(brain, brain.cfg.timing.back_cooldown_s) + 0.05, target=mob(38), target_bar=True))
    assert any(isinstance(a, Tap) and a.key == "left" for a in acts)


def test_never_moves_on_a_stale_target_position_while_being_hit(brain):
    """hunt6b: stepped back 14x on a target last seen 3s earlier while snails hit us."""
    engaged(brain, 0.0, mob(-120))
    brain.step(obs(0.1, target=mob(-120)))
    hp = 1.0
    for t in (0.5, 0.8, 1.0):                                               # target not seen since 0.1
        hp -= 0.02
        acts = brain.step(obs(t, hp=hp))
        assert not any(isinstance(a, (Tap, Hold)) and a.key in ("left", "right") for a in acts)


def test_a_target_long_unseen_is_not_walked_to(brain):
    engaged(brain, 0.0, mob(-300))
    brain.step(obs(0.1, target=mob(-300)))
    acts = brain.step(obs(0.1 + brain.cfg.timing.lost_before_reach_s + 0.1))
    assert not any(isinstance(a, (Tap, Hold)) for a in acts)


def test_a_target_missed_on_the_way_in_is_walked_to_without_stopping(brain):
    """The user (session 5): 'A human usually doesn't stop on the way to target.' pkg_idle1 12.8 s: the sprite was
    missed for a few frames mid-approach -> stood 0.7 s -> 'lost target before reaching it'."""
    engaged(brain, 0.0, mob(-300))
    acts = brain.step(obs(0.1, target=mob(-300)))
    t = 0.15
    while t < 0.9:                                                          # unseen; we walk ~6 px per tick
        acts += brain.step(obs(t, scene_dx=6.0))                           # (camera follows: we moved left)
        t += 0.05
    assert Release() not in acts and Hold("left") in acts and acts[-1] == Hold("left")
    acts = brain.step(obs(0.95, target=mob(-180)))                          # seen again: still walking in
    assert acts[-1] == Hold("left") and Release() not in acts


def test_a_missed_target_stops_the_walk_where_it_should_be(brain):
    """Dead reckoning: walking blind toward it, we stop at the release point, not past it."""
    engaged(brain, 0.0, mob(-120))
    brain.step(obs(0.1, target=mob(-120)))
    t, last = 0.15, None
    while t < 0.9:
        last = brain.step(obs(t, scene_dx=8.0))
        t += 0.05
    assert last[-1] != Hold("left")


def test_far_walk_in_is_one_continuous_hold_until_the_hit(brain):
    """acquire -> walk straight in -> hit: one Hold, no Release or pause until the swing."""
    engaged(brain, 0.0, mob(-400))
    acts, dx, t = [], -400.0, 0.1
    while dx < -50:
        a = brain.step(obs(t, target=mob(dx), scene_dx=6.0 if dx < -76 else 0.0, dot=(100.0 + dx / 15, 90.0)))
        acts += a
        if Hold(ATTACK) in a:
            break
        dx += 6.0
        t += 0.05
    keys = [a for a in acts if isinstance(a, (Hold, Release, Tap))]
    assert keys[-1] == Hold(ATTACK)
    assert all(k == Hold("left") for k in keys[:-1])                         # nothing but walking before it


def test_mid_fight_brief_loss_keeps_swinging(brain):
    engaged(brain, 0.0, mob(55))
    brain.step(obs(0.1, target=mob(55), target_bar=True))
    assert brain.step(obs(0.5))[-1] == Hold(ATTACK)                        # lost sight 0.4s: keep swinging


# ---------------------------------------------------------------- proof of mob
def test_hitting_something_with_no_hp_bar_is_not_a_mob(brain):
    """hunt6b: hit 'air next to a ladder' for 14s."""
    engaged(brain, 0.0, mob(60))
    t, seen = 0.1, []
    while brain.mode == "ENGAGE" and t < 2.5:
        seen += brain.step(obs(t, target=mob(60)))
        t += 0.1
    assert any(isinstance(a, Forget) for a in seen) and brain.mode == "LOOT"   # we were at it: pick it up
    _loot_walk(brain, t)
    assert brain.stats["not_a_mob"] == 1
    S = brain.cfg.perception.screen_per_minimap
    acts = brain.step(obs(t + 0.1, moving=[mob(0)], dot=(100.0 + 60 / S, 90.0)))   # same spot offered again
    assert not any(isinstance(a, Track) for a in acts)                      # briefly ignored


def test_unproven_target_chased_too_long_is_dropped(brain):
    """hunt6c: obsessed with a dead player's ghost, never reached it."""
    engaged(brain, 0.0, mob(-400))
    t = 0.1
    while brain.mode == "ENGAGE" and t < 10:
        brain.step(obs(t, target=mob(-400), dot=(100.0 - t, 90.0)))        # we walk freely; it keeps moving away
        t += 0.1
    assert brain.mode == "SEEK" and brain.stats["not_a_mob"] == 1 and t < 7


def test_proven_target_is_learned_once(brain):
    engaged(brain, 0.0, mob(55))
    a1 = brain.step(obs(0.1, target=mob(55), target_bar=True))
    a2 = brain.step(obs(0.2, target=mob(55), target_bar=True))
    assert kinds(a1).count("Learn") == 1 and "Learn" not in kinds(a2)


def test_learns_only_confirmed_mobs(brain):
    engaged(brain, 0.0, mob(55))
    acts = brain.step(obs(0.1, target=mob(55)))                             # no bar, no EXP yet
    assert not any(isinstance(a, Learn) for a in acts)


def test_exp_kill_without_ever_seeing_an_hp_bar_does_not_learn_the_target(brain):
    """pkg_swing1: grass got learned as a mob - EXP from another mob's death 'proved' a wrongly tracked target."""
    engaged(brain, 0.0, mob(55))
    acts = brain.step(obs(0.1, target=mob(55))) + brain.step(obs(0.2, exp=0.25, target=mob(55)))
    assert not any(isinstance(a, Learn) for a in acts)


def test_known_not_a_mob_does_not_pull_us_back_from_looting(brain):
    """pkg_swing1: hit grass 1.2s -> 'not a mob, loot it' -> LOOT saw the grass (a library match) 'in reach'
    -> fought it again: 33 times in a row."""
    grass = mob(62)
    engaged(brain, 0.0, grass)
    t = 0.1
    while brain.mode == "ENGAGE":
        brain.step(obs(t, target=grass))
        t += 0.1
    assert brain.mode == "LOOT"
    acts = brain.step(obs(t, lib=[grass]))
    assert brain.mode == "LOOT" and not any(isinstance(a, Track) for a in acts)


def test_known_not_a_mob_is_not_switched_to_mid_fight(brain):
    engaged(brain, 0.0, mob(62))
    t = 0.1
    while brain.mode == "ENGAGE":
        brain.step(obs(t, target=mob(62)))
        t += 0.1
    brain.mode, brain.target = "SEEK", None
    engaged(brain, t, mob(-300))
    acts = brain.step(obs(t + 0.1, target=mob(-300), hp=0.9, lib=[mob(62)]))   # hurt; the grass is "near"
    assert not any(isinstance(a, Track) for a in acts)


def test_a_mob_with_an_hp_bar_is_fought_even_where_something_was_blacklisted(brain):
    engaged(brain, 0.0, mob(62))
    t = 0.1
    while brain.mode == "ENGAGE":
        brain.step(obs(t, target=mob(62)))
        t += 0.1
    acts = brain.step(obs(t, bar=[mob(62)]))
    assert Track(mob(62)) in acts


# ---------------------------------------------------------------- kills
def test_kill_with_nothing_else_around_goes_looting(brain):
    engaged(brain, 0.0, mob(55))
    brain.step(obs(0.1, target=mob(55), target_bar=True))
    acts = brain.step(obs(0.2, exp=0.25))                                   # EXP up, target's bar gone
    assert brain.stats["kills"] == 1 and brain.mode == "LOOT" and any(isinstance(a, Untrack) for a in acts)


@pytest.mark.loot_off
def test_loot_off_by_default_a_kill_goes_straight_back_to_seek(brain):
    """Session 13: a pet picks up the drops - no LOOT mode, no Z, nothing remembered to come back for."""
    assert brain.cfg.perception.loot is False
    engaged(brain, 0.0, mob(55))
    brain.step(obs(0.1, target=mob(55), target_bar=True))
    acts = brain.step(obs(0.2, exp=0.25))
    assert brain.stats["kills"] == 1 and brain.mode == "SEEK" and any(isinstance(a, Untrack) for a in acts)
    t, seen = 0.3, []
    while t < 3.0:
        seen += brain.step(obs(t))
        t += 0.1
    assert brain.mode != "LOOT" and not any(isinstance(a, Tap) and a.key == PICKUP for a in seen)


@pytest.mark.loot_off
def test_loot_off_a_chain_kill_leaves_nothing_to_come_back_for(brain):
    engaged(brain, 0.0, mob(55))
    brain.step(obs(0.1, target=mob(55), target_bar=True, bar=[mob(-70)]))
    brain.step(obs(0.2, exp=0.25, bar=[mob(-70)]))
    assert brain.stats["kills"] == 1 and brain.pending_loot == []


@pytest.mark.loot_off
def test_loot_off_overrides_loot_by_sight(lbrain):
    assert not lbrain._sight()


def test_kill_chains_straight_to_the_next_mob_in_reach(brain):
    engaged(brain, 0.0, mob(55))
    brain.step(obs(0.1, target=mob(55), target_bar=True))
    other = mob(-80)
    acts = brain.step(obs(0.2, exp=0.25, bar=[other]))
    assert brain.mode == "ENGAGE" and Track(other) in acts and brain.stats["chain"] == 1


def test_exp_from_another_mob_does_not_drop_our_target(brain):
    engaged(brain, 0.0, mob(55))
    brain.step(obs(0.1, target=mob(55), target_bar=True))
    acts = brain.step(obs(0.2, exp=0.25, target=mob(55), target_bar=True, bar=[mob(55)]))
    assert brain.mode == "ENGAGE" and not any(isinstance(a, Untrack) for a in acts)


def _old_drop_zone_test_replaced_by_looting(brain):
    """hunt5: went for the spinning mesos the snail dropped."""
    engaged(brain, 0.0, mob(55))
    brain.step(obs(0.1, target=mob(55), target_bar=True))
    brain.step(obs(0.2, exp=0.25))                                          # killed at dx +55
    acts = brain.step(obs(0.3, exp=0.25, moving=[mob(58, w=40, h=30)]))     # something moving right there
    assert not any(isinstance(a, Track) for a in acts)


# ---------------------------------------------------------------- priorities
def test_mob_in_reach_beats_a_far_target(brain):
    engaged(brain, 0.0, mob(-300))
    near = mob(50)
    acts = brain.step(obs(0.1, target=mob(-300), bar=[near]))
    assert Track(near) in acts and brain.stats["reach_switches"] == 1


def test_taking_damage_turns_us_on_the_mob_next_to_us(brain):
    """hunt6c: walked toward a far target while snails next to us chipped our HP."""
    engaged(brain, 0.0, mob(-300))
    brain.step(obs(0.1, target=mob(-300), hp=1.0))
    biter = mob(80)                                                          # outside hit range but close
    acts = brain.step(obs(0.2, target=mob(-290), hp=0.97, bar=[biter]))
    assert Track(biter) in acts


def test_taking_damage_between_two_mobs_does_not_flip_flop(brain):
    """pkg_human3 59.85s: snails at -88 and +88, being hit -> switched target 4x in 0.85s, turning each time."""
    left, right = mob(-88), mob(88)
    engaged(brain, 0.0, right)
    seen, t, hp = [], 0.1, 1.0
    while t < 1.5:
        hp -= 0.01                                                           # chipped all along
        tgt = right if brain.target.rel_dx > 0 else left
        dot = (100.0 + t, 90.0)                                              # (we may walk in: not a wall)
        seen += brain.step(obs(t, target=tgt, target_bar=True, hp=hp, bar=[left, right], dot=dot))
        t += 0.05
    assert sum(isinstance(a, Track) for a in seen) <= 1
    assert flips(seen) <= 2


def test_a_mob_in_our_path_becomes_the_target(brain):
    """pkg_human3 71s: walking to a snail at -191, walked into another at -87 (knocked back, lost both)."""
    engaged(brain, 0.0, mob(-300))
    brain.step(obs(0.1, target=mob(-191)))
    in_path = mob(-87)
    acts = brain.step(obs(0.2, target=mob(-186), lib=[in_path]))
    assert Track(in_path) in acts


def test_a_clearly_closer_mob_behind_us_becomes_the_target(brain):
    """The user (perion1): always the closest mob, whichever side (was: a mob behind us didn't distract)."""
    engaged(brain, 0.0, mob(-300))
    brain.step(obs(0.1, target=mob(-191)))
    acts = brain.step(obs(0.2, target=mob(-186), lib=[mob(120)]))
    assert Track(mob(120)) in acts and brain.stats["closer_switches"] == 1


def test_a_new_closer_mob_takes_over_from_a_far_target(brain):
    """perion1: walked to targets at dx +-560 while mobs spawned much closer ('indecisive targeting')."""
    engaged(brain, 0.0, mob(-500))
    brain.step(obs(0.1, target=mob(-500)))
    near = mob(-200)
    acts = brain.step(obs(0.2, target=mob(-495), lib=[near]))
    assert Track(near) in acts and brain.target.rel_dx == pytest.approx(-200, abs=1)


def test_a_mob_only_slightly_closer_does_not_take_over(brain):
    engaged(brain, 0.0, mob(-300))
    brain.step(obs(0.1, target=mob(-300)))
    acts = brain.step(obs(0.2, target=mob(-295), lib=[mob(285)]))           # 10 px closer: within the margin
    assert not any(isinstance(a, Track) for a in acts)


def test_closest_switching_does_not_flip_flop(brain):
    """Two mobs whose distances cross each other: at most one switch per settle time, never back and forth."""
    engaged(brain, 0.0, mob(-300))
    seen, t = [], 0.1
    while t < 2.0:
        a, b = mob(-300 + 40 * t), mob(260 - 40 * t)                         # both approach us
        tgt = a if brain.target is not None and brain.target.rel_dx < 0 else b
        seen += brain.step(obs(t, target=tgt, lib=[a, b], dot=(100.0 + t, 90.0)))
        if brain.mode != "ENGAGE":
            break
        t += 0.05
    assert sum(isinstance(x, Track) for x in seen) <= 1


def test_a_closer_mob_past_a_wall_is_not_switched_to(brain):
    engaged(brain, 0.0, mob(-400))
    brain.blocked["right"] = 100.0                                           # a wall on the right
    brain.step(obs(0.1, target=mob(-400)))
    acts = brain.step(obs(0.2, target=mob(-395), lib=[mob(200)]))
    assert not any(isinstance(a, Track) for a in acts)


def test_a_target_in_reach_is_not_dropped_for_a_closer_one(brain):
    engaged(brain, 0.0, mob(60))
    brain.step(obs(0.1, target=mob(60), target_bar=True))
    acts = brain.step(obs(0.2, target=mob(60), target_bar=True, lib=[mob(-40)]))
    assert not any(isinstance(a, Track) for a in acts)


def test_taking_damage_still_switches_to_a_clearly_closer_mob(brain):
    engaged(brain, 0.0, mob(-300))
    brain.step(obs(0.1, target=mob(-300), hp=1.0))
    acts = brain.step(obs(0.2, target=mob(-290), hp=0.97, bar=[mob(80)]))
    assert Track(mob(80)) in acts


def _after_unseen_hit(brain, t0, knock=0.0, until=None, walk=6.0, hp=0.97, **kw):
    """We're hit at t0 by something we can't see and knocked `knock` px over 0.3 s (no key held, camera follows);
    afterwards we move `walk` px per tick in whichever way the brain holds. Returns (actions, swings) where a
    swing is (our position relative to where we were hit, facing) for every tick spent holding attack."""
    until = t0 + 2.0 if until is None else until
    pos, held, seen, swings, t = 0.0, None, [], [], t0
    while t < until:
        move = knock / 6 if t0 < t <= t0 + 0.3 else 0.0
        move += walk if held == "right" else -walk if held == "left" else 0.0
        pos += move
        acts = brain.step(obs(t, hp=hp, moving=[], scene_dx=-move, **kw))
        for a in acts:
            if isinstance(a, Hold):
                held = a.key if a.key in ("left", "right") else None
                if a.key == ATTACK:
                    swings.append((pos, brain.facing))
            elif isinstance(a, Release) or (isinstance(a, Tap) and a.key in ("left", "right")):
                held = None
        seen += acts
        t += 0.05
    return seen, swings


@pytest.mark.parametrize("knock", [80, -80, 60, -95])
def test_knocked_back_goes_back_to_where_it_was_hit_and_swings_there(brain, knock):
    """pkg_sweep1/pkg_swing1: snails standing still (invisible to us) hit us; the knockback threw us 50-95 px,
    either way. The snail stays where we were hit: walk back so that spot is in reach, face it, swing."""
    brain.facing = "right" if knock > 0 else "left"                        # facing away from it, like live
    brain.step(obs(0.0, hp=1.0))
    _, swings = _after_unseen_hit(brain, 0.05, knock=knock)
    assert swings, "never swung"
    toward = "left" if knock > 0 else "right"
    for pos, facing in swings:
        assert facing == toward
        assert 25 <= abs(pos) <= brain.cfg.zones.hit_max, f"swung from {pos:+.0f} px of the hit spot"


def test_hit_without_being_moved_swings_both_sides(brain):
    """The snail is right on top of us (no knockback measured): swing one side, then the other."""
    brain.facing = "right"
    brain.step(obs(0.0, hp=1.0))
    _, swings = _after_unseen_hit(brain, 0.05, knock=0.0, until=1.6)
    assert {f for _, f in swings} == {"left", "right"}


def test_hit_without_being_moved_right_after_walking_swings_behind_us_first(brain):
    """pkg_swing1 11.1s: walked right straight past a snail standing still; it was behind us."""
    engaged(brain, 0.0, mob(400))
    for i in range(5):
        brain.step(obs(0.1 + i * 0.05, target=mob(400 - 5 * i), dot=(100.0 + i * 0.5, 90.0)))   # walking right
    brain.mode, brain.target = "SEEK", None
    _, swings = _after_unseen_hit(brain, 0.4, knock=0.0, until=1.0)
    assert swings and swings[0][1] == "left"


def test_a_blind_swing_that_reveals_the_mob_fights_it(brain):
    brain.facing = "left"
    brain.step(obs(0.0, hp=1.0))
    _after_unseen_hit(brain, 0.05, knock=0.0, until=0.6)
    biter = mob(-20, w=40, h=26)
    acts = brain.step(obs(0.6, hp=0.97, bar=[biter]))                       # our swing hit it: HP bar shows
    assert Track(biter) in acts and brain.mode == "ENGAGE"


def test_a_mob_next_to_us_is_fought_even_in_an_avoided_direction(brain):
    """pkg_recover1 64.2s: the swing revealed a snail at +60 (HP bar), but 'right' was avoided for 15s after a
    wall -> patrolled left, away from it. Avoiding a direction is about walking; this needs no walk."""
    brain.blocked["right"] = 100.0
    biter = mob(60)
    acts = brain.step(obs(1.0, bar=[biter]))
    assert Track(biter) in acts


def test_a_mob_fighting_us_in_an_avoided_direction_is_waited_for_not_dropped(brain):
    """pkg_sprites1 35-40s: 'left' avoided after a wall; a Blue Snail with its HP bar sat at dx -100..-150 and came
    at us. The bot dropped it 3 times ('past the leash / an obstacle') while it hit us 100 -> 93 %.
    A mob with an HP bar comes to us: face it and wait instead of walking or leaving."""
    brain.blocked["left"] = 100.0
    biter = mob(-60)
    assert Track(biter) in brain.step(obs(1.0, bar=[biter]))
    for i, dx in enumerate((-110, -140, -130, -120)):
        acts = brain.step(obs(1.1 + i * 0.1, bar=[mob(dx)], target=mob(dx), target_bar=True))
        assert brain.mode == "ENGAGE", dx
        assert Hold("left") not in acts                                     # no walking into the avoided side
    assert brain.facing == "left"


def test_a_mob_fighting_us_slightly_past_reach_is_picked_in_an_avoided_direction(brain):
    brain.blocked["left"] = 100.0
    biter = mob(-130)
    assert Track(biter) in brain.step(obs(1.0, bar=[biter]))


def test_a_far_mob_in_an_avoided_direction_is_still_ignored(brain):
    brain.blocked["right"] = 100.0
    acts = brain.step(obs(1.0, moving=[mob(300)]))
    assert not any(isinstance(a, Track) for a in acts)


def test_no_damage_no_blind_swinging(brain):
    acts = brain.step(obs(0.0)) + brain.step(obs(0.1, moving=[]))
    assert Hold(ATTACK) not in acts


def test_hit_by_something_unseen_while_looting_stops_and_swings(brain):
    _kill_at(brain, 60)
    brain.step(obs(0.25, exp=0.25, hp=1.0))
    brain.step(obs(0.3, exp=0.25, hp=0.96))
    assert brain.mode == "SEEK" and brain.pending_loot
    _, swings = _after_unseen_hit(brain, 0.35, knock=0.0, hp=0.96, exp=0.25)
    assert swings


def test_taking_damage_from_something_unseen_triggers_a_look(brain):
    engaged(brain, 0.0, mob(-300))
    brain.step(obs(0.1, target=mob(-300), hp=1.0))
    acts = brain.step(obs(0.2, target=mob(-290), hp=0.97))
    assert kinds(acts)[-1] == "Look"
    acts = brain.step(obs(0.25, target=mob(-290), hp=0.97, moving=[mob(70, w=42, h=26)]))
    assert any(isinstance(a, Track) for a in acts)                           # fights the unseen biter


# ---------------------------------------------------------------- movement troubles
def test_blocked_walking_avoids_that_direction(brain):
    engaged(brain, 0.0, mob(-300))
    t = 0.1
    while brain.mode == "ENGAGE" and t < 3:
        brain.step(obs(t, target=mob(-300), dot=(100.0, 90.0)))             # walking left, dot frozen
        t += 0.1
    assert brain.mode == "SEEK" and brain.stats["blocked"] == 1
    acts = brain.step(obs(t, moving=[mob(-150)]))
    assert not any(isinstance(a, Track) for a in acts)                      # left is avoided for a while


def _old_patrol_alternation_replaced_by_sweep(brain):
    """hunt6e: 'patrol right' every 0.67s, walked off its area."""
    patrols, t = [], 0.0
    for _ in range(12):
        brain.step(obs(t)); t += 0.1                                         # asks for a look
        acts = brain.step(obs(t, moving=[])); t += 0.1                       # look found nothing
        patrols += [a.key for a in acts if isinstance(a, Tap)]
    assert patrols == ["left", "right", "left", "right"]                     # one patrol per 3 empty looks


def test_hidden_behind_scenery_backs_out_the_way_it_came(brain):
    engaged(brain, 0.0, mob(-300))
    brain.step(obs(0.1, target=mob(-300), dot=(100.0, 90.0)))                # walking left
    brain.step(obs(0.2, target=mob(-290), dot=(99.0, 90.0)))
    acts = brain.step(obs(1.0, me=False))
    assert Tap("right", 0.25) in acts


def test_after_backing_out_of_a_hiding_spot_that_side_is_avoided_only_briefly(sbrain):
    """pkg_sprites3 19.8s: the tag hid behind a bridge rail; after backing out, 'left' was silently avoided for
    15 s - we walked away from the snails there, and with the right side avoided too we stood still 10 s."""
    b = sbrain
    assert Track(mob(-300)) in b.step(obs(0.0, lib=[mob(-300)]))
    b.step(obs(0.1, target=mob(-300), dot=(100.0, 90.0)))                    # walking left
    b.step(obs(0.2, target=mob(-290), dot=(99.0, 90.0)))
    b.step(obs(1.0, me=False))                                              # hidden -> back out
    b.step(obs(1.5, target=mob(-280)))                                      # found again
    assert any("avoiding left" in e for e in b.events)
    assert b.blocked["left"] <= 1.5 + 3.0 * (1 + b.cfg.humanize.jitter) + 1e-6
    b.mode, b.target = "SEEK", None
    acts = b.step(obs(6.0, lib=[mob(-400)], dot=(99.0, 90.0)))
    assert Track(mob(-400)) in acts                                         # a few seconds later: left is fine


def test_loot_stays_ignored_after_we_walk_away_and_come_back(brain):
    """pkg run: hit the snail shells a dead snail dropped (zones were relative to where we stood)."""
    S = brain.cfg.perception.screen_per_minimap
    engaged(brain, 0.0, mob(60), dot=(100.0, 90.0))
    brain.step(obs(0.1, target=mob(60), target_bar=True, dot=(100.0, 90.0)))
    brain.step(obs(0.2, exp=0.25, dot=(100.0, 90.0)))                       # killed at map x = 100*S + 60
    # we're now 10 minimap px to the left: the same loot is 10*S further right on screen
    acts = brain.step(obs(0.3, exp=0.25, dot=(90.0, 90.0), moving=[mob(60 + 10 * S, w=40, h=30)]))
    assert not any(isinstance(a, Track) for a in acts)


def test_hit_loot_is_ignored_from_anywhere_afterwards(brain):
    S = brain.cfg.perception.screen_per_minimap
    engaged(brain, 0.0, mob(62), dot=(100.0, 90.0))
    t = 0.1
    while brain.mode == "ENGAGE":                                           # no name/bar ever appears
        brain.step(obs(t, target=mob(62), dot=(100.0, 90.0)))
        t += 0.1
    assert brain.stats["not_a_mob"] == 1 and t < longest(brain, brain.cfg.timing.proof_s) + 0.4   # proven loot ~1.2s after the first hit
    assert brain.mode == "LOOT"
    _, t = _loot_walk(brain, t)                                             # pick it up first
    assert brain.mode == "SEEK" and t < 6
    acts = brain.step(obs(t, moving=[mob(62 - 5 * S)], dot=(105.0, 90.0)))   # same thing, seen from elsewhere
    assert not any(isinstance(a, Track) for a in acts)
    acts = brain.step(obs(t + 0.1, moving=[mob(62)], dot=(105.0, 90.0)))      # a different spot: fair game
    assert any(isinstance(a, Track) for a in acts)


# ---------------------------------------------------------------- looting (pkg_015848: loot blacklists hid a live snail)
def _kill_at(brain, dx, dot=(100.0, 90.0)):
    engaged(brain, 0.0, mob(dx), dot=dot)
    brain.step(obs(0.1, target=mob(dx), target_bar=True, dot=dot))
    return brain.step(obs(0.2, exp=0.25, dot=dot))                          # EXP up, target's bar gone


def _loot_walk(brain, t, moved_per_tick=6.0, dot=(100.0, 90.0), max_t=8.0, scene_dx_sign=1, log=None, still=None,
               wall=None, slide=False, odo_gain=1.0):
    """Feed ticks while the brain loots; we walk `moved_per_tick` px per tick (6 px/0.05 s = 120 px/s, as measured)
    in whichever way it holds; the minimap dot follows (15 px per minimap px). Camera follows us: scene_dx = -move.
    Like the executor, a pickup tap does not let go of a held walk key. `log` collects our position at every Z,
    `still` only those pressed standing still. `wall`: a position we can't walk past (the dot freezes there).
    `slide`: after letting go we keep sliding (pkg_sprites1 66.8s: 16 px after a 0.8 s walk; ~8 px after a short
    one), spread over the next ticks. `odo_gain`: the share of our movement the brain's odometer sees (0.85 there)."""
    acts_all, held, pos = [], None, 0.0
    walk_ticks, slide_left, last_dir = 0, 0.0, 1
    S = brain.cfg.perception.screen_per_minimap
    while brain.mode == "LOOT" and t < max_t:
        move = moved_per_tick if held == "right" else -moved_per_tick if held == "left" else 0.0
        if held in ("left", "right"):
            walk_ticks, last_dir = walk_ticks + 1, (1 if held == "right" else -1)
        elif slide and walk_ticks:
            slide_left, walk_ticks = (16.0 if walk_ticks * 0.05 >= 0.4 else 8.0), 0
        if held is None and slide_left > 0:
            step = min(slide_left, 6.0)
            slide_left -= step
            move = step * last_dir
        if wall is not None and (pos + move - wall) * (1 if wall > 0 else -1) > 0:
            move = 0.0
        pos += move
        acts = brain.step(obs(t, exp=0.25, dot=(dot[0] + pos / S, dot[1]), scene_dx=-move * scene_dx_sign * odo_gain))
        acts_all += acts
        for a in acts:
            if isinstance(a, Hold):
                held = a.key
            elif isinstance(a, Release) or (isinstance(a, Tap) and a.key in ("left", "right")):
                held = None
            if isinstance(a, Tap) and a.key == PICKUP:
                if log is not None:
                    log.append(pos)
                if still is not None and held is None:
                    still.append(pos)
        t += 0.05
    return acts_all, t


PICKUP_RANGE = 30          # pkg_human3: a shell ~15 px from our centre was picked up, one ~55-60 px away was not


def assert_swept(brain, z_positions, centre):
    """Every spot a drop can land on (centre +- loot_spread) was within pickup range of some z press."""
    spread = brain.cfg.zones.loot_spread
    missed = [x for x in range(int(centre - spread), int(centre + spread) + 1, 5)
              if min((abs(x - z) for z in z_positions), default=1e9) > PICKUP_RANGE]
    assert not missed, f"z presses at {[round(z) for z in z_positions]} never covered {missed}"


def test_loot_sweeps_through_the_whole_drop_spread(brain):
    """pkg_human3 64s: coin at -20, shell at +15, blue shell at +60 around the dead snail; standing on one spot
    and pressing z got the coin and the near shell, the far shell was left."""
    _kill_at(brain, 60)
    z_at = []
    acts, t = _loot_walk(brain, 0.25, log=z_at)
    assert brain.mode == "SEEK" and brain.stats["loot_pickups"] == 1
    assert_swept(brain, z_at, 60)


def test_drop_right_under_us_is_swept_both_ways(brain):
    _kill_at(brain, 10)
    z_at = []
    _loot_walk(brain, 0.25, log=z_at)
    assert_swept(brain, z_at, 10)


def test_loot_sweep_presses_pickup_while_walking(brain):
    """Like a player running over the drops spamming z: the walk key stays down between presses."""
    _kill_at(brain, 60)
    acts, _ = _loot_walk(brain, 0.25)
    walking_taps = 0
    for prev, a in zip(acts, acts[1:]):
        if isinstance(a, Tap) and a.key == PICKUP and prev == Hold("right"):
            walking_taps += 1
    assert walking_taps >= 2


def test_loot_sweep_is_not_too_slow(brain):
    _kill_at(brain, 60)
    _, t = _loot_walk(brain, 0.25)
    assert t - 0.2 < 4.0                                                    # kill -> done


def test_loot_waits_for_the_drop_then_walks_onto_it_and_picks_up(brain):
    """pkg_020746: pressed Z during the death animation, before anything had dropped, from too far away."""
    acts = _kill_at(brain, 60)
    assert brain.mode == "LOOT" and not any(isinstance(a, Tap) and a.key == PICKUP for a in acts)
    acts, t = _loot_walk(brain, 0.25)
    holds = [i for i, a in enumerate(acts) if a == Hold("right")]
    zs = [i for i, a in enumerate(acts) if isinstance(a, Tap) and a.key == PICKUP]
    assert holds and zs and min(holds) < min(zs)                           # walked first, picked up after
    first_hold_t = 0.25 + 0.05 * sum(1 for _ in range(0))                  # (timing checked below)
    assert brain.mode == "SEEK" and brain.stats["loot_pickups"] == 1 and len(zs) >= 3
    assert brain.walked_for_loot == pytest.approx(60 + brain.cfg.zones.loot_spread, abs=25)   # through it


def test_loot_does_not_start_walking_during_the_death_animation(brain):
    _kill_at(brain, 60)
    acts = brain.step(obs(0.5, exp=0.25, scene_dx=0.0))                    # 0.3s after the kill
    assert not any(isinstance(a, (Hold, Tap)) and getattr(a, "key", "") in ("right", PICKUP) for a in acts)


def test_far_loot_is_not_worth_walking_to(brain):
    engaged(brain, 0.0, mob(-300))
    brain.step(obs(0.1, target=mob(-300), target_bar=True))
    brain.target.swung_at = 0.1                     # we hit it and it was knocked far away (EXP counts for it)
    brain.step(obs(0.2, exp=0.25))
    assert brain.mode == "SEEK"


def test_party_exp_is_not_a_kill_of_a_far_target(brain):
    # 2026-11-02 rain1/rain2 (in a party): party members' kills raise our EXP every ~2 s; each one 'killed' the
    # target we were walking to (dx 400-1100) and we walked there to loot it - 'walking constantly to the map edges'
    engaged(brain, 0.0, mob(-450))
    brain.step(obs(0.1, target=mob(-450), target_bar=True))
    brain.step(obs(0.2, exp=0.25, target=mob(-440), target_bar=True))
    assert brain.mode == "ENGAGE" and brain.stats["kills"] == 0 and brain.stats["foreign_exp"] == 1
    assert brain.target.points_at_engage is not None            # re-based: the next change is judged afresh


def test_loot_found_by_hitting_it_is_picked_up_and_only_briefly_ignored(brain):
    engaged(brain, 0.0, mob(62), dot=(100.0, 90.0))
    t = 0.1
    while brain.mode == "ENGAGE":
        brain.step(obs(t, target=mob(62), dot=(100.0, 90.0)))
        t += 0.1
    assert brain.mode == "LOOT"
    acts, t = _loot_walk(brain, t)
    assert [a.key for a in acts if isinstance(a, Tap)].count(PICKUP) >= 3
    S = brain.cfg.perception.screen_per_minimap
    acts = brain.step(obs(t + 15, moving=[mob(0)], dot=(100.0 + 62 / S, 90.0)))   # 15s later a snail there
    assert any(isinstance(a, Track) for a in acts)


def test_pickup_presses_are_spread_out_like_a_player(brain):
    """pkg_loot1 76s: coin + snail shell on the ground, 3 z taps within 0.27s picked up only the coin."""
    _kill_at(brain, 10)
    t, z_times = 0.25, []
    while brain.mode == "LOOT" and t < 4:
        if any(isinstance(a, Tap) and a.key == PICKUP for a in brain.step(obs(t, exp=0.25))):
            z_times.append(t)
        t += 0.05
    assert len(z_times) >= 4
    gaps = [b - a for a, b in zip(z_times, z_times[1:])]
    assert min(gaps) >= brain.cfg.timing.pickup_gap_min_s - 1e-6


def test_a_burst_of_3_to_5_presses_standing_on_the_drop_centre(brain):
    """pkg_zspam1: items stayed on the floor after a sweep; the shell at 44.5s went only when we pressed Z standing
    still - and the burst was 55 px past the drop centre. The user: a player spams Z 3-5 times after a kill."""
    _kill_at(brain, 60)
    still = []
    _loot_walk(brain, 0.25, still=still)
    at_centre = [p for p in still if abs(p - 60) <= brain.cfg.zones.loot_reach]
    assert 3 <= len(at_centre) <= 5


def test_then_a_short_burst_further_across_the_drop(brain):
    _kill_at(brain, 60)
    still = []
    _loot_walk(brain, 0.25, still=still)
    beyond = [p for p in still if p > 60 + brain.cfg.zones.loot_reach]
    assert 1 <= len(beyond) <= 2 and all(p - 60 <= brain.cfg.zones.loot_spread for p in beyond)


def test_the_centre_burst_count_varies():
    counts = set()
    for seed in range(12):
        cfg = Config()
        cfg.humanize.seed = seed
        b = Brain(cfg)
        _kill_at(b, 60)
        still = []
        _loot_walk(b, 0.25, still=still)
        counts.add(sum(1 for p in still if abs(p - 60) <= 15))
    assert len(counts) >= 2


def test_a_wall_in_the_drop_area_still_gets_a_burst_and_finishes(brain):
    """pkg_zspam1 84.6s: a wall stopped the sweep -> 'blocked' -> loot abandoned without the burst."""
    _kill_at(brain, 60)
    still = []
    _loot_walk(brain, 0.25, still=still, wall=80)
    assert brain.mode == "SEEK" and brain.stats["loot_gave_up"] == 0
    assert sum(1 for p in still if p >= 70) >= brain.cfg.timing.side_taps_min     # the side burst, at the wall


def test_pickup_is_spammed_over_the_drop_centre(brain):
    """Several items can lie on the same spot: several presses while we're over it."""
    _kill_at(brain, 60)
    z_at = []
    _loot_walk(brain, 0.25, log=z_at)
    assert sum(1 for z in z_at if abs(z - 60) <= 30) >= 4


def _hit_loot_at(brain, dx):
    engaged(brain, 0.0, mob(dx))
    t = 0.1
    while brain.mode == "ENGAGE":
        brain.step(obs(t, target=mob(dx)))
        t += 0.1
    assert brain.mode == "LOOT"
    return t


@pytest.mark.parametrize("dx", [62, -62, 110])
def test_a_long_loot_walk_stops_on_the_item_despite_the_slide(brain, dx):
    """pkg_sprites1 66s: a coin at +57..64 (hit for 1.2s, no HP bar). The walk let go 8 px early, slid 16 px and
    the odometer saw ~85 % of the way: we stood ~40 px past it, out of pickup range, and the coin stayed."""
    if abs(dx) <= brain.cfg.zones.hit_max:
        t = _hit_loot_at(brain, dx)
    else:                                       # (a loot spot further away: same walk, started directly)
        brain._go_loot(obs(0.0), dx, "test", dying=False)
        t = 0.05
    still = []
    _loot_walk(brain, t, still=still, slide=True, odo_gain=0.85)
    first_burst = still[:3]
    assert first_burst and all(abs(p - dx) <= PICKUP_RANGE for p in first_burst), (dx, still)


def test_a_single_item_gets_its_second_burst_on_the_near_side(brain):
    """One item, not a mob's spread of drops: if we overshot it, it's behind us, not further across."""
    t = _hit_loot_at(brain, 62)
    still = []
    _loot_walk(brain, t, still=still, slide=True, odo_gain=0.85)
    assert any(p < 62 - brain.cfg.zones.loot_reach for p in still)
    assert not any(p > 62 + brain.cfg.zones.loot_spread for p in still)


def test_a_kill_still_gets_its_second_burst_further_across(brain):
    _kill_at(brain, 60)
    still = []
    _loot_walk(brain, 0.25, still=still, slide=True, odo_gain=0.85)
    assert any(p > 60 + brain.cfg.zones.loot_reach for p in still)


def test_loot_found_by_hitting_it_is_picked_up_without_the_death_wait(brain):
    """Nothing is dying when 'the target' was a drop all along: don't stand there 0.9s first."""
    engaged(brain, 0.0, mob(10))
    t = 0.1
    while brain.mode == "ENGAGE":
        brain.step(obs(t, target=mob(10)))
        t += 0.1
    start, first_z = t, None
    while brain.mode == "LOOT" and first_z is None:
        if any(isinstance(a, Tap) and a.key == PICKUP for a in brain.step(obs(t))):
            first_z = t
        t += 0.05
    assert first_z is not None and first_z - start < 0.5


def test_a_mob_in_reach_interrupts_looting(brain):
    _kill_at(brain, 60)
    biter = mob(-55)
    acts = brain.step(obs(0.3, exp=0.25, bar=[biter]))
    assert brain.mode == "ENGAGE" and Track(biter) in acts


def test_kill_whose_hp_bar_fades_just_after_the_exp_is_still_looted(brain):
    """pkg_human1 kills #3/#4: EXP rose while the dying snail's bar was still drawn for ~0.15s -> never looted."""
    engaged(brain, 0.0, mob(55))
    brain.step(obs(0.1, target=mob(55), target_bar=True))
    brain.step(obs(0.2, exp=0.25, target=mob(55), target_bar=True, bar=[mob(55)]))   # EXP up, bar still there
    assert brain.mode == "ENGAGE"
    brain.step(obs(0.35, exp=0.25))                                                   # bar gone a moment later
    assert brain.mode == "LOOT" and brain.loot_rel == pytest.approx(55, abs=1)


def test_another_mobs_kill_does_not_send_us_looting_much_later(brain):
    engaged(brain, 0.0, mob(55))
    brain.step(obs(0.1, target=mob(55), target_bar=True))
    brain.step(obs(0.2, exp=0.25, target=mob(55), target_bar=True, bar=[mob(55)]))
    brain.step(obs(1.5, exp=0.25, target=mob(55), target_bar=True, bar=[mob(55)]))   # still alive long after
    brain.step(obs(1.6, exp=0.25, target=mob(55)))                                    # bar flickers off
    assert brain.mode == "ENGAGE"


def test_loot_left_for_a_fight_is_collected_afterwards(brain):
    """pkg_human1 kill #1: a snail came into reach while waiting for the drop; that loot was never picked up."""
    _kill_at(brain, 60)                                                     # drop #1 at +60
    biter = mob(-55)
    brain.step(obs(0.3, exp=0.25, bar=[biter]))                             # leave it, fight the biter
    brain.step(obs(0.4, exp=0.25, target=biter, target_bar=True))
    brain.step(obs(0.5, exp=0.30))                                          # biter dies -> its own loot
    assert brain.mode == "LOOT" and brain.loot_rel == pytest.approx(-55, abs=1)
    acts, t = _loot_walk(brain, 0.55)
    assert brain.mode == "SEEK"
    brain.step(obs(t, exp=0.30))                                            # then back to drop #1
    assert brain.mode == "LOOT" and brain.loot_rel > 0


def test_loot_skipped_by_a_chain_kill_is_collected_afterwards(brain):
    engaged(brain, 0.0, mob(55))
    brain.step(obs(0.1, target=mob(55), target_bar=True))
    other = mob(-70)
    brain.step(obs(0.2, exp=0.25, bar=[other]))                             # dies, chain to the next one
    assert brain.mode == "ENGAGE"
    brain.step(obs(0.3, exp=0.25, target=other, target_bar=True))
    brain.step(obs(0.4, exp=0.30))                                          # second one dies
    _, t = _loot_walk(brain, 0.45)
    brain.step(obs(t, exp=0.30))
    assert brain.mode == "LOOT" and brain.loot_rel > 0                      # the first one's drop


def test_old_left_behind_loot_is_forgotten(brain):
    _kill_at(brain, 60)
    brain.step(obs(0.3, exp=0.25, bar=[mob(-55)]))                          # drop left for a fight
    assert brain.pending_loot
    brain.mode, brain.target = "SEEK", None
    brain.step(obs(0.3 + brain.cfg.timing.loot_memory_s + 1, exp=0.25))     # long after
    assert brain.mode == "SEEK" and not brain.pending_loot


def test_looting_where_we_cannot_move_spams_z_where_we_stand_and_finishes(brain):
    _kill_at(brain, 60)
    still = []
    acts, t = _loot_walk(brain, 0.25, moved_per_tick=0.0, still=still)     # holding right, going nowhere
    # (+ one blocked period: a jump is tried first in case it's a step - 2026-11-02)
    assert brain.mode == "SEEK" and t < 4 + longest(brain, brain.cfg.timing.blocked_s) and len(still) >= 3
    assert brain.stats["block_jumps"] == 1


def test_patrol_into_a_wall_turns_around_at_once(brain):
    """pkg_020746: patrolled left into the same wall 8 times (taps weren't checked for movement)."""
    t, dirs = 0.0, []
    for _ in range(12):
        brain.step(obs(t, dot=(45.0, 90.0))); t += 0.1
        acts = brain.step(obs(t, moving=[], dot=(45.0, 90.0))); t += 0.1      # dot never changes: a wall
        dirs += [a.key for a in acts if isinstance(a, Tap)]
    assert dirs[0] == "left" and dirs[1] == "right"                          # one bump, then the other way
    assert dirs.count("left") == 1


def test_patrol_sweeps_one_way_until_the_leash_then_turns(brain):
    """pkg_020324: alternated left/right every step -> paced over the same coin for 30s."""
    leash = brain.cfg.safety.leash_minimap_px
    t, x, dirs = 0.0, 100.0, []
    for _ in range(40):
        brain.step(obs(t, dot=(x, 90.0))); t += 0.1
        acts = brain.step(obs(t, moving=[], dot=(x, 90.0))); t += 0.1
        for a in acts:
            if isinstance(a, Tap):
                dirs.append(a.key)
                x += (-1 if a.key == "left" else 1) * 25                      # each patrol step moves us
    assert dirs[:2] == ["left", "left"]                                       # keeps going, no ping-pong
    assert "right" in dirs                                                    # turned around at the leash
    first_right = dirs.index("right")
    assert first_right * 25 > leash                                           # only after reaching it


# ---------------------------------------------------------------- sprite mode (run --map): search without pauses
@pytest.fixture(params=["exact", 1, 2, 3])
def sbrain(request):
    cfg = Config()
    cfg.perception.map_id = 42
    if request.param == "exact":
        cfg.humanize.jitter = 0.0
    else:
        cfg.humanize.seed = request.param
    return Brain(cfg)


def test_sprite_mode_searches_by_walking_not_by_stopping_to_look(sbrain):
    """pkg_sprites2: 59 of 89 s went into stop-and-look ticks and blocking patrol taps. The user: 'too many
    pauses, a real player is more decisive'. With sprites every frame is a look: just keep walking."""
    acts = []
    for i in range(40):                                                    # 2 s of nothing in sight
        acts += sbrain.step(obs(i * 0.05, dot=(100.0 + i * 0.4, 90.0)))
    assert not any(isinstance(a, Look) for a in acts)
    assert not any(isinstance(a, Tap) for a in acts)                      # no blocking patrol taps
    assert not any(isinstance(a, Release) for a in acts[1:])              # one continuous walk
    assert {a.key for a in acts if isinstance(a, Hold)} == {sbrain.patrol_dir}


def test_sprite_mode_turns_around_at_a_wall(sbrain):
    # a jump is tried first (2026-11-02), so the block takes ~2 s: longer than a 2-3 s idle walk - give it time
    sbrain.cfg.timing.idle_walk_min_s = sbrain.cfg.timing.idle_walk_max_s = 5.0
    first = sbrain.patrol_dir
    t = 0.0
    while sbrain.stats["blocked"] == 0 and t < 3.0:                         # walking, the minimap dot never moves
        sbrain.step(obs(t))
        t += 0.05
    assert sbrain.stats["blocked"] == 1 and sbrain.stats["block_jumps"] == 1   # a jump first, then turn around
    acts = sbrain.step(obs(t))
    other = "right" if first == "left" else "left"
    assert Hold(other) in acts


def test_sprite_mode_engages_a_mob_the_moment_it_shows_up_while_walking(sbrain):
    for i in range(10):
        sbrain.step(obs(i * 0.05, dot=(100.0 + i * 0.4, 90.0)))
    acts = sbrain.step(obs(0.5, lib=[mob(-250)], dot=(104.0, 90.0)))
    assert Track(mob(-250)) in acts and sbrain.mode == "ENGAGE"


def test_sprite_mode_ignores_motion_that_no_sprite_explains(sbrain):
    acts = sbrain.step(obs(0.0, moving=[mob(-200)]))
    assert not any(isinstance(a, Track) for a in acts)


def test_sprite_mode_does_not_stop_to_look_when_hit_mid_fight(sbrain):
    assert Track(mob(-300)) in sbrain.step(obs(0.0, lib=[mob(-300)]))
    sbrain.step(obs(0.1, target=mob(-300)))
    acts = sbrain.step(obs(0.2, target=mob(-290), hp=0.9))
    assert not any(isinstance(a, Look) for a in acts)


def low_mob(dx, below=60, w=37, h=26):
    """A mob on lower ground: its bottom `below` px under our feet (we stand on a raised step)."""
    return (int(PX + dx - w / 2), int(FEET + below - h), w, h)


def test_a_mob_on_lower_ground_is_walked_down_to_not_swung_at_from_above(brain):
    """pkg_sprites2 4.9s: we stood on a raised step (feet 519), a Snail 60 px below at dx -64. We swung over its
    head for 1.1 s, no HP bar -> 'not a mob'. Step off the ledge toward it instead, then fight on its level."""
    _step_down_scenario(brain)


def test_a_mob_on_lower_ground_is_walked_down_to_in_sprite_mode(sbrain):
    _step_down_scenario(sbrain)


def _step_down_scenario(b):
    low = low_mob(-64)
    assert Track(low) in b.step(obs(0.0, lib=[low]))
    acts = []
    for i in range(1, 8):
        acts += b.step(obs(i * 0.05, target=low, dot=(100.0 - i * 0.4, 90.0)))
    assert Hold("left") in acts and Hold(ATTACK) not in acts
    assert b.mode == "ENGAGE" and b.stats["not_a_mob"] == 0
    same = mob(-60)                                                        # we dropped: now on its level
    acts = b.step(obs(0.5, target=same))
    assert acts[-1] == Hold(ATTACK)


# ---------------------------------------------------------------- anticipating a mob that walks toward us
def _snail_comes(brain, start_dx, speed, t0=0.1, until=1.6, bar=True):
    """We stand still; the target walks toward us at `speed` px/s. Returns all actions and the dx of the first swing."""
    acts, first_swing, t, dx = [], None, t0, float(start_dx)
    while t < until:
        a = brain.step(obs(t, target=mob(dx), target_bar=bar, bar=[mob(dx)] if bar else ()))
        acts += a
        if first_swing is None and Hold(ATTACK) in a:
            first_swing = dx
        step = speed * 0.05
        dx = dx + step if dx < 0 else dx - step
        if abs(dx) < 45:
            break
        t += 0.05
    return acts, first_swing


def test_a_snail_walking_at_us_is_waited_for_not_stepped_into(brain):
    """pkg_sprites3 11.5 / 66.9 s: at -75..-81 we took a 0.1 s step while the snail came on -> -39 contact."""
    engaged(brain, 0.0, mob(-88))
    acts, first_swing = _snail_comes(brain, -88, 45)
    assert Tap("left", brain.cfg.timing.step_s) not in acts                  # no step into it (turning is fine)
    assert Hold("left") not in acts                                          # no walking into it
    assert first_swing is not None


def test_the_swing_starts_before_a_coming_snail_is_in_reach(brain):
    """It walks into the swing: swing a little early (its speed x anticipate_s), not when it's already at 66."""
    engaged(brain, 0.0, mob(-88))
    _, first_swing = _snail_comes(brain, -88, 45)
    z = brain.cfg.zones
    assert z.hit_max < abs(first_swing) <= z.hit_max + 45 * brain.cfg.timing.anticipate_s + 3


def test_a_snail_standing_still_just_out_of_reach_is_walked_to(brain):
    engaged(brain, 0.0, mob(-85))
    acts, _ = _snail_comes(brain, -85, 0, until=0.6, bar=False)
    assert Hold("left") in acts


def test_approach_speed_ignores_noise_and_our_own_walking(brain):
    """A target that 'jumps' (tracking noise) or that we walk toward is not a mob charging at us."""
    engaged(brain, 0.0, mob(-300))
    t = 0.1
    for dx in (-300, -294, -288, -282, -276, -270):                         # we walk: the odometer sees it
        brain.step(obs(t, target=mob(dx), scene_dx=6.0))   # walking left: the scenery shifts right
        t += 0.05
    assert brain._approach(brain.target) == 0.0


def test_a_slowly_coming_snail_is_walked_in_to_not_waited_for(brain):
    """The user after pkg_sprites5: 'slightly more aggressive, hitting the mobs faster' (12.6 s of standing in
    fights). Only a charging mob is waited for; a slow one we meet."""
    engaged(brain, 0.0, mob(-88))
    acts, _ = _snail_comes(brain, -88, 20, until=0.8, bar=False)
    assert Hold("left") in acts


# ---------------------------------------------------------------- the leash (pkg_sprites6 66-95 s: left-right loop)
def test_leash_centre_is_a_steady_reading_not_a_misread_first_one(sbrain):
    sbrain.step(obs(0.0, dot=(3.9, 81.5)))                                 # misread as the game came up
    for i in range(1, 7):
        sbrain.step(obs(i * 0.05, dot=(100.0, 89.5)))
    assert sbrain.start_dot == (100.0, 89.5)


def test_no_engage_drop_loop_at_the_edge_of_the_leash(sbrain):
    """pkg_sprites6: at the leash's edge the dot flickered 63/64: SEEK picked a target outward, the fight said 'past
    the leash' 0.6 s later, walk back, pick it again... 26 times, to the end of the run."""
    leash = sbrain.cfg.safety.leash_minimap_px
    for i in range(6):
        sbrain.step(obs(i * 0.05, dot=(100.0, 89.5)))                      # start at 100
    t, drops, tracks = 0.3, 0, 0
    for i in range(80):                                                    # we stand right at the edge, dot flickers
        edge = 100.0 + leash + (0.6 if i % 2 else -0.6)
        acts = sbrain.step(obs(t, dot=(edge, 89.5), lib=[mob(250)],
                               target=mob(250) if sbrain.mode == "ENGAGE" else None))
        tracks += sum(isinstance(a, Track) for a in acts)
        drops += sum(isinstance(a, Untrack) for a in acts)
        t += 0.05
    assert tracks <= 1 and drops <= 1


# ---------------------------------------------------------------- pkg_sprites7b
def test_a_fought_target_that_vanishes_is_given_up_quickly_and_its_spot_looted(sbrain):
    """pkg_sprites7b 7-20 s: the snail we were fighting (HP bar) was gone (no EXP for us - another player's kill?),
    a coin lay there; we swung at the flowers for 14 s until the engage timeout."""
    b = sbrain
    assert Track(mob(-60)) in b.step(obs(0.0, lib=[mob(-60)]))
    t = 0.05
    while t < 1.0:
        b.step(obs(t, target=mob(-60), target_bar=True, bar=[mob(-60)]))
        t += 0.05
    gone_at, swings_late = t, 0
    while t < gone_at + 3.0 and b.mode == "ENGAGE":
        acts = b.step(obs(t))
        if t - gone_at > b.cfg.timing.keep_close_s + 0.2:
            swings_late += acts.count(Hold(ATTACK))
        t += 0.05
    assert b.mode in ("LOOT", "SEEK") and t - gone_at < b.cfg.timing.keep_close_s + 0.2   # (in reach: maybe hidden)
    assert swings_late == 0
    assert any("target gone" in e for e in b.events)


def test_walls_at_both_ends_of_an_empty_floor_keep_us_walking(sbrain):
    """pkg_sprites7b 68-77 s: left wall, then right wall -> both avoided 15 s -> stood still 9 s."""
    b = sbrain
    b.blocked = {"left": 20.0, "right": 25.0}                              # met the right wall last
    acts = b.step(obs(10.0))
    assert Hold("left") in acts


# ---------------------------------------------------------------- potions (the user: drink at 20 %, stop at 45 % only
# when no HP potions are left; HP potion on Del, MP potion on End)
def pobs(t, hp=1.0, mp=1.0, hp_potions=True, mp_potions=False, **kw):
    o = obs(t, hp=hp, **kw)
    o.mp, o.hp_potions, o.mp_potions = mp, hp_potions, mp_potions
    return o


def test_drinks_an_hp_potion_below_20_percent(brain):
    acts = brain.step(pobs(0.0, hp=0.18))
    assert acts[0] == Tap(HP_POTION, brain.cfg.timing.potion_press_s)
    assert not any(isinstance(a, Stop) for a in acts) and brain.stats["potions"] == 1


def test_with_potions_45_percent_is_no_stop_and_no_potion_yet(brain):
    acts = brain.step(pobs(0.0, hp=0.55))   # above hp_potion_at (50 %)
    assert not any(isinstance(a, Stop) for a in acts)
    assert Tap(HP_POTION, brain.cfg.timing.potion_press_s) not in acts


def test_no_hp_potions_left_stops_at_45_percent(brain):
    acts = brain.step(pobs(0.0, hp=0.40, hp_potions=False))
    assert isinstance(acts[-1], Stop) and "no HP potions" in acts[-1].reason


def test_unknown_potion_slot_counts_as_none(brain):
    assert isinstance(brain.step(pobs(0.0, hp=0.40, hp_potions=None))[-1], Stop)


def test_potions_are_spaced_out_randomly(brain):
    t, taps = 0.0, []
    while t < 3.0:
        if Tap(HP_POTION, brain.cfg.timing.potion_press_s) in brain.step(pobs(t, hp=0.15)):
            taps.append(t)
        t += 0.05
    gaps = [b - a for a, b in zip(taps, taps[1:])]
    cd = brain.cfg.timing.potion_cooldown_s
    assert len(taps) >= 2 and min(gaps) >= cd * (1 - brain.cfg.humanize.jitter) - 0.05


def test_drinking_mid_fight_keeps_fighting(brain):
    engaged(brain, 0.0, mob(-60))
    acts = brain.step(pobs(0.1, hp=0.15, target=mob(-60), target_bar=True, bar=[mob(-60)]))
    assert acts[0] == Tap(HP_POTION, brain.cfg.timing.potion_press_s)
    assert acts[-1] == Hold(ATTACK) and brain.mode == "ENGAGE"


def test_mp_potion_below_10_percent_only_if_there_are_some(brain):
    acts = brain.step(pobs(0.0, mp=0.05, mp_potions=True))
    assert Tap(MP_POTION, brain.cfg.timing.potion_press_s) in acts
    b2 = Brain(brain.cfg)
    acts = b2.step(pobs(0.0, mp=0.05, mp_potions=False))
    assert Tap(MP_POTION, brain.cfg.timing.potion_press_s) not in acts and not any(isinstance(a, Stop) for a in acts)


# ---------------------------------------------------------------- out of MP: plain attack (the user: out of MP and
# MP potions -> C instead of space (Power Strike); enough MP again -> space, until out of MP again)
def _fight_tick(b, t, mp, mp_potions=False):
    return b.step(pobs(t, mp=mp, mp_potions=mp_potions, target=mob(-60), target_bar=True, bar=[mob(-60)]))


def test_out_of_mp_and_potions_swings_with_the_plain_attack(brain):
    engaged(brain, 0.0, mob(-60))
    assert _fight_tick(brain, 0.1, mp=1.0)[-1] == Hold(ATTACK)
    acts = _fight_tick(brain, 0.2, mp=0.01)
    assert acts[-1] == Hold(BASIC) and brain.stats["basic_switches"] == 1


def test_low_mp_with_potions_keeps_the_skill(brain):
    engaged(brain, 0.0, mob(-60))
    assert _fight_tick(brain, 0.1, mp=0.01, mp_potions=True)[-1] == Hold(ATTACK)


def test_skill_again_once_mp_refilled_with_a_gap_against_flip_flop(brain):
    s = brain.cfg.safety
    engaged(brain, 0.0, mob(-60))
    assert _fight_tick(brain, 0.1, mp=0.01)[-1] == Hold(BASIC)
    mid = (s.basic_below_mp + s.skill_again_mp) / 2                  # between the two: stays plain
    assert _fight_tick(brain, 0.2, mp=mid)[-1] == Hold(BASIC)
    assert _fight_tick(brain, 0.3, mp=s.skill_again_mp)[-1] == Hold(ATTACK)
    assert _fight_tick(brain, 0.4, mp=mid)[-1] == Hold(ATTACK)      # until out of MP again
    assert _fight_tick(brain, 0.5, mp=0.01)[-1] == Hold(BASIC)
    assert brain.stats["basic_switches"] == 2


def test_a_few_casts_worth_of_mp_is_enough_for_the_skill(brain):
    """oom2: 13-29 of 275 MP (5-10 %) and the bot still swung C; a Power Strike costs ~4-6 MP."""
    engaged(brain, 0.0, mob(-60))
    assert _fight_tick(brain, 0.1, mp=0.05)[-1] == Hold(ATTACK)
    assert _fight_tick(brain, 0.2, mp=0.01)[-1] == Hold(BASIC)
    assert _fight_tick(brain, 0.3, mp=0.05)[-1] == Hold(ATTACK)


def test_new_mp_potions_bring_the_skill_back(brain):
    engaged(brain, 0.0, mob(-60))
    assert _fight_tick(brain, 0.1, mp=0.01)[-1] == Hold(BASIC)
    acts = _fight_tick(brain, 0.2, mp=0.01, mp_potions=True)
    assert acts[-1] == Hold(ATTACK) and Tap(MP_POTION, brain.cfg.timing.potion_press_s) in acts


# ---------------------------------------------------------------- used-up potions: the slot keeps the icon with a
# "0" when the last potion is gone (session 10: End read 'filled' at 0 MP potions, the bot pressed End every second
# and never switched to the plain attack)
def _mp_dry(b, t0, secs, mp=0.01, dt=0.05, **kw):
    """MP stuck at `mp` with the End slot reading filled; returns every tap time of End."""
    taps, t = [], t0
    while t < t0 + secs:
        if Tap(MP_POTION, b.cfg.timing.potion_press_s) in b.step(pobs(t, mp=mp, mp_potions=True, **kw)):
            taps.append(t)
        t += dt
    return taps


def test_potions_that_do_nothing_are_used_up(brain):
    taps = _mp_dry(brain, 0.0, 6.0)
    assert len(taps) == brain.cfg.timing.potion_fails and brain.stats["potions_out"] == 1


def test_used_up_mp_potions_switch_to_the_plain_attack(brain):
    engaged(brain, 0.0, mob(-60))
    _mp_dry(brain, 0.1, 4.0, target=mob(-60), target_bar=True, bar=[mob(-60)])
    assert _fight_tick(brain, 4.2, mp=0.01, mp_potions=True)[-1] == Hold(BASIC)


def test_used_up_potions_are_probed_now_and_then_and_a_restock_counts(brain):
    tm = brain.cfg.timing
    _mp_dry(brain, 0.0, 4.0)
    probes = _mp_dry(brain, 4.0, 2 * tm.potion_recheck_max_s + 1)
    gaps = [y - x for x, y in zip(probes, probes[1:])]
    assert probes and all(g >= tm.potion_recheck_min_s * 0.95 for g in gaps)   # a probe now and then, not each second
    b2 = Brain(brain.cfg)
    _mp_dry(b2, 0.0, 4.0)
    t, first = 4.0, None
    while first is None:
        if Tap(MP_POTION, tm.potion_press_s) in b2.step(pobs(t, mp=0.02, mp_potions=True)):
            first = t
        t += 0.05
    brain = b2
    t = first + 0.05
    while t < probes[0] + tm.potion_verify_s + 0.2:                  # restocked: this press worked
        brain.step(pobs(t, mp=0.5, mp_potions=True))
        t += 0.05
    assert brain._have("MP", pobs(t, mp_potions=True))


def test_a_working_potion_resets_the_misses(brain):
    tm = brain.cfg.timing
    t = 0.0
    for mp_after in (0.02, 0.4, 0.02, 0.4, 0.02):                  # every other press works: never 2 misses in a row
        brain.step(pobs(t, mp=0.02, mp_potions=True))
        t2 = t + 0.05
        while t2 < t + tm.potion_cooldown_s * 1.4:
            brain.step(pobs(t2, mp=mp_after if mp_after > 0.2 else 0.02, mp_potions=True))
            t2 += 0.05
        t = t2
    assert brain.stats["potions_out"] == 0


def test_used_up_hp_potions_allow_the_safety_stop(brain):
    t, acts = 0.0, []
    while t < 6.0 and not any(isinstance(a, Stop) for a in acts):
        acts = brain.step(pobs(t, hp=0.15, hp_potions=True))
        t += 0.05
    assert any(isinstance(a, Stop) for a in acts)


# ---------------------------------------------------------------- nothing to attack: stop and wait for a spawn
def _idle(b, t0, secs, dt=0.05):
    """Nothing in sight for `secs`, the minimap dot moving while we walk. Returns [(t, actions)]."""
    out, t = [], t0
    while t < t0 + secs:
        out.append((t, b.step(obs(t, dot=(100.0 + (t - t0) * 2, 90.0)))))
        t += dt
    return out


def _walk_end(ticks):
    """Time of the last tick that still walks (holds left/right)."""
    walking = [t for t, acts in ticks if any(isinstance(a, Hold) and a.key in ("left", "right") for a in acts)]
    return walking[-1] if walking else None


def test_nothing_to_attack_walks_at_most_3s_then_stands_still(sbrain):
    """pkg_potions1: no mobs from 37 s on, the bot paced wall to wall for 57 s -> a lie detector test. The user:
    stop moving after a random 2-3 s when nothing is there to attack, and wait for a spawn. (Idle jumps off here:
    tested on their own below.)"""
    sbrain.cfg.timing.idle_jumps = False
    ticks = _idle(sbrain, 0.0, 20.0)
    end = _walk_end(ticks)
    assert end is not None and 1.9 <= end <= 3.0
    after = [a for t, acts in ticks if t > end for a in acts]
    assert not any(isinstance(a, (Hold, Tap)) for a in after)               # no walking, no keys at all
    assert sbrain.stats["waits"] == 1


def test_waiting_engages_a_spawn_and_the_next_idle_spell_gets_a_fresh_walk(sbrain):
    sbrain.cfg.timing.idle_jumps = False
    _idle(sbrain, 0.0, 6.0)
    acts = sbrain.step(obs(6.0, lib=[mob(-200)]))
    assert Track(mob(-200)) in acts and sbrain.mode == "ENGAGE"
    sbrain.mode, sbrain.target = "SEEK", None                              # the fight is over (details elsewhere)
    ticks = _idle(sbrain, 10.0, 10.0)
    end = _walk_end(ticks)
    assert end is not None and 11.9 <= end <= 13.0                          # walks 2-3 s again, then waits


# ---------------------------------------------------------------- the game's Lie Detector
def _lie_obs(t, **kw):
    o = obs(t, **kw)
    o.lie_detector = True
    return o


def test_lie_detector_stops_everything_at_once_even_mid_fight(brain):
    """pkg_potions1: the Lie Detector came up and the bot walked on for 40 s. Hands off at once, stop, alarm."""
    brain.step(obs(0.0, lib=[mob(-60)]))
    brain.step(obs(0.1, target=mob(-60)))
    acts = brain.step(_lie_obs(0.2, target=mob(-60)))
    assert any(isinstance(a, Stop) and "LIE DETECTOR" in a.reason for a in acts)
    assert Release() in acts and not any(isinstance(a, (Hold, Tap)) for a in acts)


def test_lie_detector_outranks_potions(brain):
    o = pobs(0.0, hp=0.1)                                                   # potions in the slot: would drink
    o.lie_detector = True
    acts = brain.step(o)
    assert any(isinstance(a, Stop) and "LIE DETECTOR" in a.reason for a in acts)
    assert not any(isinstance(a, Tap) for a in acts)


# ---------------------------------------------------------------- decisiveness (the user, session 5)
def test_a_mob_that_fought_us_and_stands_just_out_of_reach_is_walked_to_at_once(brain):
    """pkg_idle1: 6 of 9 stops mid-fight: after a step back the snail stood at 77-90 px with its HP bar; we waited
    0.4-0.8 s, then took a step. Walk in as soon as we know it isn't charging at us (~0.2 s of sightings)."""
    engaged(brain, 0.0, mob(-82))
    acts, t = [], 0.1
    while t < 0.4:
        acts += brain.step(obs(t, target=mob(-82), target_bar=True, bar=[mob(-82)], dot=(100.0 + t, 90.0)))
        t += 0.05
    assert Hold("left") in acts and Tap("left", brain.cfg.timing.step_s) not in acts


def _done_looting(b):
    assert any(isinstance(a, Track) for a in b.step(obs(0.0, lib=[mob(40)])))     # sprite mode: seen, engaged
    b.step(obs(0.1, target=mob(40), target_bar=True, bar=[mob(40)]))
    b.step(obs(0.2, exp=0.25))                                                    # killed
    _, t = _loot_walk(b, 0.25)
    assert b.mode == "SEEK"
    return t


def test_after_looting_a_short_human_pause_before_the_next_target(sbrain):
    """Pauses belong at phase boundaries (after loot), never on the way to a target."""
    t = _done_looting(sbrain)
    tm = sbrain.cfg.timing
    far = mob(-300)
    first = None
    for i in range(30):
        acts = sbrain.step(obs(t + i * 0.05, exp=0.25, lib=[far]))
        if any(isinstance(a, Track) for a in acts):
            first = i * 0.05
            break
    assert first is not None and first <= tm.phase_pause_max_s + 0.06
    assert first >= tm.phase_pause_min_s - 0.06


def test_after_looting_a_mob_in_reach_is_fought_at_once(sbrain):
    t = _done_looting(sbrain)
    acts = sbrain.step(obs(t, exp=0.25, lib=[mob(-60)]))
    assert any(isinstance(a, Track) for a in acts)


# ---------------------------------------------------------------- another player's kill (pkg_human5m)
def _hitting(b, dx=60, bar=False):
    assert Track(mob(dx)) in b.step(obs(0.0, lib=[mob(dx)]))
    b.step(obs(0.1, target=mob(dx), target_bar=bar, bar=[mob(dx)] if bar else ()))
    assert b.step(obs(0.2, target=mob(dx), target_bar=bar, bar=[mob(dx)] if bar else ()))[-1] == Hold(ATTACK)


def dying(t, **kw):
    o = obs(t, **kw)
    o.target_dying = True
    return o


def test_someone_elses_kill_stops_the_swing_at_once_and_is_not_looted(sbrain):
    """pkg_human5m 242 s: fgbcas killed our Shroom as our first hit landed; we swung at the spot for 1 s, then
    swept their drop with Z (18 times in 5 min)."""
    _hitting(sbrain)
    acts = sbrain.step(dying(0.25))
    assert Hold(ATTACK) not in acts                                         # no swinging at a corpse
    t, seen = 0.3, []
    while t < 1.5:
        seen += sbrain.step(dying(t) if t < 0.6 else obs(t))
        t += 0.05
    assert sbrain.mode == "SEEK" and sbrain.stats["others_kills"] == 1
    assert not any(isinstance(a, Tap) and a.key == PICKUP for a in seen)
    assert Hold(ATTACK) not in seen


def test_our_kill_still_plays_the_death_animation_and_is_looted(sbrain):
    _hitting(sbrain)
    sbrain.step(dying(0.25))
    sbrain.step(dying(0.3, exp=0.25))                                        # EXP follows a tick or two later
    assert sbrain.mode == "LOOT" and sbrain.stats["kills"] == 1 and sbrain.stats["others_kills"] == 0


def test_a_fought_target_gone_without_exp_is_not_looted(sbrain):
    _hitting(sbrain, bar=True)
    t, modes = 0.3, set()
    while t < 2.5:
        sbrain.step(obs(t))                                                  # gone; no EXP for us
        modes.add(sbrain.mode)
        t += 0.05
    assert "LOOT" not in modes and sbrain.mode == "SEEK"


def test_sprite_mode_needs_no_hp_bar_a_hit_target_that_vanishes_without_exp_is_not_looted(sbrain):
    """The user (session 8): no HP bar / name dependency for mobs. Gone without EXP = not our kill."""
    _hitting(sbrain)
    t, modes = 0.3, set()
    while t < 2.5:
        sbrain.step(obs(t))                                                  # gone; no bar ever; no EXP for us
        modes.add(sbrain.mode)
        t += 0.05
    assert "LOOT" not in modes and sbrain.mode == "SEEK" and sbrain.stats["not_a_mob"] == 0


def test_sprite_mode_kill_without_any_hp_bar_is_looted(sbrain):
    box = mob(60)
    sbrain.step(Observation(t=0.0, me=(PX, FEET), exp_points=2000, dot=(100.0, 90.0), known_mobs=[box], sprite_mobs=[box]))
    t = 0.05
    while t < 1.0:
        o = obs(t, target=box)
        o.target_src = "sprite"
        sbrain.step(o)
        t += 0.05
    sbrain.step(obs(t, exp=0.25))                                            # EXP up, its sprite gone
    assert sbrain.stats["kills"] == 1 and sbrain.mode == "LOOT"


def test_sprite_mode_exp_while_our_target_is_still_seen_does_not_end_the_fight(sbrain):
    box = mob(60)
    sbrain.step(Observation(t=0.0, me=(PX, FEET), exp_points=2000, dot=(100.0, 90.0), known_mobs=[box], sprite_mobs=[box]))
    o = obs(0.1, target=box, exp=0.25)                                       # another mob we hit died
    o.target_src = "sprite"
    sbrain.step(o)
    assert sbrain.mode == "ENGAGE"


# ---------------------------------------------------------------- loot by sight (sprite mode, --loot-sight)
@pytest.fixture(params=["exact", 1, 2, 3])
def lbrain(request):
    cfg = Config()
    cfg.perception.map_id = 42
    cfg.perception.loot_by_sight = True
    if request.param == "exact":
        cfg.humanize.jitter = 0.0
    else:
        cfg.humanize.seed = request.param
    return Brain(cfg)


def _sight_walk(b, t, drops, max_t=12.0, sticky=(), slide=True, mobs_at=None, picked=None, taps=None, hide=20,
                start=0.0, appear=1.1, state=None, walk_pickup=True, keep=False):
    """Feed ticks while the brain loots by sight. `drops`: ground positions (px, relative to where we start).
    We see a drop unless our body covers it (within 20 px). Z picks up one drop within 30 px; `walk_pickup`
    False: only standing still (one live observation: Z while walking over a coin did nothing; the user says
    players pick up while walking). `sticky`: drops that never come up (not pick-up-able).
    `taps`: collects (pos, standing_still) per Z. `mobs_at`: (t_from, dx) a mob shows up next to us then."""
    drops = list(drops)
    held, pos, walk_ticks, slide_left, last_dir = None, start, 0, 0.0, 1
    while (b.mode == "LOOT" or keep) and t < max_t:          # keep: on through SEEK (and back to LOOT)
        move = 6.0 if held == "right" else -6.0 if held == "left" else 0.0
        if held in ("left", "right"):
            walk_ticks, last_dir = walk_ticks + 1, (1 if held == "right" else -1)
        elif slide and walk_ticks:
            slide_left, walk_ticks = (16.0 if walk_ticks * 0.05 >= 0.4 else 8.0), 0
        if held is None and slide_left > 0:
            step = min(slide_left, 6.0)
            slide_left -= step
            move = step * last_dir
        pos += move
        seen = [d for d in drops if abs(d - pos) >= hide] if t >= appear else []    # after the death animation
        o = obs(t, exp=0.25, dot=(100.0 + pos / 15, 90.0), scene_dx=-move,
                lib=[mob(mobs_at[1])] if mobs_at and t >= mobs_at[0] else ())
        o.drops = [(int(PX + d - pos - 12), int(FEET - 26), 24, 24) for d in seen]
        for a in b.step(o):
            if isinstance(a, Hold):
                held = a.key
            elif isinstance(a, Release) or (isinstance(a, Tap) and a.key in ("left", "right")):
                held = None
            if isinstance(a, Tap) and a.key == PICKUP:
                still = held not in ("left", "right") and slide_left == 0
                if taps is not None:
                    taps.append((pos, still))
                near = [d for d in drops if abs(d - pos) <= 30 and d not in sticky]
                if (still or walk_pickup) and near:
                    d = min(near, key=lambda d: abs(d - pos))
                    drops.remove(d)
                    if picked is not None:
                        picked.append(d)
        t += 0.05
    if state is not None:
        state["pos"] = pos
    return drops, t


def _sight_kill(b, dx=60):
    assert any(isinstance(a, Track) for a in b.step(obs(0.0, lib=[mob(dx)])))
    b.step(obs(0.1, target=mob(dx), target_bar=True, bar=[mob(dx)]))
    b.step(obs(0.2, exp=0.25))                                                   # killed
    assert b.mode == "LOOT"
    return 0.25


def test_sight_walks_through_drops_spamming_z_on_the_way(lbrain):
    """The user: 'they pick up loot while walking at every opportunity, spamming a few Zs when they pass the
    item' - no full stop on every item."""
    taps, picked = [], []
    left, _ = _sight_walk(lbrain, _sight_kill(lbrain), [60, 95], taps=taps, picked=picked, keep=True, max_t=4.0)
    assert left == [] and sorted(picked) == [60, 95] and lbrain.mode == "SEEK"
    assert not taps[0][1] and lbrain.stats["walk_pickups"] >= 1                 # picked up on the move
    tm = lbrain.cfg.timing
    assert tm.pass_taps_min <= len(taps) <= 2 * tm.taps_cap   # a burst (one burst can catch two close items)
    assert lbrain.stats["loot_gave_up"] == 0


def test_sight_a_pile_of_drops_gets_a_full_stop(lbrain):
    """The user: 'when there is a large amount of loot in one spot they fully stop to pick everything up'."""
    taps, picked = [], []
    _sight_walk(lbrain, _sight_kill(lbrain), [60, 70, 80], taps=taps, picked=picked)
    assert sorted(picked) == [60, 70, 80]
    assert sum(still for _, still in taps) >= 2                # one full stop on the pile (2-4 presses)


def test_sight_walking_past_a_drop_keeps_the_walk_key_down_and_spams_z_briefly(lbrain):
    """Z presses while walking past: 3-5 within ~0.3-0.65 s (varied), never a Release in between."""
    b, t, acts_all = lbrain, 0.0, []
    for i in range(30):                                                         # SEEK idle walk, a drop ahead
        o = obs(t, scene_dx=-6.0 if b.held else 0.0)
        o.drops = [(int(PX + 40 - 6 * i - 12), int(FEET - 26), 24, 24)] if 40 - 6 * i > -40 else []
        acts_all.append((t, b.step(o)))
        t += 0.05
    zs = [tt for tt, acts in acts_all for a in acts if a == Tap(PICKUP, b.cfg.timing.pickup_press_s)]
    tm = b.cfg.timing
    assert tm.pass_taps_min <= len(zs) <= tm.pass_taps_max
    assert zs[-1] - zs[0] <= longest(b, tm.pass_window_max_s) + 0.06
    first, last = zs[0], zs[-1]
    assert not any(isinstance(a, Release) for tt, acts in acts_all if first <= tt <= last for a in acts)


def test_sight_no_drop_seen_means_no_z_at_all(lbrain):
    """The user: a player presses Z when they *see* an item. pkg_human5m: 42 Z per kill, mostly on empty ground."""
    taps = []
    _, t = _sight_walk(lbrain, _sight_kill(lbrain, dx=60), [], taps=taps)
    tm = lbrain.cfg.timing
    assert taps == [] and lbrain.mode == "SEEK"
    assert t < 0.25 + longest(lbrain, tm.drop_delay_s) + longest(lbrain, tm.drop_look_s) + 0.15


def test_sight_mob_died_at_our_feet_gets_one_burst_where_we_stand(lbrain):
    """Drops right under us hide behind our own body: like a player, spam Z a few times where we stand."""
    taps, picked = [], []
    _sight_walk(lbrain, _sight_kill(lbrain, dx=30), [5], taps=taps, picked=picked)
    tm = lbrain.cfg.timing
    assert picked == [5] and tm.drop_taps_min <= len(taps) <= tm.drop_taps_max and all(abs(p) < 1 for p, _ in taps)


def test_sight_burst_length_and_gaps_vary_like_a_player():
    lens = set()
    for seed in range(1, 9):
        cfg = Config()
        cfg.perception.map_id, cfg.humanize.seed = 42, seed
        cfg.perception.loot_by_sight = True
        b, taps = Brain(cfg), []
        _sight_walk(b, _sight_kill(b), [60], taps=taps, keep=True, max_t=4.0)
        lens.add(len(taps))
    tm = Config().timing
    assert lens <= set(range(tm.pass_taps_min, tm.pass_taps_max + 1)) and len(lens) >= 2


def test_sight_walking_pickup_that_does_nothing_falls_back_to_stopping_on_it(lbrain):
    """If Z while walking doesn't pick it up (one live observation said so): it's still there -> stop on it."""
    taps, picked = [], []
    _sight_walk(lbrain, _sight_kill(lbrain), [60], taps=taps, picked=picked, walk_pickup=False, keep=True,
                max_t=6.0)
    assert picked == [60] and any(still for _, still in taps)


def test_sight_a_drop_that_wont_come_up_is_tried_twice_then_left_alone(lbrain):
    """Still in sight after the burst (a big item our body doesn't cover): one more burst, then give up."""
    taps = []
    left, t = _sight_walk(lbrain, _sight_kill(lbrain), [60], sticky=(60,), taps=taps, hide=0, keep=True, max_t=9.0)
    assert left == [60] and lbrain.mode == "SEEK" and lbrain.stats["loot_gave_up"] == 1
    tm = lbrain.cfg.timing
    assert 3 * tm.drop_taps_min <= len(taps) <= 3 * tm.taps_cap   # walking past, then 2 bursts standing on it


def test_sight_a_drop_hidden_under_us_that_wont_come_up_is_not_visited_forever(lbrain):
    """Standing on it our body hides it ('gone' = picked up?); seen again from a step away -> back for it; after
    the second burst there it's left alone, not a Z loop."""
    taps, t, st = [], _sight_kill(lbrain), {"pos": 0.0}
    for _ in range(4):
        _sight_walk(lbrain, t, [60], sticky=(60,), taps=taps, start=st["pos"], state=st, appear=0.0)
        t += 3.0
        lbrain.step(obs(t, exp=0.25, scene_dx=50.0))           # walked 50 px off it (left)
        st["pos"] -= 50.0
        t += 0.05
        o = obs(t, exp=0.25)                                   # in sight again, 50 px to our right
        o.drops = [(int(PX + 60 - st["pos"] - 12), int(FEET - 26), 24, 24)]
        lbrain.step(o)
        if lbrain.mode != "LOOT":
            break
        t += 0.05
    assert len(taps) <= 4 * lbrain.cfg.timing.taps_cap and lbrain.mode != "LOOT"   # walk-bys + 2 stops, then left


def test_sight_seeing_drops_with_no_mob_around_goes_for_them_instead_of_wandering(lbrain):
    """Drops left over (we were fighting elsewhere) are collected when nothing is there to fight."""
    o = obs(0.0)
    o.drops = [(int(PX + 80 - 12), int(FEET - 26), 24, 24)]
    lbrain.step(o)
    assert lbrain.mode == "LOOT"
    picked = []
    _sight_walk(lbrain, 0.05, [80], picked=picked, appear=0.0)
    assert picked == [80]


def test_sight_a_mob_coming_into_reach_interrupts_the_looting(lbrain):
    left, _ = _sight_walk(lbrain, _sight_kill(lbrain), [115], mobs_at=(1.5, -50))      # mid-walk to it
    assert lbrain.mode == "ENGAGE" and left == [115]


def test_sight_a_mob_close_by_comes_before_drops(lbrain):
    o = obs(0.0, lib=[mob(-110)])
    o.drops = [(int(PX + 50 - 12), int(FEET - 26), 24, 24)]
    assert any(isinstance(a, Track) for a in lbrain.step(o))


def test_sight_a_mob_fighting_us_comes_before_drops_even_from_afar(lbrain):
    o = obs(0.0, bar=[mob(-200)])
    o.drops = [(int(PX + 50 - 12), int(FEET - 26), 24, 24)]
    assert any(isinstance(a, Track) for a in lbrain.step(o))


def test_sight_drops_next_to_us_come_before_a_far_mob(lbrain):
    """pkg_sight2 41.0 s / 183.2 s: a drop 4-7 px away, and we walked ~500 px to a far Shroom instead (the user:
    'completely ignored coins and items where in other cases they are picked up'). On a crowded map some mob is
    almost always in sight."""
    o = obs(0.0, lib=[mob(-500)])
    o.drops = [(int(PX + 50 - 12), int(FEET - 26), 24, 24)]
    acts = lbrain.step(o)
    assert lbrain.mode == "LOOT" and not any(isinstance(a, Track) for a in acts)
    picked = []
    _sight_walk(lbrain, 0.05, [50], picked=picked, appear=0.0)
    assert picked == [50]


def test_sight_walking_into_a_wall_without_a_minimap_gives_up_fast(lbrain):
    """pkg_sight1 130 s: the inventory window covered the minimap (no dot for 93 % of ticks); we held left at a
    'drop' behind a step for 5 s without moving. Holding a walk key without moving = blocked, minimap or not."""
    o = obs(0.0, dot=None)
    o.drops = [(int(PX - 60 - 12), int(FEET - 26), 24, 24)]
    lbrain.step(o)
    assert lbrain.mode == "LOOT"
    t, walked = 0.05, 0.0
    while lbrain.mode == "LOOT" and t < 6.0:
        o = obs(t, dot=None, scene_dx=0.0)                    # we don't move: a wall
        o.drops = [(int(PX - 60 - 12), int(FEET - 26), 24, 24)]
        lbrain.step(o)
        t += 0.05
    # one jump first (a step?), then the block timer once more
    assert lbrain.mode == "SEEK" and t < 2 * longest(lbrain, lbrain.cfg.timing.blocked_s) + 0.6
    assert lbrain.stats["blocked"] == 1 and lbrain.stats["block_jumps"] == 1


def test_sight_a_drop_below_our_floor_is_not_walked_to(lbrain):
    """pkg_sight3: 'drops' in the dirt under our feet (chat scrolling); we stood on them pressing Z, 18 times."""
    o = obs(0.0)
    o.drops = [(int(PX + 30 - 12), int(FEET + 16), 24, 30)]
    lbrain.step(o)
    assert lbrain.mode != "LOOT"


def test_sight_walking_bursts_vary_in_presses_gaps_and_total_time():
    """The user: 'make the bursts humanized: the amount of presses, the time between presses, the total time to
    perform all the presses per attempt should have variation'."""
    counts, totals, gaps = set(), [], []
    for seed in range(1, 13):
        cfg = Config()
        cfg.perception.map_id, cfg.humanize.seed, cfg.perception.loot_by_sight = 42, seed, True
        b, t, zs = Brain(cfg), 0.0, []
        for i in range(40):                                                     # walking past one drop
            o = obs(t, scene_dx=-6.0 if b.held else 0.0)
            o.drops = [(int(PX + 40 - 6 * i - 12), int(FEET - 26), 24, 24)] if 40 - 6 * i > -40 else []
            if any(isinstance(a, Tap) and a.key == PICKUP for a in b.step(o)):
                zs.append(t)
            t += 0.05
        counts.add(len(zs))
        totals.append(round(zs[-1] - zs[0], 2))
        gaps += [round(y - x, 2) for x, y in zip(zs, zs[1:])]
    tm = Config().timing
    assert counts <= set(range(tm.pass_taps_min, tm.pass_taps_max + 1)) and len(counts) >= 2
    assert len(set(totals)) >= 4 and max(totals) <= tm.pass_window_max_s * 1.25 + 0.1
    assert len(set(gaps)) >= 4


def test_sight_more_presses_when_several_drops_lie_together(lbrain):
    """pkg_sight4: 'the amount of presses is too low, many items were missed' - one press picks up one item, so a
    coin next to a spore needs more. +1 press per other drop lying next to it."""
    def burst(drops_at):
        cfg = Config()
        cfg.perception.map_id, cfg.perception.loot_by_sight, cfg.humanize.jitter = 42, True, 0.0
        b, t, n = Brain(cfg), 0.0, 0
        for i in range(40):
            o = obs(t, scene_dx=-6.0 if b.held else 0.0)
            o.drops = [(int(PX + d - 6 * i - 12), int(FEET - 26), 24, 24) for d in drops_at if d - 6 * i > -40]
            n += sum(isinstance(a, Tap) and a.key == PICKUP for a in b.step(o))
            t += 0.05
        return n
    assert burst([40, 55]) == burst([40]) + 1


def test_sight_no_mob_around_far_drops_are_collected(lbrain):
    """The user: 'when there are no mobs around a player would then prioritize getting loot'."""
    o = obs(0.0)
    o.drops = [(int(PX + 400 - 12), int(FEET - 26), 24, 24)]
    lbrain.step(o)
    assert lbrain.mode == "LOOT"


def test_sight_far_drops_wait_while_mobs_are_around(lbrain):
    o = obs(0.0, lib=[mob(-500)])
    o.drops = [(int(PX + 400 - 12), int(FEET - 26), 24, 24)]
    acts = lbrain.step(o)
    assert any(isinstance(a, Track) for a in acts)


def _hit_without_bar(b, src, until):
    """Engage a mob at +60 and swing at it with no HP bar ever showing; `src` = how perception finds it."""
    box = mob(60)
    b.step(Observation(t=0.0, me=(PX, FEET), exp_points=2000, dot=(100.0, 90.0), known_mobs=[box], sprite_mobs=[box]))
    t, gone_at = 0.05, None
    while t < until:
        o = obs(t, target=box)
        o.target_src = src
        b.step(o)
        if b.mode != "ENGAGE" and gone_at is None:
            gone_at = t
        t += 0.05
    return gone_at


def test_sprite_mode_keeps_hitting_a_seen_mob_whose_hp_bar_fog_hides(sbrain):
    """perion2/3: Perion's fog washes out the HP bar; 14 own Stumps were left after ~1.1 s ('no HP bar for us')
    with our damage numbers on them. Sprite mode doesn't use bars: a mob is hit until it dies or is gone."""
    assert _hit_without_bar(sbrain, "sprite", 4.0) is None


def test_sight_a_mob_in_sight_beats_walking_to_a_far_drop(lbrain):
    """perion4 12-15 s: walked 555 px to a drop past a Stump in sight. Mobs first (drops are private: they wait)."""
    t = _sight_kill(lbrain)
    _sight_walk(lbrain, t, [400], mobs_at=(t + 1.3, -250), max_t=t + 3.0)
    assert lbrain.mode == "ENGAGE" and lbrain.target.rel_dx < -150


def test_sight_a_drop_at_our_feet_is_still_taken_before_a_mob(lbrain):
    t = _sight_kill(lbrain)
    picked = []
    _sight_walk(lbrain, t, [40], mobs_at=(t + 1.15, -250), picked=picked, max_t=t + 3.0)
    assert picked == [40]


def test_sprite_mode_a_mob_where_another_just_died_is_taken_at_once(sbrain):
    """perion5 49 s / 73 s: a Stump walking near where another player's kill died was in its 'drop zone' and
    ignored ~0.4-0.8 s ('no mobs in sight -> walking'). A sprite match is a live mob, never a drop."""
    _hitting(sbrain)
    t = 0.25
    while sbrain.mode == "ENGAGE" and t < 2.0:
        sbrain.step(dying(t))                                                # someone else's kill, no EXP
        t += 0.05
    assert sbrain.stats["others_kills"] == 1
    acts = sbrain.step(obs(t + 0.3, lib=[mob(75)]))                          # a new Stump right there
    assert Track(mob(75)) in acts


def test_sprite_mode_mobs_up_to_the_wider_leash_are_fair(sbrain):
    """perion5 118-120 s: 55 minimap px from the start, Stumps to the right were off-limits (leash 60)."""
    sbrain.step(obs(0.0, dot=(100.0, 90.0)))
    for i in range(1, 12):                                                   # a steady start reading
        sbrain.step(obs(i * 0.1, dot=(100.0, 90.0)))
    sbrain.mode, sbrain.idle_walk_until = "SEEK", None
    acts = sbrain.step(obs(1.5, dot=(155.0, 90.0), lib=[mob(150)]))
    assert Track(mob(150)) in acts


def test_a_few_exp_points_are_a_kill_even_when_the_bar_does_not_move(sbrain):
    """perion6 46.2 s: our 147 hit one-shot a Stump; the EXP bar (1 px = ~15 points) didn't move, the kill was
    taken for another player's ('death animation, no EXP') and its drop left. Points 882 -> 885 = our kill."""
    box = mob(60)
    o = Observation(t=0.0, me=(PX, FEET), exp_points=5000, dot=(100.0, 90.0), known_mobs=[box], sprite_mobs=[box])
    o.exp_points = 882
    sbrain.step(o)
    for i, pts in enumerate((882, 885)):
        o = obs(0.1 + i * 0.05, exp=0.50)                                    # bar unchanged; its sprite gone
        o.exp_points = pts
        o.target_dying = True
        sbrain.step(o)
    assert sbrain.stats["kills"] == 1 and sbrain.stats["others_kills"] == 0 and sbrain.mode == "LOOT"


def test_exp_points_dropping_is_a_level_up_kill(sbrain):
    """The user: EXP number down instead of up (e.g. 10000 -> 3) = a level-up - the kill that did it."""
    box = mob(60)
    sbrain.step(Observation(t=0.0, me=(PX, FEET), exp_points=10000, dot=(100.0, 90.0), known_mobs=[box],
                            sprite_mobs=[box]))
    o = obs(0.1)
    o.exp_points = 3
    sbrain.step(o)
    assert sbrain.stats["kills"] == 1 and sbrain.stats["level_ups"] == 1 and sbrain.mode == "LOOT"


def test_unreadable_exp_points_never_make_a_kill(sbrain):
    box = mob(60)
    sbrain.step(Observation(t=0.0, me=(PX, FEET), exp_points=500, dot=(100.0, 90.0), known_mobs=[box],
                            sprite_mobs=[box]))
    o = obs(0.1, target=box)
    o.exp_points, o.target_src = None, "sprite"
    sbrain.step(o)
    assert sbrain.stats["kills"] == 0 and sbrain.mode == "ENGAGE"


def test_a_wide_stump_walking_at_us_gets_the_swing_earlier_than_a_snail(brain):
    """perion7 52.2 s / acc1 27.4 s: zones are centre to centre, measured on 35 px snails; a Stump box is 62 px, so
    its edge is ~13 px nearer - we swung at +59..70 and it walked into us before Power Strike came out. Zones now
    count from the mob's edge."""
    engaged(brain, 0.0, mob(-110, w=62))
    acts, t, dx, first = [], 0.1, -110.0, None
    while t < 1.6 and abs(dx) > 45:
        a = brain.step(obs(t, target=mob(dx, w=62), target_bar=True, bar=[mob(dx, w=62)]))
        if first is None and Hold(ATTACK) in a:
            first = dx
        dx += 45 * 0.05
        t += 0.05
    assert first is not None
    z, tm = brain.cfg.zones, brain.cfg.timing
    assert abs(first) >= z.hit_max + (62 - 35) / 2 + 45 * tm.anticipate_s - 4   # its edge + the lead it walks


def test_a_stump_is_measured_from_its_edge(brain):
    """A 62 px Stump is 13.5 px wider per side than the 35 px snail the zones were measured on."""
    engaged(brain, 0.0, mob(-300, w=62))
    assert brain.target.wide == pytest.approx(13.5, abs=1)
    brain.step(obs(0.1, target=mob(-290, w=35)))
    assert brain.target.wide == 0


def test_a_target_hidden_in_reach_is_hit_longer_than_one_seen_leaving(sbrain):
    """acc1 38-39.6 s: our Dark Stump stood against us, covered by our body and another player (its HP bar and our
    damage numbers showed); we called it gone after 1 s and it died to our hits 0.5 s later."""
    b = sbrain
    assert Track(mob(-55)) in b.step(obs(0.0, lib=[mob(-55)]))
    t = 0.05
    while t < 0.6:
        b.step(obs(t, target=mob(-55), target_bar=True, bar=[mob(-55)]))
        t += 0.05
    gone_at = t
    while t < gone_at + 1.4:
        acts = b.step(obs(t))
        t += 0.05
    assert b.mode == "ENGAGE" and not any("target gone" in e for e in b.events)


# ---------------------------------------------------------------- session 16 (runs/manual/20261102_144214_2): Meat
# raised HP +3 % only 0.6-0.8 s after the press (verify was 0.7 s) -> a working press counted as a miss, one real
# miss later -> "used up" -> stopped at 45 % HP with 49 Meat in the slot
def test_a_slow_potion_still_counts_as_working(brain):
    t = 0.0
    brain.step(pobs(t, hp=0.495))
    while t < 2.0:
        t += 0.05
        brain.step(pobs(t, hp=0.495 if t < 0.8 else 0.695))
    assert brain.potion_fails.get("HP", 0) == 0 and "HP" not in brain.potions_out


def test_used_up_hp_potions_get_one_last_press_before_the_stop(brain):
    brain.potions_out["HP"] = 1000.0                          # wrongly judged used up, next probe far away
    acts = brain.step(pobs(10.0, hp=0.44))
    assert Tap(HP_POTION, brain.cfg.timing.potion_press_s) in acts and not any(isinstance(a, Stop) for a in acts)
    t = 10.0
    while t < 12.0:                                          # it works -> potions back, no stop
        t += 0.05
        acts = brain.step(pobs(t, hp=0.44 if t < 10.7 else 0.64))
        assert not any(isinstance(a, Stop) for a in acts)
    assert "HP" not in brain.potions_out


def test_really_no_hp_potions_still_stops_after_the_last_press(brain):
    brain.potions_out["HP"] = 1000.0
    brain.step(pobs(10.0, hp=0.44))
    t, stopped = 10.0, False
    while t < 13.0 and not stopped:
        t += 0.05
        stopped = any(isinstance(a, Stop) for a in brain.step(pobs(t, hp=0.44)))
    assert stopped


# ---------------------------------------------------------------- session 16: crowded floors (rest10m_b: engaged
# at >= 200 px -> 3 kills of 48, other bots got there first; 86 target switches in 238 engagements)
def _contest(brain, t=0.0):
    for i in range(brain.cfg.timing.crowd_losses):
        brain._lost_one(obs(t + i * 0.1))
    assert brain.contested


def test_contested_no_far_chases(brain):
    _contest(brain)
    brain.step(obs(1.0, lib=[mob(-350)]))
    assert brain.mode == "SEEK"                                            # too far: someone else's by then
    acts = brain.step(obs(1.1, lib=[mob(-350), mob(150)]))
    assert brain.mode == "ENGAGE" and Track(mob(150)) in acts            # a near one is still fought


def test_far_mobs_are_fine_when_not_contested(brain):
    brain._lost_one(obs(0.0))                                             # one loss isn't a crowd
    acts = brain.step(obs(1.0, lib=[mob(-350)]))
    assert brain.mode == "ENGAGE" and Track(mob(-350)) in acts


def test_contested_ages_out(brain):
    _contest(brain)
    brain.step(obs(brain.cfg.timing.crowd_window_s + 1.0))
    assert not brain.contested
    brain.step(obs(brain.cfg.timing.crowd_window_s + 1.1, lib=[mob(-350)]))
    assert brain.mode == "ENGAGE"


def test_a_mob_a_little_closer_doesnt_steal_the_target(brain):
    engaged(brain, 0.0, mob(-200))
    brain.step(obs(0.1, target=mob(-200)))
    acts = brain.step(obs(2.0, target=mob(-190), lib=[mob(170)]))        # 20 px closer: not worth turning around
    assert brain.stats["closer_switches"] == 0 and Track(mob(170)) not in acts


# ---------------------------------------------------------------- session 16: exact MP from the HUD text. The skill's
# cost is measured from the number; Power Strike was held at 17/359 MP without firing (101 ticks)
def _mp_tick(b, t, mp_now, mp_max=359):
    o = pobs(t, mp=mp_now / mp_max, target=mob(-60), target_bar=True, bar=[mob(-60)])
    o.mp_now, o.mp_max = mp_now, mp_max
    return b.step(o)


def test_skill_cost_is_measured_and_the_plain_attack_comes_below_one_cast(brain):
    engaged(brain, 0.0, mob(-60))
    t, mp = 0.1, 60
    assert _mp_tick(brain, t, mp)[-1] == Hold(ATTACK)
    for _ in range(2):                                            # two casts of 19 MP each
        t += 0.8; mp -= 19
        _mp_tick(brain, t, mp)
    assert brain.skill_cost == 19 and mp == 22
    t += 0.8; mp -= 19                                            # 3 MP left: less than a cast
    assert _mp_tick(brain, t, mp)[-1] == Hold(BASIC)
    assert _mp_tick(brain, t + 5.0, 18)[-1] == Hold(BASIC)          # regen to 18: still short of 19
    assert _mp_tick(brain, t + 9.0, 19)[-1] == Hold(ATTACK)      # enough for a cast: the skill again


def test_skill_that_isnt_firing_is_noticed_without_a_known_cost(brain):
    engaged(brain, 0.0, mob(-60))
    t = 0.1
    acts = _mp_tick(brain, t, 17)
    assert acts[-1] == Hold(ATTACK)                              # 4.7 %: above the old 2.5 % share threshold
    while t < 2.5 and brain.attack_key == ATTACK:
        t += 0.1
        acts = _mp_tick(brain, t, 17)
    assert brain.attack_key == BASIC and brain.skill_min_mp == 18 and t <= 0.1 + 1.5 * 1.3
    assert _mp_tick(brain, t + 3.0, 17)[-1] == Hold(BASIC)
    assert _mp_tick(brain, t + 6.0, 18)[-1] == Hold(ATTACK)


def test_mp_dropping_while_not_holding_the_skill_isnt_a_cast(brain):
    o = pobs(0.0, mp=100 / 359); o.mp_now, o.mp_max = 100, 359
    brain.step(o)
    o = pobs(0.1, mp=80 / 359); o.mp_now, o.mp_max = 80, 359
    brain.step(o)
    assert brain.skill_cost == 0
