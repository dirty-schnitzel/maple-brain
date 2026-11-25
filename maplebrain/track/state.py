"""The state's records (docs/state_model.md section 2). Built so far: the MOB record (PLAN-tracker step 3), one per
mob the tracker holds, filled by track/mobs.py every frame; the DROP record (step 4a), filled by track/drops.py. Step 8
adds the stored tables (writer and reader) here.

A mob is in the state once CONFIRMED (seen clearly once, or sighted for 0.5 s: PLAN-tracker design 4); a tentative
track is kept beside it (`confirmed` False) and is not yet a mob - a reader leaves it out. Two places, on purpose:
`x_seen`, `y_seen` = where it was last seen (the model's x, y while unseen); `x`, `y` = where it is now: seen, the
same; remembered, the middle of where it can be (`can_lo..can_hi` on its node; a flyer's set in two directions),
which is what the tracker's grades measure (tools/perc/track/score.py).
"""
from dataclasses import asdict, dataclass

# cover: what is over a mob that is not seen (or "none" while seen). The tracker's names (the prototype's): "fading
# in" (last seen fading in: not checked for 0.4 s), "out of view" (its places lie past the screen's edge), "ui /
# scenery" (in view, but nothing there can show a mob: the UI, animated or front scenery); "edge" (its body box at x,
# y crosses the screen's edge: the edge wins over what covers its in-view part - the user, 2026-11-24), then what is
# drawn over the nearest place it can be: "us", "player", "mob", "drop", "effect" (anything else); "blind" = no camera
# this frame (every field keeps its last value).
COVERS = ("none", "fading in", "out of view", "ui / scenery", "edge", "us", "player", "mob", "drop", "effect", "blind")
STATES = ("tentative", "live", "hit", "dying", "hidden", "offscreen")


@dataclass
class Mob:
    id: int                             # never reused in a stay
    kind: int                           # the client's mob id, voted over the sightings (a clear one counts more)
    confirmed: bool                     # a mob in the state (else a tentative track)
    state: str                          # STATES: live / hit (seen), dying, hidden / offscreen (remembered), tentative
    x: float                            # feet, map px (see the module's docstring)
    y: float
    sx: float                           # ... on the screen (x - the camera)
    sy: float
    x_seen: float                       # where it was last seen
    y_seen: float
    place: str                          # "stand" / "air" / "fly" (graph.PLACES), at its last sighting
    node: int                           # standing: its node; air: the first surface under it (graph.NONE: none)
    from_node: int                      # the node it stood on last (its possible set lies on it)
    off: float                          # feet y - the node's surface y at its last sighting (NaN: over nothing)
    vx: float                           # px/s over its last 0.25 s of sightings
    vy: float                           # px/s from its last frame step (0 when not seen on the last frame)
    facing: int                         # -1 left / +1 right
    pose: str                           # the animation and frame ("move_2")
    opacity: float
    life: str                           # spawning (fading in) / alive / hit / dying
    seen: bool                          # found on this frame (a blind frame keeps the last value)
    vis: float                          # the share of its full size seen at its last sighting
    cover: str                          # COVERS
    unseen_s: float                     # seconds since it was last seen
    can_lo: float | None                # remembered: the x range where it can be now (None while seen)
    can_hi: float | None
    born_t: float
    born_how: str                       # how it came into sight: "there at entry" / "faded in" / "came into view" /
                                        # "uncovered"
    first_pose: str                     # the pose of its first sighting (a die pose: first seen dying; the user,
                                        # 2026-11-24: how it came into sight and its first pose are two fields)
    hits: int = 0                       # step 5 (events) fills these
    last_hit_t: float | None = None
    last_hit_by: str | None = None
    seen_share: float = 1.0             # the share of its frames since birth it was seen on

    def as_dict(self) -> dict:
        return asdict(self)


# a drop's cover (track/drops.py): sighted - "none" (fully seen), "partly" (a weak sighting or part of it unseen),
# "drop" (partly under another drop), "scenery" (part of it under front scenery); not sighted - what the look at its
# place said: "out of view", "edge" (too little of it on screen), "ui" (under the UI / unknown scenery), "scenery"
# (behind front scenery of its layer), "covered" (something is drawn over its place), "empty" (its place shows the
# scenery: gone after 0.15 s of it); "blind" = no camera this frame.
DROP_COVERS = ("none", "partly", "drop", "scenery", "out of view", "edge", "ui", "covered", "empty", "blind")


@dataclass
class Drop:
    """One drop the drop tracker holds (docs/state_model.md section 2, "Every drop"). In the state once CONFIRMED
    (sighted at rest over 0.25 s: PLAN-tracker design 5); a tentative one is kept beside it (`confirmed` False)."""
    id: int                             # never reused in a stay
    item: int                           # the picture class's item id (items.json); mesos 9000000-9000003
    cls: str                            # meso bronze / gold / bundle / sack, equip, use, etc, setup
    confirmed: bool
    x: int                              # map px, exact: the picture's bottom-centre
    y: int                              # its foothold's surface y under it (the bob is 0..5 px around it)
    fh: int | None                      # that foothold's id, its layer
    layer: int | None
    node: int                           # the graph's node it lies on (graph.NONE: no graph / not found)
    born_t: float                       # its first resting sighting
    landed: bool                        # its place was on screen before it lay there (else it came into view lying)
    from_mob: int | None                # the mob track whose death fits it (time and place); None: none fits
    seen: bool                          # sighted on this frame
    cover: str                          # DROP_COVERS
    unseen_s: float                     # seconds since it was last sighted

    def as_dict(self) -> dict:
        return asdict(self)
