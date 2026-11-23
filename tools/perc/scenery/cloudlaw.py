"""PLAN-moving-scenery.md step 4's first check: does what the cloud design rests on hold on a capture? From
run_clouds.py's per-frame finds (OUT/clouds_<tag>.json: every cloud CloudFinder.find saw alone on a frame - picture k,
map place of its top-left, the share of its informative pixels the exact model explains, the opacity it measured).
    python tools/perc/scenery/cloudlaw.py TAG [--map MAP]
The finds are linked frame to frame into clouds (same picture, within 6 px of where the cloud's speed puts it). Per
cloud seen on >= 20 frames:
  opacity    the spread of its measured opacity (p5..p95, max - min): the design needs one opacity a cloud
  speed      a straight line through its places (x and y against time): the slope = its speed, the rms of the
             residuals (whole pixels on a straight line give ~0.29 px; anything bigger = not constant)
  share      how much of its picture the exact model explains at its whole-pixel place (p50): low = drawn at
             fractions of a pixel, or not the model
Then where clouds are born and die on the map (the map's edge?), how many are on the map at once."""
import argparse
import json

import numpy as np

import msl


def link(rows, gate=6.0):
    tracks = []
    for r in rows:
        t = r["t"]
        taken = set()
        for k, mx, my, sh, nn, o, vis in r["clouds"]:
            best, bd = None, gate
            for j, tr in enumerate(tracks):
                if tr["k"] != k or j in taken or t - tr["t"][-1] > 3.0:
                    continue
                vx = tr["vx"] if len(tr["t"]) >= 3 else 0.0
                vy = tr["vy"] if len(tr["t"]) >= 3 else 0.0
                dt = t - tr["t"][-1]
                d = max(abs(tr["x"][-1] + vx * dt - mx), abs(tr["y"][-1] + vy * dt - my))
                lim = bd if len(tr["t"]) >= 3 else max(bd, 60 * dt + 3)     # unknown speed: up to 60 px a second
                if d <= lim and (best is None or d < bd):
                    best, bd = j, d
            if best is None:
                tracks.append({"k": k, "t": [t], "x": [mx], "y": [my], "o": [o], "sh": [sh], "vx": 0.0, "vy": 0.0})
                taken.add(len(tracks) - 1)
                continue
            tr = tracks[best]
            taken.add(best)
            tr["t"].append(t)
            tr["x"].append(mx)
            tr["y"].append(my)
            tr["o"].append(o)
            tr["sh"].append(sh)
            if len(tr["t"]) >= 3:
                tt = np.array(tr["t"])
                tr["vx"] = float(np.polyfit(tt, tr["x"], 1)[0])
                tr["vy"] = float(np.polyfit(tt, tr["y"], 1)[0])
    return tracks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--min", type=int, default=20)
    a = ap.parse_args()
    rows = json.loads((msl.OUT / f"clouds_{a.tag}.json").read_text())
    tracks = [tr for tr in link(rows) if len(tr["t"]) >= a.min]
    print(f"{a.tag}: {len(rows)} frames over {rows[-1]['t'] - rows[0]['t']:.0f} s, finds {sum(len(r['clouds']) for r in rows)}; "
          f"clouds seen on >= {a.min} frames: {len(tracks)}")
    out, spreads, rmss, shares = [], [], [], []
    for n, tr in enumerate(tracks):
        tt, x, y, o, sh = (np.array(tr[k]) for k in ("t", "x", "y", "o", "sh"))
        px, py = np.polyfit(tt, x, 1), np.polyfit(tt, y, 1)
        rx, ry = x - np.polyval(px, tt), y - np.polyval(py, tt)
        rms = float(np.sqrt(np.mean(rx ** 2 + ry ** 2)))
        sp = float(np.percentile(o, 95) - np.percentile(o, 5))
        spreads.append(sp)
        rmss.append(rms)
        shares.append(float(np.median(sh)))
        row = {"n": n, "k": tr["k"], "frames": len(tt), "s": round(float(tt[-1] - tt[0]), 1), "o_p50": round(float(np.median(o)), 4),
               "o_p5_p95": round(sp, 4), "o_maxmin": round(float(o.max() - o.min()), 4), "vx": round(float(px[0]), 2),
               "vy": round(float(py[0]), 2), "rms": round(rms, 2), "max_res": round(float(np.max(np.hypot(rx, ry))), 2),
               "share_p50": round(float(np.median(sh)), 3), "x0": int(x[0]), "x1": int(x[-1]), "y0": int(y[0]), "t0": round(float(tt[0]), 1), "t1": round(float(tt[-1]), 1)}
        out.append(row)
        print(f"  cloud {n:2d} pic {tr['k']}: {len(tt):4d} frames over {row['s']:5.1f} s, opacity {row['o_p50']:.3f} (p5-p95 {sp:.4f}, "
              f"max-min {row['o_maxmin']:.3f}), speed {px[0]:6.2f} / {py[0]:5.2f} px/s, line rms {rms:.2f} (max {row['max_res']:.2f}), "
              f"share p50 {row['share_p50']:.2f}; x {row['x0']} -> {row['x1']} ({row['t0']}-{row['t1']} s)")
    print(f"  opacity p5-p95 spread per cloud: p50 {np.median(spreads):.4f}, max {max(spreads):.4f};  line rms per cloud: p50 "
          f"{np.median(rmss):.2f}, max {max(rmss):.2f} px;  share p50 per cloud: p50 {np.median(shares):.2f}, min {min(shares):.2f}")
    print(f"  clouds found per frame: p50 {np.median([len(r['clouds']) for r in rows]):.0f}, max {max(len(r['clouds']) for r in rows)}")
    (msl.OUT / f"cloudlaw_{a.tag}.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
