"""python -m maplebrain run <out_dir> [--seconds 60] [--attack KEY] [--jump shift]
   python -m maplebrain record [OUT]                  (you play, everything is recorded as lossless video; PLAN-data.md)
   python -m maplebrain assets build [--export DIR]   (game data from the client export, see assets/README.md)

Must run elevated (the game is elevated; Windows drops simulated keys from a lower-integrity process).
"""
import argparse
import sys
from pathlib import Path

from .config import Combat, Keys, corpus_root


VIDEO_HELP = ("every frame into a lossless video in the run folder (frames_0000.mkv ..., ~0.2-0.7 GB a minute) "
              "instead of frame files; with --frames-png the PNG files are written too")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="maplebrain")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="hunt live (elevated)")
    r.add_argument("out", type=Path)
    r.add_argument("--seconds", type=float, default=60)
    r.add_argument("--attack", default=Keys.attack)
    r.add_argument("--basic-attack", default=Keys.basic_attack, help="plain attack used while out of MP and MP potions")
    r.add_argument("--jump", default=Keys.jump)
    r.add_argument("--hp-stop", type=float, default=0.45)
    r.add_argument("--map", type=int, default=None, help="Classic World map id (42 = Snail Hunting Ground III); "
                   "default: recognised from the minimap at the start")
    r.add_argument("--weapon", default=Combat.weapon, help="weapon type for the reach (poleArm, spear, ...)")
    r.add_argument("--attack-speed", type=int, default=None, help="the weapon's attackSpeed, sets the swing "
                   "length (default: the usual one for the type in the client data; a Booster takes 2 off)")
    r.add_argument("--no-focus", action="store_true", help="don't bring the game to front; wait for you to")
    r.add_argument("--frames-every", type=int, default=3, help="save every Nth frame (1 = all, for tracker tests)")
    r.add_argument("--frames-png", action="store_true", help="save the frames lossless (PNG, ~1.1 MB each) instead "
                   "of JPEG: reference recordings")
    r.add_argument("--video", action="store_true", help=VIDEO_HELP)
    v = sub.add_parser("serve", help=f"stay loaded; {Keys.start.upper()} starts hunting, {Keys.stop.upper()} stops (elevated, game focused); "
                                     f"between hunts {Keys.mode.upper()} = mode (auto / platform), {Keys.mark.upper()} = mark the platform you stand on")
    v.add_argument("out", type=Path, nargs="?", default=Path("runs/manual"), help="one folder per hunt in here")
    v.add_argument("--attack", default=Keys.attack)
    v.add_argument("--basic-attack", default=Keys.basic_attack, help="plain attack used while out of MP and MP potions")
    v.add_argument("--jump", default=Keys.jump)
    v.add_argument("--hp-stop", type=float, default=0.45)
    v.add_argument("--map", type=int, default=None, help="fix the map; default: recognised from the minimap on every start")
    v.add_argument("--weapon", default=Combat.weapon, help="weapon type for the reach (poleArm, spear, ...)")
    v.add_argument("--attack-speed", type=int, default=None, help="the weapon's attackSpeed, sets the swing "
                   "length (default: the usual one for the type in the client data; a Booster takes 2 off)")
    v.add_argument("--start-key", default=Keys.start)
    v.add_argument("--stop-key", default=Keys.stop)
    v.add_argument("--frames", action="store_true", help="also save every 3rd frame (~50 MB per 10 min)")
    v.add_argument("--frames-every", type=int, default=None, help="save every Nth frame (implies --frames; 1 = all)")
    v.add_argument("--frames-png", action="store_true", help="save the frames lossless (PNG, ~1.1 MB each, ~3.3 GB "
                   "per 5 min; implies --frames) instead of JPEG: reference recordings")
    v.add_argument("--video", action="store_true", help=VIDEO_HELP)
    v.add_argument("--observe", action="store_true", help="record only: you play, the bot presses no keys")
    c = sub.add_parser("record", help=f"you play, everything the game shows is recorded as lossless video + your keys "
                                      f"(no perception, nothing pressed); {Keys.start.upper()} starts a recording, "
                                      f"{Keys.stop.upper()} ends it (game focused, native 1366x768 window)")
    c.add_argument("out", type=Path, nargs="?", default=None,
                   help="one folder per recording in here (default: the corpus' incoming folder)")
    c.add_argument("--corpus", type=Path, default=None, metavar="DIR",
                   help=f"where the recordings go: the corpus folder, recordings land in DIR\\incoming (default: "
                        f"{corpus_root()} = CORPUS in maplebrain/config.py, or the environment variable MAPLE_CORPUS)")
    c.add_argument("--start-key", default=Keys.start)
    c.add_argument("--stop-key", default=Keys.stop)
    c.add_argument("--note-key", default=Keys.note, help="the marker key: a key the game does not use, pressed when "
                   "something makes you change what you do (its presses are listed per map by the corpus)")
    c.add_argument("--label", action="append", default=[], metavar="NAME", help="a label for what you set out to "
                   "do (exploration, expiry, pickups; give it again for a second label): kept with each recording "
                   "and written into its captures' names, beside the label the tool works out (farming, traveling)")
    g = sub.add_parser("goto", help="brain-v2 movement test: travel to a platform, or a tour of random goals "
                       "(elevated; clean maps, native window)")
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
    lm = sub.add_parser("livemap", help="console map of the running hunt (tracks), redrawn in place")
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
    w.add_argument("--every", type=float, default=1.0, help="seconds between looks (the Lie Detector gives 10+ s)")
    w.add_argument("--gpu", action="store_true", help="match on the GPU (CUDA) instead of the CPU")
    s = sub.add_parser("assets", help="rebuild assets/mcw from the client export (tools/cwdata/export.ps1; "
                       "see assets/README.md)")
    s.add_argument("action", choices=["build", "scene"], help="build: assets/mcw (maps, mobs; in git). scene: the "
                   "scene model's pictures per map -> assets/scene (large, not in git; PLAN-perception.md step 1)")
    s.add_argument("maps", type=int, nargs="*", help="scene: these map ids (default: every map with mob spawns)")
    s.add_argument("--export", type=Path, default=None, help="the export folder (default: export.ps1's)")
    a = ap.parse_args(argv)
    if a.cmd in ("run", "serve", "goto", "watch", "record"):   # beside the game: a background process, else on the slow cores
        from .procperf import prefer_performance
        print(prefer_performance())
    if a.cmd == "livemap":
        from .livemap import follow, replay
        if a.replay:
            return replay(a.dir, a.speed, a.every, a.width, a.t0, a.map)
        return follow(a.dir, a.every, a.width, a.map)
    if a.cmd == "watch":
        from .runtime.runner import watch
        return watch(a.out, a.seconds, a.every, a.gpu)
    if a.cmd == "record":
        from .config import Config
        from .runtime.record import record
        from .runtime.runner import VK
        for k in (a.start_key, a.stop_key):
            if k not in VK:
                ap.error(f"hotkeys must be F1-F12, got {k!r}")
        cfg = Config()
        cfg.keys.start, cfg.keys.stop, cfg.keys.note = a.start_key, a.stop_key, a.note_key
        return record(a.out or (a.corpus or corpus_root()) / "incoming", cfg, labels=a.label)
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
        from .gamedata import EXPORT, ROOT, build
        if a.action == "scene":
            from .scene import build_scenes
            n = build_scenes(a.export or EXPORT, ROOT, a.maps or None)
            print(f"{n} scenes built")
            return 0
        build(a.export or EXPORT)
        return 0
    if a.cmd in ("run", "serve"):
        from .config import Config
        from .keyboard import validate
        from .runtime.runner import VK, run, serve
        for k in (a.attack, a.basic_attack, a.jump):
            validate(k)
        cfg = Config()
        cfg.keys.attack, cfg.keys.jump, cfg.safety.hp_stop = a.attack, a.jump, a.hp_stop
        cfg.keys.basic_attack = a.basic_attack
        cfg.perception.map_id = a.map
        cfg.combat.weapon, cfg.combat.attack_speed = a.weapon, a.attack_speed
        from .brain.reach import Reach
        try:
            Reach(a.weapon)
        except KeyError as e:
            ap.error(str(e))
        if a.cmd == "run":
            return run(a.out, a.seconds, cfg, focus=not a.no_focus, frames_every=a.frames_every,
                       frames_png=a.frames_png, video=a.video)
        for k in (a.start_key, a.stop_key):
            if k not in VK:
                ap.error(f"hotkeys must be F1-F12, got {k!r}")
        cfg.keys.start, cfg.keys.stop = a.start_key, a.stop_key
        if a.video and (a.frames or a.frames_every is not None) and not a.frames_png:
            ap.error("--video already holds every frame, lossless: JPEG frame files beside it are not written "
                     "(--frames-png adds PNG files of every Nth frame)")
        every = a.frames_every if a.frames_every is not None else (3 if a.frames or a.frames_png else 0)
        return serve(a.out, cfg, frames=every, observe=a.observe, frames_png=a.frames_png, video=a.video)
    return 2


if __name__ == "__main__":
    sys.exit(main())
