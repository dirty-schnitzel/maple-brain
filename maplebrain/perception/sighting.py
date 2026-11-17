"""A mob sighting as the tracker takes it (world.py): the fit's mobs and its looks around tracks (fit.Fitter.hit).

Moved here 2026-11-17 from the old detectors (sprites.Pose, gpu_sprites.Hit) when they were deleted; same fields,
so recorded sightings read the same."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Pose:
    """Which sprite frame: animation, frame number in play order, facing, and the frame's origin (the client's feet
    point, from mob.json 'frames') inside the drawn box - flipped with the sprite."""
    anim: str
    n: int
    facing: str             # "left" (the client draws mobs facing left) / "right" (mirrored)
    ox: int
    oy: int


@dataclass
class Hit:
    mob_id: int
    box: tuple          # (x, y, w, h) screen pixels: the pose's picture at the feet
    feet: tuple         # (x, y)
    pose: Pose
    score: float        # 1.0 from the fit (its own rule decided)
