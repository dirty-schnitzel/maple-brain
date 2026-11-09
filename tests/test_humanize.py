"""No fixed intervals between actions: press lengths, pauses and waits are all randomized (bot-detection)."""
import maplebrain.keyboard as keyboard
from maplebrain.brain.actions import Tap
from maplebrain.brain.brain import Brain
from maplebrain.config import Config, Humanize
from maplebrain.humanize import Humanizer

from test_brain import PICKUP, mob, obs


def test_vary_stays_within_the_jitter_band_and_is_never_constant():
    hz = Humanizer(0.2, seed=7)
    xs = [hz.vary(0.3) for _ in range(500)]
    assert all(0.24 <= x <= 0.36 for x in xs)
    assert len({round(x, 6) for x in xs}) > 450
    assert 0.29 < sum(xs) / len(xs) < 0.31                                  # centred on the nominal value


def test_jitter_zero_is_exact():
    assert Humanizer(0.0).vary(0.3) == 0.3


def _fake_keyboard(monkeypatch):
    sent, sleeps = [], []
    monkeypatch.setattr(keyboard, "_send", lambda k, up: sent.append((k, up)))
    monkeypatch.setattr(keyboard.time, "sleep", lambda s: sleeps.append(s))
    kb = keyboard.Keyboard(hwnd=1, hcfg=Humanize(seed=3))
    monkeypatch.setattr(kb, "focused", lambda: True)
    return kb, sent, sleeps


def test_keyboard_taps_never_repeat_the_same_timing(monkeypatch):
    kb, _, sleeps = _fake_keyboard(monkeypatch)
    for _ in range(20):
        kb.tap("z", down_s=0.06)
    react, down, gap = sleeps[0::3], sleeps[1::3], sleeps[2::3]
    for xs in (react, down, gap):
        assert len(set(xs)) == len(xs)                                       # all different
    j = Humanize().jitter
    assert all(0.06 * (1 - j) - 1e-9 <= d <= 0.06 * (1 + j) + 1e-9 for d in down)
    assert all(0.005 <= r <= 0.030 for r in react)


def test_holding_a_key_does_not_add_a_reaction_pause_on_every_repeat(monkeypatch):
    kb, sent, sleeps = _fake_keyboard(monkeypatch)
    for _ in range(5):
        kb.down("space")                                                     # a hold re-sends key-down each tick
    assert len(sleeps) == 1 and sent.count(("space", False)) == 5


def test_brain_pickup_presses_have_varied_spacing():
    cfg = Config()
    cfg.humanize.seed = 5
    brain = Brain(cfg)
    brain._go_loot(obs(0.0), 5, "test", dying=False)
    t, z_times = 0.0, []
    while brain.mode == "LOOT" and t < 4:
        if any(isinstance(a, Tap) and a.key == PICKUP for a in brain.step(obs(t))):
            z_times.append(t)
        t += 0.01                                                            # fine ticks: see the real spacing
    gaps = [round(b - a, 2) for a, b in zip(z_times, z_times[1:])]
    assert len(gaps) >= 3 and len(set(gaps)) > 1


def test_step_back_cooldown_differs_each_time():
    cfg = Config()
    cfg.humanize.seed = 11
    brain = Brain(cfg)
    cooldowns = set()
    t = 0.0
    brain._engage(obs(t, moving=[mob(38)]), mob(38), "test")
    for _ in range(6):
        brain.step(obs(t, target=mob(38), target_bar=True))
        cooldowns.add(round(brain.back_cooldown, 4))
        t += 2.0
    assert len(cooldowns) == 6


def test_count_is_a_random_whole_number_in_range():
    hz = Humanizer(0.2, seed=1)
    xs = [hz.count(3, 5) for _ in range(100)]
    assert set(xs) == {3, 4, 5}
    assert Humanizer(0.0).count(3, 5) == 4


# ---------------------------------------------------------------- human-shaped timing (after Lie Detector #2)
def test_vary_is_skewed_like_human_timing():
    """Mostly a little quicker than nominal, a longer tail of slower ones (not symmetric around a fixed centre)."""
    hz = Humanizer(0.25, seed=4, drift=0.0)
    xs = sorted(hz.vary(1.0) for _ in range(4000))
    median = xs[len(xs) // 2]
    assert median < 1.0
    assert (xs[-1] - median) > (median - xs[0])                              # the slow side reaches further


def test_session_tempo_wanders_but_stays_in_band():
    hz = Humanizer(0.25, seed=9)
    xs = [hz.vary(1.0) for _ in range(6000)]
    assert all(0.75 - 1e-9 <= x <= 1.25 + 1e-9 for x in xs)
    means = [sum(xs[i:i + 1000]) / 1000 for i in range(0, 6000, 1000)]
    assert max(means) - min(means) > 0.02                                    # fresher / slower stretches


def _step_backs(seed, n=40):
    """n separate 'snail walks into us' moments; returns (back-step Taps, skipped count, ticks from step to turn)."""
    cfg = Config()
    cfg.humanize.seed = seed
    brain = Brain(cfg)
    steps, settle_ticks = [], []
    t = 0.0
    for _ in range(n):
        t += 3.0                                                             # past the cooldown each time
        brain.mode, brain.target = "SEEK", None                              # a new snail each time
        brain._engage(obs(t, moving=[mob(60)]), mob(60), "test")
        t += 0.05
        brain.step(obs(t, target=mob(60), target_bar=True))
        t += 0.05
        acts = brain.step(obs(t, target=mob(-30), target_bar=True))
        back = [a for a in acts if isinstance(a, Tap) and a.key == "right"]
        if back:
            steps.append(back[0])
            k = 0
            while True:                                                      # ticks until it turns back to the mob
                k += 1
                t += 0.02
                a2 = brain.step(obs(t, target=mob(-50), target_bar=True))
                if any(isinstance(a, Tap) and a.key == "left" for a in a2) or k > 50:
                    break
            settle_ticks.append(k)
        else:
            brain.step(obs(t + 0.05, target=mob(-50), target_bar=True))
    return steps, n - len(steps), settle_ticks


def test_step_backs_vary_in_length_and_in_the_pause_before_turning_back():
    """Lie Detector #2 run: 256 step-backs in 31 min, all a 0.3 s step + an instant 35 ms turn."""
    steps, skipped, settle = _step_backs(seed=21)
    tm = Config().timing
    assert len({s.secs for s in steps}) == len(steps) and len(steps) >= 20    # every step a different length
    assert all(tm.back_min_s <= s.secs <= tm.back_max_s for s in steps)
    assert len(set(settle)) >= 3 and min(settle) >= 2                         # never an instant turn


def test_some_step_backs_are_skipped_most_are_not():
    _, skipped, _ = _step_backs(seed=5, n=80)
    assert 2 <= skipped <= 30
