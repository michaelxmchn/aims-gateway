# Procedural and Handmade Level Design Integration

Based on Chapter 11: "Integrating Procedural and Handmade Level Design" by Mark R. Johnson.

## The Two Approaches

### Procedural Content Generation (PCG)
Algorithmic creation of game content: levels, items, enemies, stories.

**Strengths:**
- Massive replay value
- Reduced development time per unit content
- Surprise even for developers
- Adaptive difficulty potential

**Weaknesses:**
- Can feel same-y across generations
- Difficult to guarantee specific experiences
- Narrative hard to generate
- Quality floors vary

### Handmade Content
Designer-crafted levels and experiences.

**Strengths:**
- Precise control over experience
- Guaranteed quality
- Narrative coherence
- Specific memorable moments

**Weaknesses:**
- Time-intensive
- Limited replay value
- Players eventually memorize content
- Scaling difficult

---

## Why Integrate?

Neither approach alone serves all needs. Integration strategies leverage strengths of both.

### What PCG Struggles With
- Coherent multi-step narratives
- Meaningful puzzle design
- Guaranteed dramatic moments
- Consistent thematic experience

### What Handmade Adds
- Narrative anchors
- Quality guarantees
- Specific gameplay challenges
- Memorable set pieces

---

## Two Integration Models

### Vertical Integration
A handmade thread runs *through* procedural content.

**Characteristics:**
- Linear progression of handmade elements
- Procedural content surrounds the thread
- Players encounter handmade content in sequence
- Thread spans significant portion of game

**Best for:**
- Narrative sequences
- Multi-step puzzles
- Quest chains
- Story progression

**Examples:**
- FTL: Quest nodes distributed through procedural star map
- Spelunky: Secret item chain requiring precise sequence

### Horizontal Integration
Procedural and handmade content are *interchangeable* in the same slot.

**Characteristics:**
- Either type can appear in any given location
- Modular substitution
- No linear progression requirement
- Same slot, different fill

**Best for:**
- Room-by-room variety
- Guaranteed gameplay instances
- Quality floors
- Encounter variation

**Examples:**
- Dungeon Crawl Stone Soup: Vaults among procedural rooms
- Ultima Ratio Regum: Handmade variants mixed with procedural

---

## Case Study: FTL (Vertical)

### Structure
- Nodes on a star map
- Most nodes procedural
- Some nodes are quest-specific (handmade)
- Quest nodes appear in sequence across sectors

### Integration
- Procedural: Combat encounters, shops, empty space
- Handmade: Multi-part quests, story events, special encounters

### Player Experience
- Procedural nodes provide variety
- Quest nodes provide narrative progression
- Players choose path but hit quest nodes as they progress

---

## Case Study: Dungeon Crawl Stone Soup (Horizontal)

### Structure
- Procedurally generated dungeon floors
- "Vaults" are handmade rooms/areas
- Vaults appear among procedural content

### Integration
- Procedural: Standard dungeon rooms, corridors
- Handmade: Vaults with curated enemy/loot combinations

### Visibility
DCSS makes the difference **obvious**:
- Vaults visually distinct
- Players recognize human design
- Creates risk/reward choice ("explore vault?")

### Purpose
- Visual variety
- Gameplay pacing
- Optional challenge/reward

---

## Case Study: Spelunky (Vertical)

### Structure
- Procedurally generated platformer levels
- Hidden secret sequence spans entire game
- Specific items must be collected in order

### The Secret Chain
1. Find key + chest in Mines → get Udjat Eye
2. Udjat Eye reveals Black Market → get Ankh
3. Die with Ankh near Moai → get Hedjet
4. Kill Anubis → get Scepter
5. Use Scepter in Temple → access City of Gold
6. Get Book of Dead → reveals Hell entrance

### Integration
- Procedural: Level geometry, enemy placement, item locations
- Handmade: The sequence itself, specific item interactions

### Player Experience
- Most players never see the secret
- Skilled players work toward it
- Each step is procedurally placed but handmade in design

---

## Case Study: Ultima Ratio Regum (Horizontal, Hidden)

### Philosophy
Blur the line between procedural and handmade so players can't tell which is which.

### Implementation
- Most systems can output procedural OR handmade content
- Same slot might get generated altar or preset altar
- Player cannot distinguish source

### Goals
1. Handmade might be perceived as procedural (quality validation)
2. Procedural perceived as handmade (quality achievement)
3. Guaranteed interesting content without telegraphing it

### Example: Buildings
- Cathedrals: Highly procedural (few constraints, sprawling)
- Mansions: More handmade (many required rooms, specific layouts)
- Constraint level determines procedural/handmade ratio

---

## Key Design Questions

### Should Players Know?

**Make it obvious (DCSS approach):**
- Visual variety
- Risk/reward signaling
- Gameplay pacing tool
- Player can choose engagement level

**Hide it (URR approach):**
- Seamless experience
- Quality perception uniform
- No "content type" metagaming
- Procedural must meet handmade quality bar

### What Should Be Handmade?

**Vertical model uses handmade for:**
- Narrative threads
- Puzzle sequences
- Story progression

**Horizontal model uses handmade for:**
- Quality guarantees
- Specific gameplay moments
- Variety injection

---

## Practical Considerations

### Procedural Constraints
The more constraints on generation, the more similar outputs become.

**High constraints = handmade-like results**
- May need to shift toward handmade
- Example: Mansions require many rooms → layouts converge

**Low constraints = high variety**
- Procedural works well
- Example: Cathedrals with few requirements → high variety

### Development Timeline
- Procedural systems: High upfront cost, low marginal cost
- Handmade content: Linear cost per unit
- Integration requires both investments

### Testing Considerations
- Procedural needs testing across many generations
- Handmade needs testing of specific content
- Integration needs testing of transitions/interactions

---

## Future Directions

### What's Hard to Generate
- Multi-node narratives
- Complex puzzles
- Coherent story progression

These remain primarily handmade.

### What's Improving
- Room-level generation
- Enemy placement
- Loot distribution
- Environmental variety

Integration will likely expand as generation quality improves.

---

## Summary

1. **Neither pure approach is sufficient** — Integration leverages both
2. **Vertical integration** — Handmade thread through procedural space (narrative, quests)
3. **Horizontal integration** — Interchangeable modules (rooms, encounters)
4. **Visibility is a design choice** — Obvious vs hidden integration serves different goals
5. **Constraints determine ratio** — More constraints → more handmade needed
6. **Quality bars matter** — Procedural must meet handmade standards for hidden integration
