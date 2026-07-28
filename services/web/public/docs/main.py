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
            # Launch only if we own the planet, have enough ships and energy
            if owner == me and ships >= 25 and energy >= 20:
                targets = [q for q in planets if q[1] != me]
                if not targets:
                    continue
                target = min(
                    targets, key=lambda q: (q[2] - x) ** 2 + (q[3] - y) ** 2
                )
                ang = angle_to(x, y, target[2], target[3])
                actions.append([pid, ang, int(ships / 2)])

        # Send action array to engine stdout
        sys.stdout.write(json.dumps(actions) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
