"""brain-v2: what happened to the mobs - state history per track, kills by OUR last hit, mobs someone else is hitting,
and the outcome of every swing for reach learning. Reads the tracks, never presses keys.
Swings come from the Weapon: one per press (one press = one swing in the game). Step 7 of the attack logic described
end to end in v2/combat.py.
v3 layer: world model (memory of the last HISTORY_S; PLAN-v3.md step 4 grows the longer memory beside it). Step 1:
reads the world model's Mob objects instead of the track dicts.
"""
import collections

from ..v3.model import LIVE

KILL_WINDOW = (0.2, 1.0)        # swing press -> its target turns dying (farming example: peak 0.5-0.8 s, few after 1.0)
HISTORY_S = 3.0


class Ledger:
    def __init__(self, reach, stats, say):
        self.reach, self.stats, self.say = reach, stats, say
        self.hist = {}                                    # track id -> deque[(t, state)]
        self.contested = {}                               # track id -> t someone else's hit was seen
        self.strikes = collections.deque()                # (t, ids in our weapon's reach at that swing)
        self.swing_t = -9.0
        self.kill_t = []

    def swung(self, now, near: list, in_reach: frozenset):
        self.reach.swing(now, near)
        self.strikes.append((now, in_reach))
        while self.strikes and now - self.strikes[0][0] > 2.0:
            self.strikes.popleft()
        self.swing_t = now

    def our_kill(self, now, tid) -> bool:
        """Last hit by OUR weapon: it turns dying KILL_WINDOW after a swing that had it inside our reach (predicted,
        like the strike rule). Kills others make on mobs we never had in reach aren't counted; a few we finish off
        for others are (the user, 2026-11-05: fine)."""
        lo, hi = KILL_WINDOW
        return any(lo <= now - t <= hi and tid in ids for t, ids in self.strikes)

    def contested_recently(self, tid, now, secs=3.0) -> bool:
        return now - self.contested.get(tid, -9) < secs

    def update(self, now, mobs):
        """`mobs`: the world model's [Mob] this tick (every kind and state)."""
        for m in mobs:
            h = self.hist.setdefault(m.id, collections.deque())
            prev = h[-1][1] if h else None
            h.append((now, m.state))
            while h and now - h[0][0] > HISTORY_S:
                h.popleft()
            if m.state == prev:
                continue
            ours = [n for t, n in self.reach.swings if now - t <= 1.0]
            had = any(tid == m.id for near in ours for tid, dx, dy in near)
            if m.state == "dying" and prev in LIVE:
                if self.our_kill(now, m.id):
                    self.stats["kills"] += 1
                    self.kill_t.append(now)
                    self.say(f"kill #{self.stats['kills']} (last hit): {m.type} id {m.id}")
                else:
                    self.stats["deaths_not_ours"] += 1
            elif m.state == "hit" and prev in ("live", "hidden") and not had and now - self.swing_t > 1.0:
                self.contested[m.id] = now
        for i in [i for i, h in self.hist.items() if h and now - h[-1][0] > HISTORY_S]:
            del self.hist[i]

        def state_of(tid, t0, t1):
            return [st for t, st in self.hist.get(tid, ()) if t0 <= t <= t1]
        for dx, dy, hit in self.reach.outcome(now, state_of):
            self.stats["reach_hit" if hit else "reach_nohit"] += 1
