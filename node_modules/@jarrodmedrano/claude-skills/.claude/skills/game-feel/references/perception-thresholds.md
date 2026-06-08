# Perception Thresholds for Game Feel

Understanding human perception limits is essential for creating responsive controls.

## The Model Human Processor

Card, Moran, and Newell's research established three processors working in sequence:

### Processor Cycle Times

| Processor | Average | Range | Function |
|-----------|---------|-------|----------|
| **Perceptual** | ~100ms | 50-200ms | Takes sensory input, finds patterns |
| **Cognitive** | ~70ms | 30-100ms | Compares state to intent, decides action |
| **Motor** | ~70ms | 25-170ms | Translates decision to muscle movement |

**Total correction cycle: ~240ms**

This is the minimum time for a human to:
1. See the current state
2. Think about what to do
3. Act on that decision

## The Correction Cycle in Games

When controlling a game, players run continuous correction cycles:

```
Intent (grab coin) 
    → Perceive (see Mario's position)
    → Think (too far right)
    → Act (press left)
    → Perceive (see Mario move)
    → Think (almost there)
    → Act (release, press jump)
    → ...repeat at ~240ms intervals
```

This is identical to reaching for a muffin on your desk—constant micro-adjustments until the goal is achieved.

## Critical Thresholds for Game Response

### Frame Rate (Impression of Motion)

| FPS | Milliseconds | Perception |
|-----|--------------|------------|
| 10 | 100ms | Minimum for motion illusion |
| 20 | 50ms | Acceptable motion |
| 30 | 33ms | Smooth motion |
| 60 | 16ms | Very smooth |
| 120+ | <8ms | Diminishing returns for most |

**Why it matters**: Below 10fps, the brain sees discrete images, not motion. The illusion breaks.

### Response Time (Input to Visual Feedback)

| Response | Feel | Notes |
|----------|------|-------|
| <50ms | Instantaneous | "Extension of your body" |
| 50-100ms | Tight, responsive | Ideal for action games |
| 100-150ms | Noticeable but acceptable | Strategy games tolerate this |
| 150-200ms | Sluggish | Players complain |
| >240ms | Broken | Exceeds correction cycle |

**The 50ms rule**: At 50ms or less, cause and effect feel simultaneous due to perceptual fusion.

### Continuity (Consistent Response Rate)

The game must accept input and provide feedback at **consistent 100ms intervals or less**.

Sporadic response is worse than slow response:
- Consistent 80ms = acceptable
- Varying 40-200ms = feels broken

## Perceptual Fusion

When two events occur within the same perceptual cycle (~100ms), they appear fused:

- Mario in position A, then position B within 100ms = perceived as motion
- Button press and character response within 100ms = perceived as cause-and-effect

**This is how games create the illusion of direct control.**

## Fitt's Law Application

The time to reach a target depends on distance and target size:

```
MT = a + b × log₂(2D/W)

MT = movement time
a = start/stop time
b = device speed
D = distance to target
W = target width
```

**Game design implications**:
- Larger targets = faster to hit
- Closer targets = faster to hit
- Menu items at screen edges = effectively infinite width
- Tiny checkboxes = frustrating

## Factors That Affect Perception Speed

### Faster Processing
- High alertness/stress
- Familiar tasks
- Clear visual feedback
- Predictable patterns

### Slower Processing
- Fatigue
- Distraction
- Poor visibility
- Novel situations

## Measuring Your Own Response Time

Test at humanbenchmark.com/tests/reactiontime

Typical results:
- Average person: 200-250ms
- Trained gamer: 150-180ms
- Theoretical minimum: ~150ms

This represents perception + cognition + motor response combined.

## Practical Guidelines

### For Responsive Feel
1. Target <100ms input-to-display
2. Maintain consistent frame rate (30+ fps)
3. Never exceed 240ms response time
4. Use animation to mask unavoidable delays

### Acceptable Delay Contexts
Delays can be acceptable when:
- Player chose to trigger a long animation
- Metaphor supports it (heavy character)
- Risk/reward tradeoff is clear
- Delay is consistent and predictable

### Breaking Feel Intentionally
Sometimes you want temporary loss of control:
- Recovery frames after attacks (fighting games)
- Stumble animations after hits
- Charge-up mechanics

**Key**: Player must have chosen to enter the vulnerable state.

## The Computer's Responsibility

Real-time control requires the computer to maintain:

1. **Motion threshold**: Display updates at 10+ fps (ideally 30+)
2. **Response threshold**: Input-to-display in <240ms (ideally <100ms)
3. **Continuity threshold**: Consistent update rate at 100ms or less

If any threshold is violated, the player will notice. If response exceeds 240ms, real-time control is broken entirely.
