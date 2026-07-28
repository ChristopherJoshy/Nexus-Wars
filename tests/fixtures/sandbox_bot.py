import sys
import json
import math


def angle_to(ax, ay, bx, by):
    return math.atan2(by - ay, bx - ax)


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        obs = json.loads(line)
        planets = obs["planets"]
        me = obs["player"]
        actions = []
        for p in planets:
            pid, owner, x, y, r, ships, prod, energy, ecap, eregen = p
            if owner != me or ships < 20:
                continue
            best = None
            bestd = 1e18
            for q in planets:
                if q[0] == pid:
                    continue
                d = (q[2] - x) ** 2 + (q[3] - y) ** 2
                if d < bestd:
                    bestd = d
                    best = q
            if best is None:
                continue
            ang = angle_to(x, y, best[2], best[3])
            actions.append([pid, ang, max(1, int(ships / 2))])
        sys.stdout.write(json.dumps(actions) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
