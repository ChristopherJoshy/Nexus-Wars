"use client";

export default function OverviewPage() {
  return (
    <div className="max-w-5xl mx-auto py-4">
      {/* GitHub README Document Container */}
      <div className="bg-card border border-border rounded-lg p-4 sm:p-8 text-xs leading-relaxed space-y-12 font-sans">
        
        {/* HEADER SECTION */}
        <section id="readme-overview" className="space-y-6">
          <div className="border-b border-border pb-4 space-y-2">
            <h1 className="text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight">Nexus Wars</h1>
            <p className="text-sm text-muted-foreground">
              Command orbital fleets and conquer 4-fold symmetric solar systems in continuous 2D space. A deterministic 1v1 real-time strategy environment for autonomous AI agents.
            </p>
          </div>

          {/* Table of Contents */}
          <div className="bg-muted border border-border p-4 rounded-md space-y-2">
            <h2 className="text-xs font-bold text-foreground uppercase tracking-wider">Table of Contents</h2>
            <ul className="list-disc list-inside space-y-1 text-xs text-primary font-medium">
              <li><a href="#readme-overview" className="hover:underline">Overview &amp; Executive Summary</a></li>
              <li><a href="#readme-rules" className="hover:underline">Game Mechanics &amp; Map Specifications</a></li>
              <li><a href="#readme-energy" className="hover:underline">Thermal Energy &amp; Fleet Dynamics</a></li>
              <li><a href="#readme-math" className="hover:underline">Mathematical &amp; Physics Specifications</a></li>
              <li><a href="#readme-combat" className="hover:underline">Combat Resolution Pipeline</a></li>
              <li><a href="#readme-protocol" className="hover:underline">Bot Protocol &amp; Complete Starter Code</a></li>
              <li><a href="#readme-sandbox" className="hover:underline">Validation &amp; nsjail Sandbox Policy</a></li>
            </ul>
          </div>

          {/* Parameter Specifications Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-muted border-b border-border text-foreground">
                  <th className="p-2.5 font-semibold border-r border-border">Parameter</th>
                  <th className="p-2.5 font-semibold border-r border-border">Specification</th>
                  <th className="p-2.5 font-semibold">Description</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                <tr className="hover:bg-muted/50">
                  <td className="p-2.5 font-mono text-primary border-r border-border">Format</td>
                  <td className="p-2.5 border-r border-border">1v1 Deterministic RTS</td>
                  <td className="p-2.5 text-muted-foreground">Head-to-head match between two autonomous Python agent processes</td>
                </tr>
                <tr className="hover:bg-muted/50">
                  <td className="p-2.5 font-mono text-primary border-r border-border">Board Dimensions</td>
                  <td className="p-2.5 border-r border-border">100.0 &times; 100.0</td>
                  <td className="p-2.5 text-muted-foreground">Continuous 2D space with origin (0.0, 0.0) at top-left</td>
                </tr>
                <tr className="hover:bg-muted/50">
                  <td className="p-2.5 font-mono text-primary border-r border-border">Central Star</td>
                  <td className="p-2.5 border-r border-border">Sun (50.0, 50.0), Radius 10.0</td>
                  <td className="p-2.5 text-muted-foreground">Gravitational barrier; any fleet passing into radius 10.0 is vaporized</td>
                </tr>
                <tr className="hover:bg-muted/50">
                  <td className="p-2.5 font-mono text-primary border-r border-border">Episode Length</td>
                  <td className="p-2.5 border-r border-border">500 Steps (0 to 499)</td>
                  <td className="p-2.5 text-muted-foreground">Discrete turn steps; evaluation ends at step 499 resolution</td>
                </tr>
                <tr className="hover:bg-muted/50">
                  <td className="p-2.5 font-mono text-primary border-r border-border">Turn Timeout</td>
                  <td className="p-2.5 border-r border-border">1000 ms / turn</td>
                  <td className="p-2.5 text-muted-foreground">Per-step compute budget enforced inside nsjail sandbox</td>
                </tr>
                <tr className="hover:bg-muted/50">
                  <td className="p-2.5 font-mono text-primary border-r border-border">Rating Model</td>
                  <td className="p-2.5 border-r border-border">Glicko-2 (&mu;=600, &sigma;=350)</td>
                  <td className="p-2.5 text-muted-foreground">Skill rating with uncertainty decay and volatility tracking (&tau;=0.06)</td>
                </tr>
              </tbody>
            </table>
          </div>

          <h2 className="text-xl font-bold text-foreground border-b border-border pb-2">Overview &amp; Core Challenge</h2>
          <p>
            <strong className="text-foreground font-semibold">Nexus Wars</strong> challenges participants to program an autonomous agent that navigates a dynamic solar system. Unlike traditional static strategy games, planets in Nexus Wars rotate continuously around a central Sun, requiring agents to project target trajectories, evaluate orbital intercept points, and balance garrison production against launching long-range attack armadas.
          </p>

          <blockquote className="border-l-4 border-primary bg-muted p-4 rounded-r-md text-muted-foreground">
            <strong className="text-foreground font-semibold">Key Differentiating Mechanic:</strong> Every fleet launch costs <strong className="text-amber-700 font-semibold">20 thermal energy</strong> from the originating planet. Planets generate <strong className="text-primary font-semibold">+5 energy per turn</strong> up to a maximum cap of <strong className="text-foreground font-semibold">100 energy</strong>. This rate-limits fleet launches to a maximum frequency of 1 launch every 4 turns per planet, eliminating low-cost ship spam and rewarding strategic energy banking.
          </blockquote>

          <h2 className="text-xl font-bold text-foreground border-b border-border pb-2">Evaluation &amp; Ladder Architecture</h2>
          <p>
            When a team uploads a bot script (<code className="text-primary font-mono">agent.py</code>), the platform executes the following pipeline:
          </p>
          <ol className="list-decimal list-inside space-y-2 pl-2 text-xs">
            <li><strong className="text-foreground font-semibold">Self-Play Validation:</strong> The submission plays a validation match against itself. If it raises an exception, exceeds memory (512 MB), or times out (&gt;1000 ms), the submission is marked as <code className="text-destructive font-mono">Error</code> and log diagnostics are provided.</li>

            <li><strong className="text-foreground font-semibold">Ladder Entry:</strong> Valid submissions enter the live matchmaking queue initialized at Glicko-2 rating &mu; = 600, RD = 350.</li>
            <li><strong className="text-foreground font-semibold">Active Submission Limit:</strong> Teams can upload up to 5 submissions per day. The ladder automatically pairs the latest 2 active submissions from each team to maintain matchmaking density.</li>
            <li><strong className="text-foreground font-semibold">Continuous Rating Updates:</strong> Match outcomes continuously refine team skill ratings with deviation decay over time.</li>
          </ol>
        </section>

        {/* GAME MECHANICS SECTION */}
        <section id="readme-rules" className="space-y-6 pt-4">
          <h1 className="text-2xl font-bold text-foreground border-b border-border pb-2">Game Mechanics &amp; Map Specifications</h1>

          <h2 className="text-lg font-bold text-foreground">1. Map Geometry &amp; 4-Fold Symmetry</h2>
          <p>
            Map layouts are generated deterministically per episode seed using 4-fold mirror symmetry across quadrants:
          </p>
          <ul className="list-disc list-inside space-y-1.5 pl-2 text-xs">
            <li><strong className="text-foreground font-semibold">Symmetric Grouping:</strong> Planets are generated in groups of 4 coordinates: <code className="text-primary font-mono">(x, y)</code>, <code className="text-primary font-mono">(100-x, y)</code>, <code className="text-primary font-mono">(x, 100-y)</code>, and <code className="text-primary font-mono">(100-x, 100-y)</code>.</li>
            <li><strong className="text-foreground font-semibold">Home Planets:</strong> At step 0, one planet group is selected for home placement: Player 0 is assigned planet index 0 with 10 garrison ships; Player 1 is assigned planet index 3 with 10 garrison ships.</li>
            <li><strong className="text-foreground font-semibold">Planet Count:</strong> Maps contain between 5 and 10 planet groups (20 to 40 total planets). At least 3 groups are guaranteed to be static outer planets.</li>
            <li><strong className="text-foreground font-semibold">Clearance Rule:</strong> All generated planets maintain a minimum physical clearance distance of <code className="text-foreground font-mono">7.0</code> units from every other planet boundary.</li>
          </ul>

          <h2 className="text-lg font-bold text-foreground">2. Planets &amp; Orbital Motion</h2>
          <p>
            Planets are represented by a 10-element state tuple passed to agents every step:
          </p>
          <pre className="bg-muted border border-border p-3 rounded-md font-mono text-xs text-primary overflow-x-auto">
{`Planet Tuple: [id, owner, x, y, radius, ships, production, energy, energyCap, energyRegen]`}
          </pre>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-muted border-b border-border text-foreground">
                  <th className="p-2 border-r border-border">Property</th>
                  <th className="p-2 border-r border-border">Type / Range</th>
                  <th className="p-2">Mechanic Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                <tr>
                  <td className="p-2 font-mono text-primary border-r border-border">owner</td>
                  <td className="p-2 border-r border-border">-1, 0, 1</td>
                  <td className="p-2 text-muted-foreground">-1 = Neutral, 0 = Player 0 (Blue), 1 = Player 1 (Orange)</td>
                </tr>
                <tr>
                  <td className="p-2 font-mono text-primary border-r border-border">radius</td>
                  <td className="p-2 border-r border-border">1.0 to 2.61</td>
                  <td className="p-2 text-muted-foreground">Computed directly as <code className="font-mono">radius = 1.0 + ln(production)</code></td>
                </tr>
                <tr>
                  <td className="p-2 font-mono text-primary border-r border-border">production</td>
                  <td className="p-2 border-r border-border">1 to 5 ships/turn</td>
                  <td className="p-2 text-muted-foreground">Ships added to garrison each turn if planet is owned (<code className="font-mono">owner != -1</code>)</td>
                </tr>
                <tr>
                  <td className="p-2 font-mono text-primary border-r border-border">orbit type</td>
                  <td className="p-2 border-r border-border">Inner vs Outer</td>
                  <td className="p-2 text-muted-foreground">Inner (<code className="font-mono">dist + radius &lt; 50.0</code>) rotate around Sun; Outer (<code className="font-mono">&ge; 50.0</code>) remain static</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        {/* THERMAL ENERGY SECTION */}
        <section id="readme-energy" className="space-y-6 pt-4">
          <h1 className="text-2xl font-bold text-foreground border-b border-border pb-2">Thermal Energy &amp; Fleet Launch Dynamics</h1>

          <h2 className="text-lg font-bold text-foreground">1. Energy Management Rules</h2>
          <p>
            Thermal energy regulates launch frequency per planet:
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-muted border-b border-border text-foreground">
                  <th className="p-2 border-r border-border">Energy Parameter</th>
                  <th className="p-2 border-r border-border">Engine Value</th>
                  <th className="p-2">Rule Enforcement</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                <tr>
                  <td className="p-2 font-mono text-primary border-r border-border">Launch Cost</td>
                  <td className="p-2 border-r border-border">20 energy</td>
                  <td className="p-2 text-muted-foreground">Deducted from planet pool upon launching a fleet (regardless of fleet size)</td>
                </tr>
                <tr>
                  <td className="p-2 font-mono text-primary border-r border-border">Regeneration Rate</td>
                  <td className="p-2 border-r border-border">+5 energy / step</td>
                  <td className="p-2 text-muted-foreground">Added to owned planet pool at the start of turn step resolution</td>
                </tr>
                <tr>
                  <td className="p-2 font-mono text-primary border-r border-border">Energy Capacity</td>
                  <td className="p-2 border-r border-border">100 energy</td>
                  <td className="p-2 text-muted-foreground">Maximum stored energy (allows up to 5 banked launches per planet)</td>
                </tr>
                <tr>
                  <td className="p-2 font-mono text-primary border-r border-border">Rejection Policy</td>
                  <td className="p-2 border-r border-border">Silent Rejection</td>
                  <td className="p-2 text-muted-foreground">If planet energy &lt; 20 or ships &gt; garrison, action is rejected and logged</td>
                </tr>
              </tbody>
            </table>
          </div>

          <h2 className="text-lg font-bold text-foreground">2. Fleet Speed Logarithmic Scaling</h2>
          <p>
            Fleets travel in straight trajectories at a speed determined by total ship count. Larger armadas travel faster:
          </p>
          <pre className="bg-muted border border-border p-3 rounded-md font-mono text-xs text-foreground">
{`speed = min(6.0, 1.0 + 5.0 * ( ln(ships) / ln(1000) )^1.5)`}
          </pre>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-muted border-b border-border text-foreground">
                  <th className="p-2 border-r border-border">Fleet Size (Ships)</th>
                  <th className="p-2 border-r border-border">Calculated Speed (Units / Turn)</th>
                  <th className="p-2">Travel Time Across 50 Unit Distance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                <tr>
                  <td className="p-2 font-mono text-primary border-r border-border">1 Ship</td>
                  <td className="p-2 border-r border-border">1.00 unit/turn</td>
                  <td className="p-2 text-muted-foreground">50 turns</td>
                </tr>
                <tr>
                  <td className="p-2 font-mono text-primary border-r border-border">10 Ships</td>
                  <td className="p-2 border-r border-border">1.36 units/turn</td>
                  <td className="p-2 text-muted-foreground">~37 turns</td>
                </tr>
                <tr>
                  <td className="p-2 font-mono text-primary border-r border-border">100 Ships</td>
                  <td className="p-2 border-r border-border">3.23 units/turn</td>
                  <td className="p-2 text-muted-foreground">~15.5 turns</td>
                </tr>
                <tr>
                  <td className="p-2 font-mono text-primary border-r border-border">500 Ships</td>
                  <td className="p-2 border-r border-border">5.15 units/turn</td>
                  <td className="p-2 text-muted-foreground">~9.7 turns</td>
                </tr>
                <tr>
                  <td className="p-2 font-mono text-primary border-r border-border">&ge; 1000 Ships</td>
                  <td className="p-2 border-r border-border">6.00 units/turn (Max Speed Cap)</td>
                  <td className="p-2 text-muted-foreground">~8.3 turns</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        {/* MATHEMATICAL SPECIFICATIONS */}
        <section id="readme-math" className="space-y-6 pt-4">
          <h1 className="text-2xl font-bold text-foreground border-b border-border pb-2">Mathematical &amp; Physics Specifications</h1>

          <h2 className="text-lg font-bold text-foreground">1. Orbital Position Equations</h2>
          <p>
            Inner planets rotate around the Sun at <code className="font-mono">(50.0, 50.0)</code> at a fixed angular velocity &omega; &isin; [0.025, 0.05] rad/turn. Position at step t is calculated via parametric circle equations:
          </p>
          <pre className="bg-muted border border-border p-3 rounded-md font-mono text-xs text-foreground">
{`x(t) = 50.0 + R * cos( theta_0 + omega * t )
y(t) = 50.0 + R * sin( theta_0 + omega * t )`}
          </pre>

          <h2 className="text-lg font-bold text-foreground">2. Continuous Swept-Pair Collision Detection</h2>
          <p>
            To prevent fast fleets from tunneling or clipping through moving planets between steps, collision is evaluated continuously along line segments:
          </p>
          <pre className="bg-muted border border-border p-3 rounded-md font-mono text-xs text-foreground">
{`Fleet segment:  F(t) = A + t * (B - A),   where 0 <= t <= 1
Planet segment: P(t) = P0 + t * (P1 - P0), where 0 <= t <= 1

Relative displacement: D(t) = (A - P0) + t * [(B - A) - (P1 - P0)]
Collision condition:   min_t ||D(t)|| <= Planet_Radius`}
          </pre>
          <p className="text-muted-foreground">
            The quadratic discriminant check <code className="font-mono">disc = b^2 - 4ac</code> determines exact collision within time step <code className="font-mono">t &isin; [0, 1]</code>.
          </p>
        </section>

        {/* COMBAT RESOLUTION SECTION */}
        <section id="readme-combat" className="space-y-6 pt-4">
          <h1 className="text-2xl font-bold text-foreground border-b border-border pb-2">Combat Resolution Pipeline</h1>

          <p>
            When multiple fleets arrive at the same planet during step resolution:
          </p>
          <ol className="list-decimal list-inside space-y-2 pl-2 text-xs">
            <li><strong className="text-foreground font-semibold">Attacker Force Summation:</strong> All incoming fleets per player are aggregated into a total attacking force: <code className="font-mono">player_ships[p] = &sum; fleet.ships</code>.</li>
            <li><strong className="text-foreground font-semibold">Attacker vs Attacker Clash:</strong> Attacking forces fight amongst themselves first. The largest attacking force fights the second-largest:
              <pre className="bg-muted border border-border p-2.5 rounded-md font-mono text-xs text-foreground mt-1">
{`survivor_ships = top_ships - second_ships`}
              </pre>
              If <code className="font-mono">top_ships == second_ships</code>, both forces destroy each other completely (<code className="font-mono">survivor_ships = 0</code>).
            </li>
            <li><strong className="text-foreground font-semibold">Garrison Battle / Reinforcement:</strong>
              <ul className="list-disc list-inside pl-4 mt-1 space-y-1">
                <li>If the surviving attacker matches the planet owner: garrison is reinforced (<code className="font-mono">planet.ships += survivor_ships</code>).</li>
                <li>If the surviving attacker is hostile: garrison is reduced (<code className="font-mono">planet.ships -= survivor_ships</code>). If garrison drops below 0, the planet is captured: <code className="font-mono">planet.owner = survivor_owner</code> and <code className="font-mono">planet.ships = abs(remaining)</code>.</li>
              </ul>
            </li>
          </ol>
        </section>

        {/* BOT PROTOCOL & STARTER CODE */}
        <section id="readme-protocol" className="space-y-6 pt-4">
          <h1 className="text-2xl font-bold text-foreground border-b border-border pb-2">Bot Protocol &amp; Complete Starter Code</h1>

          <h2 className="text-lg font-bold text-foreground">Standard Input Observation Format</h2>
          <p>Each step, the engine writes a JSON object line to standard input:</p>
          <pre className="bg-muted border border-border p-4 rounded-md font-mono text-xs text-foreground overflow-x-auto">
{`{
  "player": 0,
  "step": 42,
  "angular_velocity": 0.035,
  "planets": [
    // [id, owner, x, y, radius, ships, production, energy, energyCap, energyRegen]
    [0, 0, 50.0, 20.0, 3.2, 45, 4, 80, 100, 5],
    [1, 1, 50.0, 80.0, 3.2, 32, 4, 100, 100, 5]
  ],
  "fleets": [
    // [id, owner, x, y, angle, from_planet_id, ships, launchedStep]
    [101, 0, 50.0, 30.0, 1.5708, 0, 20, 40]
  ]
}`}
          </pre>

          <h2 className="text-lg font-bold text-foreground">Standard Output Action Format</h2>
          <p>Return a JSON array of 3-tuples written to standard output:</p>
          <pre className="bg-muted border border-border p-3 rounded-md font-mono text-xs text-primary overflow-x-auto">
{`[[from_planet_id, angle_in_radians, ship_count]]`}
          </pre>

          <h2 className="text-lg font-bold text-foreground">Official Tactical Python Starter Code (<code className="font-mono text-primary">agent.py</code>)</h2>
          <pre className="bg-muted border border-border p-4 rounded-md font-mono text-xs text-foreground overflow-x-auto">
{`#made without ai by chris (only this bot :) )
import sys
import json
import math

SUN_X, SUN_Y = 50.0, 50.0
SUN_SAFE_RADIUS = 11.5

def dist(ax, ay, bx, by):
    return math.sqrt((ax - bx)**2 + (ay - by)**2)

def line_intersects_sun(ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx*dx + dy*dy
    if l2 == 0:
        return dist(ax, ay, SUN_X, SUN_Y) < SUN_SAFE_RADIUS
    t = max(0.0, min(1.0, ((SUN_X - ax)*dx + (SUN_Y - ay)*dy) / l2))
    proj_x, proj_y = ax + t*dx, ay + t*dy
    return dist(proj_x, proj_y, SUN_X, SUN_Y) < SUN_SAFE_RADIUS

def get_fleet_speed(ships):
    if ships <= 1:
        return 1.0
    val = (math.log(ships) / math.log(1000)) ** 1.5
    return min(6.0, 1.0 + 5.0 * val)

def predict_planet_position(p, step, initial_planets, angular_vel):
    pid, owner, x, y, r, ships, prod, e, ecap, eregen = p
    init_p = next((ip for ip in initial_planets if ip[0] == pid), None)
    if not init_p:
        return x, y
    dx = init_p[2] - SUN_X
    dy = init_p[3] - SUN_Y
    orbital_r = math.sqrt(dx*dx + dy*dy)
    if orbital_r + r >= 50.0:
        return x, y
    init_angle = math.atan2(dy, dx)
    future_angle = init_angle + angular_vel * step
    return SUN_X + orbital_r * math.cos(future_angle), SUN_Y + orbital_r * math.sin(future_angle)

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        
        obs = json.loads(line)
        me = obs["player"]
        step = obs.get("step", 0)
        angular_vel = obs.get("angular_velocity", 0.035)
        planets = obs.get("planets", [])
        initial_planets = obs.get("initial_planets", planets)
        
        actions = []
        my_planets = [p for p in planets if p[1] == me]
        target_planets = [p for p in planets if p[1] != me]
        
        if not target_planets:
            sys.stdout.write("[]\\n")
            sys.stdout.flush()
            continue

        for p in my_planets:
            pid, owner, px, py, pr, pships, pprod, energy, ecap, eregen = p
            
            if energy < 20 or pships <= 15:
                continue
            
            best_target = None
            best_score = -float("inf")
            best_angle = 0.0
            best_fleet_size = 0
            
            for t in target_planets:
                t_id, t_owner, tx, ty, tr, t_ships, t_prod, te, tecap, teregen = t
                
                launch_ships = pships - 10
                speed = get_fleet_speed(launch_ships)
                est_dist = dist(px, py, tx, ty)
                est_turns = math.ceil(est_dist / speed)
                
                pred_x, pred_y = predict_planet_position(t, step + est_turns, initial_planets, angular_vel)
                
                if line_intersects_sun(px, py, pred_x, pred_y):
                    continue
                
                expected_defense = t_ships + (t_prod * est_turns if t_owner != -1 else 0)
                needed_ships = expected_defense + 3
                
                if launch_ships < needed_ships:
                    continue
                
                score = (t_prod * 15.0) - (expected_defense * 0.5) - (est_dist * 0.8)
                if t_owner == -1:
                    score += 40.0
                
                if score > best_score:
                    best_score = score
                    best_target = t
                    best_angle = math.atan2(pred_y - py, pred_x - px)
                    best_fleet_size = int(needed_ships)

            if best_target and best_fleet_size >= 5:
                actions.append([pid, best_angle, best_fleet_size])

        sys.stdout.write(json.dumps(actions) + "\\n")
        sys.stdout.flush()

if __name__ == "__main__":
    main()`}
          </pre>
        </section>

        {/* SANDBOX & SECURITY POLICY */}
        <section id="readme-sandbox" className="space-y-6 pt-4">
          <h1 className="text-2xl font-bold text-foreground border-b border-border pb-2">Validation &amp; nsjail Sandbox Policy</h1>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-muted border-b border-border text-foreground">
                  <th className="p-2.5 border-r border-border">Constraint</th>
                  <th className="p-2.5 border-r border-border">Limit</th>
                  <th className="p-2.5">Enforcement Policy</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                <tr>
                  <td className="p-2.5 font-mono text-primary border-r border-border">Sandbox Isolation</td>
                  <td className="p-2.5 border-r border-border">Linux `nsjail`</td>
                  <td className="p-2.5 text-muted-foreground">Unprivileged user namespace execution with seccomp syscall filtering</td>
                </tr>
                <tr>
                  <td className="p-2.5 font-mono text-primary border-r border-border">Turn Timeout</td>
                  <td className="p-2.5 border-r border-border">1000 ms / step</td>
                  <td className="p-2.5 text-muted-foreground">Late response yields empty action; 10 consecutive timeouts kill process</td>
                </tr>
                <tr>
                  <td className="p-2.5 font-mono text-primary border-r border-border">Memory Budget</td>
                  <td className="p-2.5 border-r border-border">512 MB RAM</td>
                  <td className="p-2.5 text-muted-foreground">Processes exceeding memory cap are terminated immediately</td>
                </tr>
                <tr>
                  <td className="p-2.5 font-mono text-primary border-r border-border">Network Access</td>
                  <td className="p-2.5 border-r border-border">Disabled</td>
                  <td className="p-2.5 text-muted-foreground">Network sockets blocked; no outbound or inbound connections allowed</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
