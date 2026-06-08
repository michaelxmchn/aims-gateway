# Classic Game Feel Profiles

Detailed breakdowns of iconic game feel implementations for reference and study.

---

## Asteroids (1979)

**Feel Summary**: Floaty, on-the-edge-of-control, expressive space simulation

### Why It Worked
Asteroids redefined what games could feel like. By separating thrust from rotation, it created a sensation of piloting a craft that was always *almost* out of control—but never actually was.

### Input
- 5 two-state buttons (Rotate L/R, Thrust, Fire, Hyperspace)
- Two-handed operation required
- No chorded moves
- Big, springy, satisfying buttons

### Core Mechanic: Separated Thrust/Rotation

**Rotation**: Direct, instant
```
if (rotateLeft) shipAngle -= rotateSpeed
if (rotateRight) shipAngle += rotateSpeed
```
- Very slight attack (~0.1s ramp)
- No simulation, no inertia
- Crisp, precise

**Thrust**: Simulated, accumulative
```
thrustVector = directionFromAngle(shipAngle) × thrustSpeed
shipVelocity = shipVelocity + thrustVector  // ADD, not overwrite!
```
- Floaty 3+ second attack to max speed
- 4+ second release (very low dampening ~0.99)
- Creates "spacey" frictionless feel

### Critical Insight
The thrust vector is **added** to ship velocity, not overwriting it. This decouples where you're facing from where you're going—the fundamental Asteroids feel.

### Context
- Screen wrap containment (no escape)
- Asteroid density provides constant danger
- Ship moves faster than asteroids but less predictably
- "Like being an experienced ice skater at a crowded public rink"

### Polish
- Size-pitch correlation: Large asteroid = deep boom, small = high ping
- Ship disintegrates into component lines on death
- Thruster visual: flickering vector line
- Cohesive despite limited hardware

### Rules
- One-hit death (ship feels fragile)
- Points scale with difficulty (small asteroid = 100, large = 20)
- Flying saucers: High risk/reward (1000 points for small)
- Extra life at 10,000 points

---

## Super Mario Bros (1985)

**Feel Summary**: Fluid, expressive, intuitive—the gold standard for platformers

### Why It Worked
Miyamoto understood feel as artistic experience, not simulation accuracy. The result: controls that feel natural despite being highly artificial.

### Input
- NES Controller: D-pad + A (jump) + B (run)
- Simple Boolean signals
- B modifies movement parameters, not separate action

### Horizontal Movement

**Walk**:
- Acceleration: Moderate
- Max speed: Capped
- Deceleration: Moderate slide to stop

**Run (B held)**:
- Acceleration: Higher
- Max speed: Higher cap
- Deceleration: Same as walk

**Air**:
- Acceleration: Reduced
- Same max speed limits apply

### Vertical Movement (The Jump)

**The Recipe**:
1. Button press → Instant large upward force
2. While held → Force continues (up to max time)
3. Early release → Velocity artificially set to low preset value
4. Apex detected → Gravity TRIPLES for descent
5. Terminal velocity caps fall speed

**The Critical Hack**:
When player releases jump early:
```
if (velocity.y > reducedJumpVelocity) {
    velocity.y = reducedJumpVelocity  // Artificial cap
}
```
This creates consistent arc shapes regardless of release timing.

**Running Jump Boost**:
If speed > walk max when jumping, slight extra jump force.

### Key Parameters
| Parameter | Approximate Value |
|-----------|------------------|
| Walk acceleration | Moderate |
| Walk max speed | ~3 units/frame |
| Run acceleration | Higher |
| Run max speed | ~5 units/frame |
| Air acceleration | ~30% of ground |
| Jump force | Large instant burst |
| Gravity | Moderate |
| Fall gravity | 3× normal gravity |
| Max jump time | ~0.4 seconds |

### Context
- Blocks at exact jump heights
- Gaps at exact run-jump distances  
- Enemies as timing challenges
- Pipes and hidden areas reward exploration

### Polish
- Slide whistle jump sound (rising pitch)
- Dust on direction change
- Squash on landing
- Simple but coherent

### Rules
- Size changes with powerups (feel different)
- One-hit death (small) or shrink (big)
- Coins everywhere (constant small rewards)
- Time pressure (never truly relaxed)

---

## Super Mario 64 (1996)

**Feel Summary**: Expressive 3D translation with precision special moves

### Why It Worked
Successfully translated 2D Mario feel to 3D through camera-relative controls, multiple jump types, and incline-based physics.

### Input
- N64 controller: Analog stick + A (jump) + B (attack) + Z (crouch)
- Stick provides continuous direction AND speed
- Camera controls on C-buttons

### Movement System

**Thumbstick → World Direction**:
```
worldDirection = cameraForward × stick.y + cameraRight × stick.x
```

**Turn Interpolation**:
```
if (speed > 0) {
    currentDirection = lerp(currentDirection, desiredDirection, turnSpeed)
} else {
    currentDirection = desiredDirection  // Instant at standstill
}
```
Creates carving motion when moving, instant turns when stopped.

**Incline Physics**:
- Steep slopes (>45°) resist climbing
- Very steep slopes (~75°) trigger slide state
- Creates soft boundaries without invisible walls

### Jump Types

| Jump | Trigger | Height | Control |
|------|---------|--------|---------|
| Basic | A | Variable (hold) | Full air steering |
| Continuous | A after landing | Higher, variable | Full air steering |
| Triple | A after Continuous + speed | Highest, fixed | Air steering |
| Long | Z+A moving | Low, far, fixed | Air steering |
| Back Somersault | A while crouching | Very high, fixed | Air steering |
| Side Somersault | A during direction change | High, fixed | Air steering |
| Wall Kick | A near wall + away | Fixed | Limited steering |

**Variable vs Fixed**:
- Variable jumps: Expressive, moment-to-moment control
- Fixed jumps: Predictable, precision platforming

### Ground Pound
```
if (inAir && Z) {
    velocity.x = 0; velocity.z = 0  // Kill horizontal momentum
    wait(0.1)
    velocity.y = -groundPoundSpeed
}
```
Provides precision landing by removing horizontal momentum.

### Context
- Levels designed around jump trajectories
- Landmarks visible from anywhere (aids navigation)
- Inclines create soft boundaries
- Open spaces for running, tight spaces for precision

### Polish
- Three-tier impact system (light/medium/heavy)
- Surface-specific footsteps
- Mario's vocalizations sync with motion
- Exaggerated limb scaling on attacks

### Control Ambiguity (Flaw)
Z+A can produce ground pound, backflip, or long jump depending on subtle timing differences. This is acknowledged as a design flaw.

---

## Comparative Analysis

### Response Time
| Game | Attack | Release |
|------|--------|---------|
| Asteroids rotation | ~0.1s | Instant |
| Asteroids thrust | ~3s | ~4s |
| Mario Bros walk | ~0.2s | ~0.3s |
| Mario Bros run | ~0.3s | ~0.3s |
| Mario 64 run | ~0.15s | ~0.1s |

### Expressivity
| Game | Movement States | Jump Variety |
|------|-----------------|--------------|
| Asteroids | Continuous velocity | N/A |
| Mario Bros | Walk/Run | Variable height |
| Mario 64 | Walk/Run/Slide/Crawl | 7+ jump types |

### What They Share
1. **Separated systems**: Thrust/rotation, horizontal/vertical
2. **Artificial interventions**: Hacks that feel natural
3. **Context-mechanic fit**: Levels designed for the controls
4. **Coherent polish**: Effects reinforce physics
5. **Responsive input**: <100ms response times

---

## Modern Applications

### When to Use Asteroids-Style Feel
- Space games
- Physics toys
- "Barely in control" experiences
- Games about mastering momentum

### When to Use Mario-Style Feel
- Platformers
- Action games
- Games requiring precise positioning
- Accessible but deep controls

### When to Use Mario 64-Style Feel
- 3D platformers
- Exploration games
- Games with diverse movement options
- Precision 3D navigation

---

## Study Recommendations

To deeply understand these profiles:

1. **Play** the original games extensively
2. **Analyze** by recording and frame-stepping
3. **Recreate** the feel in a simple prototype
4. **Modify** parameters to understand their impact
5. **Compare** to modern games in the same genre
