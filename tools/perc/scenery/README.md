# tools/perc/scenery: the measurements and prototypes behind PLAN-moving-scenery.md

Written by the plan session (2026-11-21). Nothing here is on the live path and nothing in `maplebrain/` was
changed: these tools measure footage and prototype the plan's parts, and they are the **reference** the plan's
executor sessions port from and check against. Run from the repo root with the venv python. They read the bank
(dev group only; a hold-out capture is refused) and write to `F:\dev\maple-corpus\work\scenery\` (`msl.OUT`: sheets,
JSON results, the cached cameras - safe to delete, made again by the tools). GPU: not while the user records
(`msl.guard`).

Words: a **mover** = a background layer the client moves with time (back type 4 / 6); a **cloud** = one of the
client's 7 weather cloud pictures, drawn over the field on maps whose info says `cloud = 1`; **expected** = the map
drawn for a camera; **undone** = the frame with the clouds taken out again.

## Measuring
| Tool | What it answers |
|---|---|
| `catalog.py [MAP ..]` | What the client files say moves, per map: the table by kind (`catalog.json`), the background pictures' own properties (`back_props.json`). No GPU, no footage |
| `export_helper.ps1` | Until `export.ps1` does it (the plan's step 1): the raw bytes of the pixel-format-1537 pictures (`raw1537.tsv`), the weather cloud and portal pictures (`MapHelper\...png`) |
| `cam.py CAP ..` | The scene camera of every frame of a capture, also on a map the hunt refuses (the camera registers on tiles / objects only) -> `cams\`. The kept replay's camera when the capture has one |
| `look.py CAP IDX ..` | One frame, today's expected picture and where they differ, as a sheet |
| `phase.py CAP` | Where is each mover on each frame? Its opaque pixels show their own colour: every sideways place x 5 rows tried -> `phase\<cap>.json`. The law came out of these files (the plan, "What was measured") |

## Prototypes (slow, exact: the reference)
| Tool | What it is |
|---|---|
| `proto.py` | `MScene`: maplebrain's `Scene` + the two flat pictures' real colours + the ADDED layers + every mover found on the frame (`locate`, top-most first) and drawn at its place (`expected`) |
| `clouds.py` | `CloudFinder`: the clouds of one frame alone - the thickness the frame implies per pixel, matched against the 7 pictures at every place (FFT), each match checked with the exact model (its own opacity) |
| `run_proto.py CAP`, `run_clouds.py CAP` | Those two over a capture: the share of the play area the frame equals the expected picture, before / after |
| `sound_proto.py CAP ..` | `tools/perc/track/sound.py`'s verdict (the `model` share) for today's picture and the prototype's |
| `run_fit.py CAP [--clouds FILE]` | maplebrain's fit, unchanged, three ways: today's picture / movers explained / + clouds undone; sheets of the mobs only one way finds |
| `synth_clouds.py CAP` | Truth by construction: a mob sprite pasted on a foothold, a cloud blended over it, found or not per cloud thickness - cloud left in / undone / undone + the tolerant vote (`cloudvote.py`) |

## Prototypes (fast: what a frame would cost)
| Tool | What it is |
|---|---|
| `fastexp.py CAP` | `FastScene.expected`: every background layer drawn only where it is on screen, one `lerp_` each; checked against `proto` and timed against today's `Scene.expected` |
| `fastpipe.py CAP [--clouds FILE]` | `FastMovers.step` (all movers x 7 places in one batch, sample pixels, a peak rule), `FastClouds.step / layer / undo` (followed clouds, one batch); agreement with the slow reference + ms per part |
| `cloudtrack.py CAP [--fit] [--tolvote]` | The clouds FOLLOWED over time, end to end: follow -> the cloud layer -> new clouds by the coarse finder only where the frame is still whitened -> the frame undone -> the fit; sheets of random mobs for a look by eye |

## Gates: maplebrain's code against the reference (the plan's executor steps)
| Tool | Step | What it checks |
|---|---|---|
| `live2.py CAP` | 2 | `scene.MoverFollow` + `Scene.expected(C, X)` against `proto.MScene` on every frame: the picture at the reference's places (levels), the share of the reference's mover-frames the live follow finds on its own and on the same pixel, frame = expected (`shows`), the ms -> `live2_<cap>.json` |
| `live3.py CAP ..` | 3 | the kept replay's sightings against `run_fit.py`'s A / B on the same frames; `--sheet N` random live sightings A does not give, for the look by eye |
| `cloudlaw.py TAG` | 4 | `run_clouds.py`'s per-frame finds linked into clouds: per cloud the opacity spread, a straight line through its places, the share the exact model explains (does the design's base hold?) |
| `live4.py CAP --finds TAG` | 4 | `perception/clouds.py` over every frame against the per-frame finds: frame = expected with the cloud layer, finds followed within 1 px, per cloud opacity / line, ms, finder runs |

## What they showed (the numbers are in the plan)
1. The Victoria Road forest maps have no moving scenery: one picture's colour is decoded wrong by the export
   (the sky), and Ellinia's light rays are ADDED to the picture, not laid over it. With both right, 9 of 9 forest
   captures are sound.
2. A moving back keeps its exact colours; its place is `5 x rx` px a second along the MAP (not the screen), its row
   the static formula with another rounding. Followed per frame it is exact to the pixel, and the expected picture
   with every layer drawn where it is costs under 1 ms - less than today's.
3. Perion's clouds in front are the client's weather clouds: 7 pictures, each cloud at its own constant opacity and
   speed, at whole pixels, over mobs and name tags, under the UI. Undone, the fit finds the mobs under them.
