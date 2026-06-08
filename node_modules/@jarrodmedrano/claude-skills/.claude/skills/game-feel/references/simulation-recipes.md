# Simulation Recipes for Game Feel

Practical patterns for implementing specific feel profiles.

## Fundamental Simulation Approaches

### Level 1: Set Position Directly
```
position = position + (direction × speed)
```
- Input directly moves object
- Feel: Stiff, robotic, no momentum
- Example: Donkey Kong, early arcade games

### Level 2: Set Velocity
```
if (input) velocity = targetVelocity
position = position + velocity
```
- Input sets speed directly
- Feel: More responsive than position, but still abrupt
- Example: Some puzzle games

### Level 3: Apply Force (Acceleration)
```
if (input) acceleration = force
velocity = velocity + acceleration
velocity = velocity × friction
position = position + velocity
```
- Input adds force, velocity accumulates
- Feel: Fluid, physical, expressive
- Example: Mario, Asteroids, most modern games

---

## The Asteroids Recipe

The classic "spaceship" feel.

### Core Principle
**Separate thrust from rotation.**

### Variables
```
shipRotation          // Current facing angle
shipPosition          // X, Y coordinates
shipVelocity          // Current movement vector
thrustSpeed           // Current thrust magnitude
thrustAcceleration    // How fast thrust builds
thrustVelocity        // Force vector to add
maxThrustSpeed        // Speed cap
dampening             // Very low (0.99+)
```

### The Algorithm
```
// Rotation: Direct, instant
if (rotateLeft) shipRotation -= rotateSpeed
if (rotateRight) shipRotation += rotateSpeed

// Thrust: Simulated, accumulates
if (thrustButton) {
    thrustSpeed = min(thrustSpeed + thrustAcceleration, maxThrustSpeed)
    thrustVelocity = directionFromAngle(shipRotation) × thrustSpeed
    shipVelocity = shipVelocity + thrustVelocity
}

// Very low friction (space feel)
shipVelocity = shipVelocity × dampening

// Cap maximum speed
shipVelocity = clampMagnitude(shipVelocity, maxVelocity)

// Update position
shipPosition = shipPosition + shipVelocity

// Screen wrap
shipPosition = wrapToScreen(shipPosition)
```

### Key Insight
Thrust vector is ADDED to velocity, not overwriting it. This decouples rotation from movement direction, creating the "always on the edge of control" feel.

### Tuning Notes
- Rotation should be instant with very slight attack (~0.1s)
- Dampening very low: 4+ seconds to stop from full speed
- Screen wrap prevents escape, creates constant danger

---

## The Super Mario Bros Recipe

The gold standard for platformer feel.

### Core Principle
**Separate horizontal and vertical systems.**

### Horizontal Variables
```
walkAcceleration      // Force applied when walking
walkMaxSpeed          // Walking speed cap
runAcceleration       // Force when B held (higher)
runMaxSpeed           // Running speed cap (higher)
airAcceleration       // Reduced control in air
deceleration          // Friction when not pressing direction
```

### Vertical Variables
```
gravity               // Constant downward force
initialJumpForce      // Upward velocity on button press
minJumpTime           // Minimum button hold for jump
maxJumpTime           // Maximum button hold for jump
reducedJumpVelocity   // Velocity set on early release
fallGravity           // Gravity after apex (3× normal!)
terminalVelocity      // Maximum fall speed
```

### Horizontal Movement
```
if (leftOrRight) {
    if (onGround) {
        if (runButton) {
            velocity.x += runAcceleration × direction
            velocity.x = clamp(velocity.x, -runMaxSpeed, runMaxSpeed)
        } else {
            velocity.x += walkAcceleration × direction
            velocity.x = clamp(velocity.x, -walkMaxSpeed, walkMaxSpeed)
        }
    } else {
        // Reduced air control
        velocity.x += airAcceleration × direction
    }
} else {
    // Apply deceleration toward zero
    velocity.x = moveToward(velocity.x, 0, deceleration)
}
```

### Vertical Movement (The Jump)
```
// Gravity always applied
velocity.y -= gravity

// Jump initiation
if (jumpButtonPressed && onGround) {
    velocity.y = initialJumpForce
    jumpHoldTime = 0
    isJumping = true
}

// Jump extension while held
if (isJumping && jumpButtonHeld) {
    jumpHoldTime += deltaTime
    if (jumpHoldTime < maxJumpTime) {
        // Continue applying upward force
        velocity.y = initialJumpForce
    }
}

// THE CRITICAL HACK: Early release handling
if (isJumping && jumpButtonReleased) {
    if (velocity.y > reducedJumpVelocity) {
        velocity.y = reducedJumpVelocity  // Artificial cap!
    }
    isJumping = false
}

// Increased fall gravity after apex
if (velocity.y < 0) {
    velocity.y -= fallGravity  // 3× normal gravity!
}

// Terminal velocity
velocity.y = max(velocity.y, -terminalVelocity)
```

### Why the "Hack" Works
Setting velocity to a fixed low value on early release:
1. Creates consistent arc shapes
2. Maintains graceful motion
3. Provides clear minimum jump height
4. Feels natural despite being artificial

### Running Jump Boost
```
if (jumpButtonPressed && speed > walkMaxSpeed) {
    initialJumpForce *= 1.1  // Slight boost
}
```

---

## The Mario 64 Recipe

Translating platformer feel to 3D.

### Core Additions for 3D

**Camera-Relative Input**
```
// Thumbstick direction relative to camera, not character
worldDirection = cameraForward × stick.y + cameraRight × stick.x
```

**Turn Interpolation**
```
// Blend toward desired direction for carving motion
if (speed > 0) {
    currentDirection = lerp(currentDirection, desiredDirection, turnSpeed)
} else {
    currentDirection = desiredDirection  // Instant at standstill
}
```

**Incline Physics**
```
groundAngle = getGroundAngle()
if (groundAngle > slideThreshold) {
    // Enter slide state
    state = SLIDING
    velocity += getDownhillVector() × slideAcceleration
}
```

### Multiple Jump Types

| Jump | Trigger | Properties |
|------|---------|------------|
| **Basic** | A button | Variable height (hold-sensitive) |
| **Continuous** | A after landing | Higher, still variable |
| **Triple** | A after Continuous + speed | Fixed trajectory, highest |
| **Long** | Z+A while moving | Fixed, horizontal emphasis |
| **Back Somersault** | A while ducking | Fixed, highest vertical |
| **Side Somersault** | A during direction change | Fixed, high |
| **Wall Kick** | A near wall + away input | Fixed |

### Fixed vs Variable Trajectories
- **Variable** (basic): Expressive, moment-to-moment control
- **Fixed** (special): Predictable, precision platforming

### The Ground Pound
```
if (inAir && zButtonPressed) {
    velocity.x = 0
    velocity.z = 0
    // Pause briefly
    wait(0.1)
    // Slam down with high gravity
    velocity.y = -groundPoundSpeed
}
```
Provides precision landing by removing horizontal momentum.

---

## Tuning Guidelines

### For "Tight" Feel
- High acceleration values
- Short attack times (<0.1s)
- Moderate deceleration
- Quick release phase

### For "Floaty" Feel
- Low acceleration values
- Long attack times (0.3-0.5s)
- Low deceleration (high inertia)
- Long release phase

### For "Weighty" Feel
- Strong gravity
- Even stronger fall gravity
- Moderate acceleration
- Pronounced squash/stretch animation

### For "Responsive" Feel
- <100ms input-to-response
- Direct mapping where possible
- Visual feedback on frame 1
- Sound on input, not on action completion

---

## Common Pitfalls

### Problem: Character won't stop
**Cause**: No deceleration when input stops
**Fix**: Apply friction force toward zero velocity

### Problem: Jump feels "swimmy"
**Cause**: Same gravity up and down
**Fix**: Increase fall gravity (2-3× normal)

### Problem: Controls feel random
**Cause**: Variable attack/release based on frame timing
**Fix**: Use fixed-timestep physics, frame-independent values

### Problem: Can't make precise movements
**Cause**: Only high-speed movement available
**Fix**: Add acceleration curve, lower minimum speed threshold

### Problem: Character slides off platforms
**Cause**: Deceleration too slow, momentum carries past edge
**Fix**: Increase deceleration, or snap to platform edges
