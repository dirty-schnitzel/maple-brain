"""python -m maplebot run <out_dir> [--seconds 60] [--attack KEY] [--jump shift]
   python -m maplebot assets build [--export DIR]   (game data from the client export, see assets/README.md)

Must run elevated (the game is elevated; Windows drops simulated keys from a lower-integrity process).
"""
import argparse
import sys
from pathlib import Path

from .config import Combat, Keys, Perception


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="maplebot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="hunt live (elevated)")
    r.add_argument("out", type=Path)
    r.add_argument("--seconds", type=float, default=60)
    r.add_argument("--attack", default=Keys.attack)
    r.add_argument("--basic-attack", default=Keys.basic_attack, help="plain attack used while out of MP and MP potions")
    r.add_argument("--jump", default=Keys.jump)
    r.add_argument("--pickup", default=Keys.pickup)
    r.add_argument("--hp-stop", type=float, default=0.45)
    r.add_argument("--map", type=int, default=None, help="Classic World map id (42 = Snail Hunting Ground III); "
                   "default: recognised from the minimap at the start")
    r.add_argument("--loot", action="store_true", help="pick up drops (off: a pet does it)")
    r.add_argument("--loot-sight", action="store_true", help="experimental: loot what's seen on the ground")
    r.add_argument("--gpu", action="store_true", help="find mobs on the GPU (whole screen; needs torch + CUDA)")
    r.add_argument("--tracker", action="store_true", help="the brain uses the tracker's tracks (needs --gpu)")
    r.add_argument("--brain", choices=["v1", "v2"], default="v1", help="v2 = brain-v2 combat (implies --gpu)")
    r.add_argument("--weapon", default=Combat.weapon, help="brain v2: weapon type for the reach (poleArm, spear, ...)")
    r.add_argument("--attack-speed", type=int, default=None, help="brain v2: the weapon's attackSpeed, sets the swing "
                   "length (default: the usual one for the type in the client data; a Booster takes 2 off)")
    r.add_argument("--mob-score", type=float, default=None, help="a new mob needs a sighting this good (default "
                   f"{Perception.sprite_score}); mobs already tracked are followed at any score")
    r.add_argument("--no-focus", action="store_true", help="don't bring the game to front; wait for you to")
    r.add_argument("--frames-every", type=int, default=3, help="save every Nth frame (1 = all, for tracker tests)")
    v = sub.add_parser("serve", help=f"stay loaded; {Keys.start.upper()} starts hunting, {Keys.stop.upper()} stops (elevated, game focused)")
    v.add_argument("out", type=Path, nargs="?", default=Path("runs/manual"), help="one folder per hunt in here")
    v.add_argument("--attack", default=Keys.attack)
    v.add_argument("--basic-attack", default=Keys.basic_attack, help="plain attack used while out of MP and MP potions")
    v.add_argument("--jump", default=Keys.jump)
    v.add_argument("--pickup", default=Keys.pickup)
    v.add_argument("--hp-stop", type=float, default=0.45)
    v.add_argument("--map", type=int, default=None, help="fix the map; default: recognised from the minimap on every start")
    v.add_argument("--loot", action="store_true", help="pick up drops (off: a pet does it)")
    v.add_argument("--loot-sight", action="store_true", help="experimental: loot what's seen on the ground")
    v.add_argument("--gpu", action="store_true", help="find mobs on the GPU (whole screen; needs torch + CUDA)")
    v.add_argument("--tracker", action="store_true", help="the brain uses the tracker's tracks (needs --gpu)")
    v.add_argument("--brain", choices=["v1", "v2"], default="v1", help="v2 = brain-v2 combat (implies --gpu)")
    v.add_argument("--weapon", default=Combat.weapon, help="brain v2: weapon type for the reach (poleArm, spear, ...)")
    v.add_argument("--attack-speed", type=int, default=None, help="brain v2: the weapon's attackSpeed, sets the swing "
                   "length (default: the usual one for the type in the client data; a Booster takes 2 off)")
    v.add_argument("--mob-score", type=float, default=None, help="a new mob needs a sighting this good (default "
                   f"{Perception.sprite_score}); mobs already tracked are followed at any score")
    v.add_argument("--start-key", default=Keys.start)
    v.add_argument("--stop-key", default=Keys.stop)
    v.add_argument("--frames", action="store_true", help="also save every 3rd frame (~50 MB per 10 min)")
    v.add_argument("--frames-every", type=int, default=None, help="save every Nth frame (implies --frames; 1 = all)")
    v.add_argument("--observe", action="store_true", help="record only: you play, the bot presses no keys")
    g = sub.add_parser("goto", help="brain-v2 movement test: travel to a platform, or a tour of random goals "
                       "(elevated; implies --gpu)")
    g.add_argument("out", type=Path)
    g.add_argument("--to", type=float, nargs="+", default=None, metavar=("PLATFORM", "X"),
                   help="one trip to this platform id (and x on it), then stop")
    g.add_argument("--seconds", type=float, default=180)
    g.add_argument("--jump", default=Keys.jump)
    g.add_argument("--hp-stop", type=float, default=0.45)
    g.add_argument("--map", type=int, default=None)
    g.add_argument("--seed", type=int, default=None)
    g.add_argument("--no-focus", action="store_true")
    g.add_argument("--frames-every", type=int, default=3)
    lm = sub.add_parser("livemap", help="console map of the running hunt (tracks; needs --gpu), redrawn in place")
    lm.add_argument("dir", type=Path, nargs="?", default=Path("runs/manual"),
                    help="a run folder, or a folder of hunts (the newest is followed)")
    lm.add_argument("--every", type=float, default=0.3)
    lm.add_argument("--width", type=int, default=None, help="columns (default: the console's)")
    lm.add_argument("--replay", action="store_true", help="play a recorded run back at real speed")
    lm.add_argument("--speed", type=float, default=1.0)
    lm.add_argument("--t0", type=float, default=0.0, help="--replay: start at this second")
    lm.add_argument("--map", type=int, default=None, help="the map id (default: from the hunt logs)")
    w = sub.add_parser("watch", help="no hunt: siren if the Lie Detector shows up (keep running between runs)")
    w.add_argument("out", type=Path, nargs="?", default=Path("runs/watch"))
    w.add_argument("--seconds", type=float, default=4 * 3600)
    s = sub.add_parser("assets", help="rebuild assets/mcw from the client export (tools/cwdata/export.ps1; "
                       "see assets/README.md)")
    s.add_argument("action", choices=["build"])
    s.add_argument("--export", type=Path, default=None, help="the export folder (default: export.ps1's)")
    a = ap.parse_args(argv)
    if a.cmd == "livemap":
        from .livemap import follow, replay
        if a.replay:
            return replay(a.dir, a.speed, a.every, a.width, a.t0, a.map)
        return follow(a.dir, a.every, a.width, a.map)
    if a.cmd == "watch":
        from .runtime.runner import watch
        return watch(a.out, a.seconds)
    if a.cmd == "goto":
        from .config import Config
        from .keyboard import validate
        from .runtime.goto import goto
        validate(a.jump)
        cfg = Config()
        cfg.keys.jump, cfg.safety.hp_stop, cfg.perception.map_id = a.jump, a.hp_stop, a.map
        to = (int(a.to[0]), a.to[1] if len(a.to) > 1 else None) if a.to else None
        return goto(a.out, cfg, a.seconds, to, focus=not a.no_focus, frames_every=a.frames_every, seed=a.seed)
    if a.cmd == "assets":
        from .gamedata import EXPORT, build
        build(a.export or EXPORT)
        return 0
    if a.cmd in ("run", "serve"):
        from .config import Config
        from .keyboard import validate
        from .runtime.runner import VK, run, serve
        for k in (a.attack, a.basic_attack, a.jump, a.pickup):
            validate(k)
        cfg = Config()
        cfg.keys.attack, cfg.keys.jump, cfg.keys.pickup, cfg.safety.hp_stop = a.attack, a.jump, a.pickup, a.hp_stop
        cfg.keys.basic_attack = a.basic_attack
        cfg.perception.map_id = a.map
        cfg.perception.loot = a.loot
        cfg.perception.loot_by_sight = a.loot and a.loot_sight
        cfg.perception.gpu = a.gpu or a.brain == "v2"
        cfg.brain, cfg.combat.weapon, cfg.combat.attack_speed = a.brain, a.weapon, a.attack_speed
        if a.mob_score is not None:
            cfg.perception.sprite_score = a.mob_score
        if a.brain == "v2":
            from .brain.reach import Reach
            try:
                Reach(a.weapon)
            except KeyError as e:
                ap.error(str(e))
        if a.tracker and not a.gpu:
            ap.error("--tracker needs --gpu")
        cfg.perception.tracker = a.tracker
        if a.cmd == "run":
            return run(a.out, a.seconds, cfg, focus=not a.no_focus, frames_every=a.frames_every)
        for k in (a.start_key, a.stop_key):
            if k not in VK:
                ap.error(f"hotkeys must be F1-F12, got {k!r}")
        cfg.keys.start, cfg.keys.stop = a.start_key, a.stop_key
        every = a.frames_every if a.frames_every is not None else (3 if a.frames else 0)
        return serve(a.out, cfg, frames=every, observe=a.observe)
    return 2


if __name__ == "__main__":
    sys.exit(main())
