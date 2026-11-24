"""Us in the state (docs/state_model.md section 2, "Us"; PLAN-tracker design 7). Built so far: the 8 hotkeys
(`slots`, step 7). Step 4b adds the rest beside it - the feet from our tag placed by the one rule, `facing`, `act`,
the HUD's numbers - as further parts of `Us`, each with its own state and events; nothing here knows the brain.

The slots part: per key the item / skill / action on it and the item's amount, from FrameFacts `slots` (the hotkey
reader, perception/slots.py: exact or nothing on each frame). A key whose cell is not readable on a frame (a tooltip,
the cursor, a map change's fade) keeps its last exact reading, with `seen` False. Every change of an exact reading is
a `slot` event; an amount's step on the same item carries `d` (a potion drunk = -1, one picked up = +1).
"""
from dataclasses import dataclass, field


@dataclass
class Slot:
    """One hotkey as the state holds it. `kind` "item" / "skill" / "skill_disabled" / "skill_mouseover" / "action" /
    "empty" (perception/slots.Read); `id` the item's / skill's / action's id, `amount` the number drawn (None: none
    drawn). `seen`: read exactly on this frame (False: held from `seen_t`). `since`: when it last changed."""
    kind: str
    id: int | None
    amount: int | None
    seen: bool = True
    seen_t: float = 0.0
    since: float = 0.0

    def reading(self) -> list:
        return [self.kind, self.id, self.amount]


class Slots:
    """`update(slots, t)` per frame with FrameFacts `slots` ({key: [kind, id, amount] or None}) -> this frame's
    events. `keys` = {key: Slot}: every key ever read (a key never read exactly is not in it)."""

    def __init__(self):
        self.keys: dict[str, Slot] = {}

    def update(self, slots: dict, t: float) -> list:
        events = []
        for s in self.keys.values():
            s.seen = False
        for key, r in (slots or {}).items():
            if r is None:
                continue
            kind, cid, amount = r
            s = self.keys.get(key)
            if s is None:
                self.keys[key] = Slot(kind, cid, amount, True, t, t)
                continue
            if [kind, cid, amount] != s.reading():
                same = (kind, cid) == (s.kind, s.id) and amount is not None and s.amount is not None
                events.append({"ev": "slot", "t": t, "key": key, "was": s.reading(), "now": [kind, cid, amount],
                               "d": amount - s.amount if same else None})
                s.kind, s.id, s.amount, s.since = kind, cid, amount, t
            s.seen, s.seen_t = True, t
        return events

    def state(self) -> dict:
        """{key: {kind, id, amount, seen, seen_t, since}} - the state's `slots`."""
        return {k: {"kind": s.kind, "id": s.id, "amount": s.amount, "seen": s.seen, "seen_t": s.seen_t,
                    "since": s.since} for k, s in self.keys.items()}


@dataclass
class Us:
    """Our character in the state. `update(facts)` per frame (perception/facts.FrameFacts) -> this frame's events;
    `state()` the fields built so far."""
    slots: Slots = field(default_factory=Slots)

    def update(self, facts) -> list:
        return self.slots.update(facts.slots, facts.t)

    def state(self) -> dict:
        return {"slots": self.slots.state()}
