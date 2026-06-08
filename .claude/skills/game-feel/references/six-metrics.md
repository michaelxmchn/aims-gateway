# The Six Metrics of Game Feel

A framework for measuring and comparing how games feel, enabling meaningful analysis across different games.

## Overview

| Metric | Question It Answers |
|--------|---------------------|
| **Input** | What signals enter the system? |
| **Response** | How do signals change the game? |
| **Context** | What space gives meaning to motion? |
| **Polish** | What effects sell the interactions? |
| **Metaphor** | What expectations does representation create? |
| **Rules** | What game rules affect moment-to-moment feel? |

---

## 1. Input Metrics

### Physical Device Properties
- **Ergonomics**: How does it feel to hold?
- **Button quality**: Springy, mushy, clicky?
- **Build quality**: Solid, cheap, premium?

### Signal Properties

| Property | Description | Example |
|----------|-------------|---------|
| **States** | How many positions? | 2 (button), 360° (stick) |
| **Signal type** | Boolean or continuous? | On/off vs 0.0-1.0 |
| **Sensitivity** | How much variance detected? | Analog stick precision |
| **Combination** | What can be pressed together? | Chords, simultaneous inputs |

### Signal Interpretations
Raw signals can be interpreted as:
- **Instant**: Up, Down
- **Over time**: Pressed, Held, Released
- **Duration**: How long held
- **Sequence**: Button combinations over time

### Input Space
The total possible inputs at any moment:
- NES controller: 8 buttons, simple combinations
- Modern controller: 15+ inputs, analog sticks, triggers
- More input space = more potential expressivity

---

## 2. Response Metrics

### Mapping Types

| Type | Description | Feel |
|------|-------------|------|
| **Direct** | Input directly sets value | Responsive but limited |
| **Indirect** | Input modifies simulation | Expressive but complex |
| **State change** | Input switches behavior modes | Enables move variety |

### What Gets Modulated

Response can change:
- **Position** (teleport-like, stiff)
- **Velocity** (speed changes)
- **Acceleration** (force applied)
- **Simulation parameters** (gravity, friction)
- **Character state** (walking→running→jumping)

### ADSR Envelope Measurements

For any response, measure:
- **Attack**: Time to reach full response
- **Decay**: Time to settle to sustained level
- **Sustain**: Level maintained while input held
- **Release**: Time to return to neutral after input stops

### Expressivity
How many different outcomes are possible from the same basic action?

Low expressivity: Jump always same height
High expressivity: Jump height varies with button hold time

---

## 3. Context Metrics

### Spatial Relationships

| Relationship | Measure |
|--------------|---------|
| **Density** | Objects per unit area |
| **Spacing** | Distance between interaction points |
| **Scale** | Object size relative to avatar |
| **Variety** | How much spacing varies |

### Context-Mechanic Fit

The key question: Does the space match the avatar's capabilities?

- Jump height → Platform heights
- Run speed → Corridor widths
- Stopping distance → Gap before hazards
- Turn radius → Corner angles

### Collision Properties
- **Friction**: How much does contact slow movement?
- **Bounciness**: Do objects rebound?
- **Passability**: What can be moved through?

---

## 4. Polish Metrics

### Effect Categories

| Category | Examples |
|----------|----------|
| **Particles** | Dust, sparks, debris |
| **Screen effects** | Shake, flash, zoom |
| **Animation** | Squash/stretch, anticipation, follow-through |
| **Sound** | Impact sounds, ambient, UI feedback |
| **Haptics** | Controller rumble patterns |

### Measuring Polish Quality

**Coherence**: Do effects tell the same story?
- Big hit = big sound + big shake + big particles

**Synchronization**: Do effects align with action?
- Footstep sounds sync with animation frames

**Proportionality**: Do effect intensities scale appropriately?
- Light impact → small effect
- Heavy impact → large effect

### The Three-Tier System
Many games use light/medium/heavy impact tiers:
- Each tier has distinct animation, sound, and visual effect
- Creates clear hierarchy of interaction intensity

---

## 5. Metaphor Metrics

### Representation Scale

| Level | Description | Example |
|-------|-------------|---------|
| **Abstract** | Shapes, no real-world analog | Geometry Wars |
| **Iconic** | Recognizable but stylized | Mario |
| **Representational** | Realistic depiction | Uncharted |

### Expectation Setting

Metaphor creates expectations about:
- **Weight**: Heavy things should feel heavy
- **Speed**: Cars should feel faster than people
- **Friction**: Ice should be slippery
- **Damage**: Fire should hurt

### Treatment Consistency
Does the visual style match across elements?
- Mario: All cartoony = unified expectations
- Mixing realistic and cartoony = confused expectations

### Exceed vs Meet Expectations
- **Exceed**: Feels better than it looks (good)
- **Meet**: Feels as expected (neutral)
- **Fail**: Looks better than it feels (bad)

---

## 6. Rules Metrics

### Rules That Affect Feel

| Rule Type | Feel Impact |
|-----------|-------------|
| **Health/damage** | Risk perception, caution level |
| **Lives/continues** | Tension, stakes |
| **Scoring** | Motivation for precision |
| **Unlocks** | Expanding capability |
| **Time limits** | Urgency, rushing |

### State-Affecting Rules

Rules that change available actions:
- Power-ups granting new moves
- Damage reducing capabilities
- Context-sensitive actions

### Risk/Reward Rules

Rules that create feel through consequence:
- High-risk maneuvers = high reward
- Safe play = low reward
- Creates reason to master difficult techniques

---

## Using the Metrics

### For Analysis
When analyzing an existing game:
1. Document each metric category
2. Note how they interact
3. Identify what creates the distinctive feel

### For Design
When designing new feel:
1. Start with desired feel description
2. Work backward to required metrics
3. Tune each category to support the goal

### For Comparison
Comparing two games:
1. Measure same metrics for both
2. Note where they differ
3. Correlate differences to feel differences

### For Debugging
When feel is wrong:
1. Identify the symptom
2. Check metrics in likely categories
3. Adjust and test

---

## Metric Interactions

The six metrics don't exist in isolation:

- **Input + Response**: How signals become actions
- **Response + Context**: Whether avatar fits the space
- **Context + Polish**: Environmental feedback
- **Polish + Metaphor**: Whether effects match representation
- **Metaphor + Rules**: Whether game logic fits the world
- **Rules + Input**: What actions are meaningful

The best game feel comes from all six working in harmony.
