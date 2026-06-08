# ADSR Tuning for Game Feel

The ADSR envelope, borrowed from audio synthesis, provides a powerful framework for understanding and tuning game response curves.

## The ADSR Model

```
Level
  ^
  |     Decay
  |    /‾‾‾‾\
  |   /      \___________Sustain___________
  |  /Attack                               \
  | /                                       \Release
  |/                                         \
  +---------------------------------------------> Time
  Input Starts                            Input Ends
```

| Phase | Definition | Game Example |
|-------|------------|--------------|
| **Attack** | Time from input start to peak response | Acceleration from standstill |
| **Decay** | Time from peak to sustained level | Initial burst settling |
| **Sustain** | Level maintained while input held | Running at max speed |
| **Release** | Time from input end to neutral | Deceleration to stop |

## Why ADSR Matters for Feel

Most "feel" descriptions map directly to ADSR characteristics:

| Feel Term | Primary ADSR Factor |
|-----------|---------------------|
| Tight | Short Attack + Short Release |
| Floaty | Long Attack + Long Release |
| Responsive | Short Attack |
| Sluggish | Long Attack |
| Slippery | Long Release |
| Snappy | Short Attack + Short Release |
| Weighty | Medium Attack + Medium Release |

## Measuring ADSR in Games

### Attack Time
1. Start from neutral (stationary)
2. Press input
3. Measure time until maximum response reached

**Mario walk attack**: ~0.2 seconds
**Asteroids thrust attack**: ~0.3 seconds
**Donkey Kong walk attack**: ~0.03 seconds (nearly instant)

### Release Time
1. From sustained state (full speed)
2. Release input
3. Measure time until neutral (stopped)

**Mario release**: ~0.3 seconds
**Asteroids release**: ~4+ seconds
**Donkey Kong release**: ~0.03 seconds (nearly instant)

### Sustain Level
The maintained response value during continuous input.

**Mario walk sustain**: Walk max speed
**Mario run sustain**: Run max speed (higher)
**Asteroids sustain**: Max velocity (capped)

## Tuning Guidelines

### For Platformers (Mario-like)

```
Attack:  0.1 - 0.3 seconds
Decay:   Minimal (go straight to sustain)
Sustain: Max speed (walk or run)
Release: 0.2 - 0.4 seconds

Jump Attack: Instant (frame 1 response)
Jump Release: Variable based on button hold
```

### For Space Games (Asteroids-like)

```
Attack:  0.2 - 0.5 seconds
Decay:   Minimal
Sustain: Max thrust speed
Release: 2 - 5+ seconds (low friction)

Rotation Attack: Very short (0.05-0.1s)
Rotation Release: Instant (no inertia)
```

### For Racing Games

```
Acceleration Attack: 1-3 seconds (car builds speed)
Acceleration Sustain: Top speed
Braking Release: 0.5-1 second

Steering Attack: 0.1-0.2 seconds (turn-in)
Steering Release: 0.1-0.2 seconds (self-centering)
```

### For Fighting Games

```
Normal Attack: 2-5 frames attack (~0.03-0.08s)
Heavy Attack: 8-15 frames attack (~0.13-0.25s)
Recovery (Release): 5-20 frames depending on move

Movement Attack: Very short (instant response)
Movement Release: Very short (precise positioning)
```

## Attack Curves

Not all attacks are linear. Common curve shapes:

### Linear
```
Response
    |    /
    |   /
    |  /
    | /
    |/_____ Time
```
Steady increase. Feels mechanical.

### Ease-In (Slow Start)
```
Response
    |      _/
    |    _/
    |  _/
    | /
    |/_____ Time
```
Sluggish start, fast finish. Feels heavy.

### Ease-Out (Fast Start)
```
Response
    |  /‾‾‾
    | /
    |/
    |/
    |/_____ Time
```
Quick start, gradual finish. Feels responsive.

### Ease-In-Out
```
Response
    |    _--‾
    |  _/
    | /
    |/
    |/_____ Time
```
Smooth acceleration. Feels natural.

## Release Curves

### Linear Deceleration
Constant friction. Feels artificial but predictable.

### Exponential Decay
Fast initial slowdown, gradual final approach to zero.
Feels more natural, like real friction.

### Instant Stop
No release phase. Feels robotic, but precise.

## The Mario Jump ADSR

The Mario jump is a special case with modified ADSR:

```
        Variable Attack (button held)
             |
             v
Force   ____/‾‾‾\
            |    \
            |     \_ Apex
            |       \
            |        \ Accelerated Release (3× gravity)
            |         \
        ____+__________\____
            ^           ^
        Button       Button
        Pressed      Released
```

### Key Features:
1. **Attack is instant** (large force applied frame 1)
2. **Attack extends** while button held (up to max time)
3. **Early release** artificially caps upward velocity
4. **Release accelerates** (fall gravity > rise gravity)

## Practical Tuning Process

### Step 1: Identify Desired Feel
"I want movement to feel tight but not robotic"

### Step 2: Set Target ADSR Values
- Attack: 0.1s (responsive)
- Release: 0.15s (not instant, slight slide)
- Sustain: Based on desired max speed

### Step 3: Implement and Test
Build the basic response, measure actual values

### Step 4: Iterate
- Too floaty? Shorten attack and release
- Too stiff? Lengthen attack and release
- Too slippery? Shorten release specifically
- Too sticky? Shorten attack specifically

### Step 5: Test Edge Cases
- Direction reversal
- Stop from max speed
- Start from standstill
- Interrupting actions

## Common ADSR Mistakes

### All Values Same
Everything feels samey. Vary ADSR between actions.

### No Attack Phase
Movement feels robotic, digital, unnatural.

### No Release Phase
Stopping feels abrupt, jarring.

### Too Long Attack
Players feel input is being ignored.

### Too Long Release  
Players feel out of control.

### Inconsistent Curves
Different actions feel like different games.

## ADSR for Different Actions

| Action | Attack | Release | Notes |
|--------|--------|---------|-------|
| Walk | 0.1-0.2s | 0.2-0.3s | Moderate both |
| Run | 0.2-0.4s | 0.3-0.5s | Longer for weight |
| Jump | Instant | Gravity-driven | Special handling |
| Turn | 0.05-0.1s | 0.05-0.1s | Needs precision |
| Shoot | 0-0.03s | 0-0.03s | Near instant |
| Charge | 0.5-3s | Variable | Long attack is the point |
| Drift | N/A | 1-3s | Release IS the mechanic |

## Testing Tools

### Frame-by-Frame Analysis
Record gameplay at 60fps, step through frames
Count frames from input to response

### Value Visualization
Graph position/velocity over time
Look for smooth curves vs jagged transitions

### Comparison Recording
Record same action in reference game
Match curves to match feel
