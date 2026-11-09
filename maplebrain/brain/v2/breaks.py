"""brain-v2 breaks: nobody plays without ever stopping. Two kinds, both drawn fresh every time (no fixed timings):

    beat    a fight just ended and no mob is near -> BEAT_CHANCE of standing still BEAT_S (a look around). Only at that
            moment, never on the way to a target (the user: "a human doesn't stop on the way"). Ends early when a mob
            comes near.
    break   every BREAK_EVERY_S, stop for BREAK_S (uniform, the user: "every few minutes, on a ladder or
            otherwise safe space, never between mobs"). It waits for a safe spot, it doesn't go to one: trips climb ropes
            all the time, so when one is due the bot simply stops on the next rope it climbs.
                on a rope, head under the platform above, feet over the mobs below, no mob close
                                                             -> safe at once (judged where we'll come to rest: we
                                                                coast on after the keys go up)
                on the ground, no mob or spawn close by      -> safe only ROPE_FIRST_S after it fell due (ropes first;
                                                                a map without ropes still gets its breaks)
            A mob coming near us on the ground or a knock off ends it early; it then stays due, the bot finishes the
            fight and takes it at the next safe spot.

Damage ends either kind for good (the user: "taking damage during break = break over"): HP went down -> back to
hunting, the next break 2-5 min on. Never mid-fight (attack held) and never in the air. Reflexes (potions, HP stop) and
the lie detector go on during both.

v3 layer: tasks (Rest; PLAN-v3.md makes it a goal of its own in step 2). Step 1: reads the world model's Map (ropes,
Spawn objects) and our Character from the Scene.
"""
BEAT_CHANCE = 0.5
BEAT_S = (0.25, 1.5)
NEAR_PX = 250                     # a mob this close (same level): no beat, and a beat ends
BREAK_EVERY_S = (120.0, 300.0)    # s of play between two breaks
BREAK_S = (5.0, 20.0)             # the user 2026-11-06: half of the 10-40 s first asked for
ROPE_FIRST_S = (20.0, 40.0)       # s after a break fell due in which only a rope will do
ROPE_CLEAR_PX = 120               # no mob this close to a rope we stop on
ROPE_TOP_PX = 65                  # our feet this far under a rope's top: our body is ~60 px, the head stays under the
                                  # platform (27 live rope breaks: feet < 50 px under: 9 of 13 hit, 28 HP drops, mobs
                                  # walking by; >= 60 px: 1 of 14, 1 drop)
ROPE_FOOT_PX = 35                 # our feet this far over a rope's foot: over the mobs on the floor (~49 px, floor ~14
                                  # px under the foot)
COAST_S = 0.15                    # s of climbing that still happen after the keys go up (runs/v2 10:44: 18 px at 120 px/s)
GROUND_CLEAR_PX = 350             # no mob this close (same level) to a ground spot we stop on
SPAWN_CLEAR_PX = 150              # no spawn point this close: one could appear next to us
DANGER_PX = 100                   # a mob this close on the ground ends a break
LEVEL_PX = 80                     # |dy| that counts as our level


class Breaks:
    def __init__(self, map_, hz, stats, say):
        self.map, self.hz, self.stats, self.say = map_, hz, stats, say
        self.kind = None                                  # "beat" / "break" while resting
        self.until = 0.0
        self.due = None                                   # the next break falls due then
        self.ropes_only_until = 0.0
        self.fighting = False
        self.hp = None

    def _plan(self, now):
        self.due = now + self.hz.between(*BREAK_EVERY_S)
        self.ropes_only_until = self.due + self.hz.between(*ROPE_FIRST_S)

    def _close(self, sc, px, level=LEVEL_PX) -> bool:
        return any(abs(x.dx) <= px and abs(x.dy) <= level for x in sc.mobs)

    def safe(self, sc) -> bool:
        """A spot to stop on for a while (module doc)."""
        s = sc.me
        if s.state == "rope":
            if s.rope is not None:
                r = self.map.rope(s.rope)
                if not r.top + ROPE_TOP_PX <= s.y + s.vy * COAST_S <= r.bottom - ROPE_FOOT_PX:
                    return False
            return not self._close(sc, ROPE_CLEAR_PX)
        if s.state != "ground" or sc.now < self.ropes_only_until or self._close(sc, GROUND_CLEAR_PX):
            return False
        return not any(abs(sp.x - s.x) <= SPAWN_CLEAR_PX and abs(sp.y - s.y) <= LEVEL_PX for sp in self.map.spawns)

    def _start(self, kind, secs, now):
        self.kind, self.until = kind, now + secs
        self.stats[kind + "s"] += 1
        self.stats["rest_s"] += round(secs)
        if kind == "break":
            self.say(f"break {secs:.0f} s")

    def _interrupted(self, sc) -> bool:
        if sc.me.state == "air":
            return True
        if self.kind == "beat":
            return self._close(sc, NEAR_PX)
        return sc.me.state == "ground" and self._close(sc, DANGER_PX)

    def resting(self, sc, fighting: bool, hp=None) -> bool:
        """One tick. True = stay still this tick (`fighting`: the attack key is held, `hp`: our HP now)."""
        now = sc.now
        if self.due is None:
            self._plan(now)
        fight_over, self.fighting = self.fighting and not fighting, fighting
        hurt = hp is not None and self.hp is not None and hp < self.hp
        self.hp = hp if hp is not None else self.hp
        if self.kind is not None:
            finished = hurt or now >= self.until
            if not finished and not self._interrupted(sc):
                return True
            if hurt:
                self.stats["rests_hurt"] += 1
                self.say(f"{self.kind} over: took damage")
            if finished and self.kind == "break":
                self._plan(now)
            self.kind = None
            return False
        if fighting or sc.me.state == "air":
            return False
        if now >= self.due and self.safe(sc):
            self._start("break", self.hz.between(*BREAK_S), now)
        elif fight_over and not self._close(sc, NEAR_PX) and self.hz.between(0.0, 1.0) < BEAT_CHANCE:
            self._start("beat", self.hz.between(*BEAT_S), now)
        return self.kind is not None
