# Play-Personas for Player-Centered Level Design

Based on Chapter 13: "Play-Personas" by Alessandro Canossa (Northeastern University).

## Core Concept

Play-personas are **patterns of preferential interaction and navigation attitudes** that help designers:
1. Pre-figure player behavior before implementation (metaphor)
2. Evaluate actual player behavior after release (lens)

> "Level designers are designing spaces for players to act. Games must be played to fully exist."

---

## Why Play-Personas?

### The Problem of Scale
In a simple Pac-Man maze, there are 24 decision points with 2 choices each = 16,777,216 possible low-level behaviors.

**Solution:** Group low-level actions into high-level behaviors.

### High-Level Behaviors Example (Pac-Man)

| Low-Level | High-Level Behavior |
|-----------|---------------------|
| Move up/down/left/right | Center vs Periphery dwelling |
| Eat pills timing | Early vs Late pill eating |
| Direction changes | Linear vs Broken path |

Three binary high-level behaviors = 8 personas (2³)

---

## The Two Modes

### Play-Persona as Metaphor (A Priori)
**Before** the game exists or is playable:
- Hypothesize how players will behave
- Design levels to accommodate target behaviors
- Select which personas to design for

### Play-Persona as Lens (A Posteriori)
**After** players can be observed:
- Validate hypotheses with telemetry
- Discover unexpected behavioral clusters
- Evaluate if design supports intended personas

---

## The Six-Step Process

### Step 1: Gameplay Analysis
List all low-level mechanics, then abstract into high-level behaviors.

**Example: Left 4 Dead**

Low-level mechanics:
- Primary attack (ranged)
- Secondary attack (melee)
- Crouch-shooting
- Jump, reload, run
- Use items (flashlight, medkit, pills, Molotov, pipe bomb)
- Change weapons

Abstracted to high-level behaviors:
- Aggressive vs Defensive playstyle
- Team-oriented vs Solo
- Resource-conserving vs Resource-spending
- Leading vs Following

### Step 2: Create Permutation Matrix

Plot all combinations of high-level behaviors:

| Profile | Aggressive? | Team? | Resource? |
|---------|-------------|-------|-----------|
| 1 | Yes | Yes | Conserving |
| 2 | Yes | Yes | Spending |
| 3 | Yes | No | Conserving |
| 4 | Yes | No | Spending |
| 5 | No | Yes | Conserving |
| 6 | No | Yes | Spending |
| 7 | No | No | Conserving |
| 8 | No | No | Spending |

### Step 3: Select the Cast
Choose 2-3 personas that:
- Align with design vision
- Represent meaningfully different experiences
- Are achievable given level constraints

**Don't design for all personas.** A fraidy-cat persona doesn't belong in late-game difficulty.

### Step 4: Associate Affordances with Behaviors

Build a thesaurus linking:

**Ludic affordances** (what players can do):
- Combat opportunities
- Resource locations
- Risk/reward placements

**Aesthetic affordances** (what players perceive):
- Color coding
- Architectural cues
- Sound design
- Lighting

**Example associations:**
- Bonus items near danger = rewards aggressive personas
- Safe routes with fewer rewards = supports cautious personas
- Team-required obstacles = enforces cooperative play

### Step 5: Orchestrate Throughout Level

Modulate which personas are viable at different points:
- Early game: Multiple personas viable
- Challenge sections: Specific personas rewarded
- Recovery sections: Safe personas viable again

**The designer controls** which behavioral profiles are available at any given time.

### Step 6: Validate with Telemetry

After playtesting, analyze:
- Do players cluster into expected personas?
- Did unexpected personas emerge?
- Are intended persona pathways actually used?

---

## Example: Pac-Man Personas

### The Matrix
| # | Center/Periphery | Pill Timing | Path Style |
|---|------------------|-------------|------------|
| 1 | Center | Early | Linear |
| 2 | Center | Early | Broken |
| 3 | Center | Late | Linear |
| 4 | Center | Late | Broken |
| 5 | Periphery | Early | Linear |
| 6 | Periphery | Early | Broken |
| 7 | Periphery | Late | Linear |
| 8 | Periphery | Late | Broken |

### Named Personas

**Fraidy Cat** (Profile 5):
- Periphery dweller
- Eats pills early (security)
- Linear path (predictable)
- Avoids ghosts at all costs

**Risk Taker** (Profile 4):
- Center dweller
- Delays pills (maximizes points)
- Broken path (responsive)
- Embraces ghost proximity

### Designing for Both

**For Fraidy Cat:**
- Safe peripheral routes
- Pills accessible from edges
- Escape paths from center

**For Risk Taker:**
- Bonus items in center
- Delayed rewards for pill timing
- Complex navigation challenges

---

## From Cooper's Personas

Traditional HCI personas (Alan Cooper) describe:
- Demographics
- Goals and motivations
- Behaviors and attitudes
- Fictional narrative details

### Play-Personas Differ

| Traditional | Play-Persona |
|-------------|--------------|
| Narrative description | Parametric model |
| Static profile | Dynamic behavior pattern |
| Pre-design only | Pre and post-design |
| Qualitative | Quantifiable |

---

## Practical Applications

### During Design
1. Identify core mechanics
2. Abstract to high-level behaviors
3. Generate persona matrix
4. Select target personas
5. Design affordances supporting those personas
6. Orchestrate persona viability through level

### During Testing
1. Instrument telemetry for high-level behaviors
2. Cluster player data
3. Compare to expected personas
4. Identify gaps between design intent and actual play

### Communication Tool
Personas provide shared language:
- "This section is designed for Risk Takers"
- "We need a Fraidy Cat path through here"
- "The telemetry shows most players are Profile 3"

---

## Benefits

1. **Avoid self-referential design** — Designers aren't the target players
2. **Enable diversity** — Design for multiple valid playstyles
3. **Focus effort** — Can't please everyone; pick meaningful personas
4. **Validate intent** — Telemetry confirms or refutes hypotheses
5. **Communicate clearly** — Shared vocabulary for team discussions

---

## Limitations

1. **Subjectivity** — Different designers derive different high-level behaviors
2. **Combinatorial explosion** — Many behaviors = many personas
3. **Selection bias** — Choosing which personas to design for shapes experience
4. **Telemetry requirements** — Validation requires instrumentation

---

## Key Insight

> "Play-personas represent means to imply metaphorically players during the design phase and also serve as lenses to evaluate finished levels."

The same framework works for planning AND evaluation—connect design intent to measurable player behavior.
