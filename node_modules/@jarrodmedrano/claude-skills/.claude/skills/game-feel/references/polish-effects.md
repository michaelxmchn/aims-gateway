# Polish Effects for Game Feel

Polish transforms mechanical interactions into visceral experiences. Without polish, even perfect mechanics feel flat and lifeless.

## Why Polish Matters

> "Because of the limited processing power, each individual effect is drop-dead simple. They harmonize so well, though, that the net effect is a powerful sense of physical properties."
> — On Asteroids

Polish accomplishes three things:
1. **Sells the interaction** — Makes virtual contact feel real
2. **Provides feedback** — Confirms player actions
3. **Creates consistency** — Builds coherent physical world

## The Polish Toolkit

### Visual Effects

| Effect | Use For | Example |
|--------|---------|---------|
| **Particles** | Impacts, movement, environment | Dust on landing, sparks on collision |
| **Screen shake** | Heavy impacts, explosions | Camera shake on ground pound |
| **Screen flash** | Damage, power-ups, transitions | White flash on hit |
| **Motion blur** | High speed, impacts | Blur during dash |
| **Distortion** | Energy, impacts, power | Shockwave ripple |
| **Squash/stretch** | Weight, anticipation | Character squashes on landing |
| **Trailing** | Fast movement, special moves | Afterimages during jump |

### Audio Effects

| Effect | Use For | Example |
|--------|---------|---------|
| **Impact sounds** | Collisions, attacks | Thud on landing |
| **Footsteps** | Movement grounding | Steps sync with animation |
| **Whooshes** | Fast movement | Swoosh during jump/swing |
| **UI sounds** | Feedback, confirmation | Click on menu selection |
| **Ambient** | Environmental presence | Wind, machinery |
| **Music stingers** | State changes, achievements | Jingle on item pickup |

### Haptic Effects

| Effect | Use For | Example |
|--------|---------|---------|
| **Rumble pulse** | Impacts, damage | Vibration on hit |
| **Sustained rumble** | Ongoing effects | Engine running |
| **Pattern rumble** | Footsteps, rhythm | Step-step-step pattern |

### Animation Polish

| Technique | Purpose | Example |
|-----------|---------|---------|
| **Anticipation** | Prepares viewer for action | Wind-up before jump |
| **Follow-through** | Completes action believably | Hair settling after landing |
| **Secondary motion** | Adds life and weight | Cape flowing behind |
| **Exaggeration** | Emphasizes key moments | Fist enlarges during punch |
| **Ease in/out** | Natural acceleration | Smooth start/stop |

## The Three-Tier Impact System

Many polished games use three impact levels:

### Light Impact
- Small particle burst
- High-pitched click sound
- Subtle/no screen shake
- Brief rumble pulse

### Medium Impact
- Moderate particle spray
- Mid-tone thud sound
- Slight screen shake
- Medium rumble

### Heavy Impact
- Large particle explosion
- Deep boom sound
- Strong screen shake
- Long rumble

**Application**: Map game interactions to appropriate tier:
- Walking into wall → Light
- Landing from jump → Medium
- Ground pound → Heavy

## Sound-Motion Harmony

### Pitch-Position Correlation
Mario's jump: Rising tone as he rises, falling tone as he falls.
Creates subconscious reinforcement of motion.

### Size-Pitch Correlation
- Large objects → Low sounds
- Small objects → High sounds
- Asteroids: Large asteroid explosion = deep boom, small = high ping

### Speed-Intensity Correlation
- Fast motion → Louder, more intense
- Slow motion → Quieter, more subtle

### Material-Sound Correlation
Footstep sounds change based on surface:
- Stone → Hard click
- Grass → Soft thud
- Metal → Metallic clang
- Water → Splash

## Animation Timing

### Sync Points
Critical moments when animation, sound, and effect must align:
- **Foot contact** — Footstep sound, dust particle
- **Impact moment** — Hit sound, screen shake, particle burst
- **Jump apex** — Can trigger state changes, sound shifts

### Frame-Perfect Events
Some events must happen on exact frames:
- Jump sound on frame 1 of jump
- Landing effect on exact frame of ground contact
- Attack hit on specific animation frame

## Screen Shake Best Practices

### Parameters to Control
- **Intensity** — How far camera moves
- **Duration** — How long shake lasts
- **Frequency** — How fast it oscillates
- **Decay** — How it diminishes over time
- **Direction** — Random, directional, or circular

### Guidelines
- Heavy impacts: High intensity, medium duration, fast decay
- Rumble effects: Low intensity, long duration, no decay
- Avoid constant shaking — loses impact
- Direction can indicate impact direction

### Common Mistake
Shake intensity too high → Nauseating, obscures action
Shake duration too long → Annoying, feels broken

## Crossover Sensation

When multiple mechanics exist, polish should reinforce their shared physics:

**Swimming feels floaty BECAUSE walking feels grounded**
- Same gravity system, different friction values
- Polish effects reflect this (bubbles vs dust)

**Flying defies THE SAME gravity that affects jumping**
- Player recognizes the relationship
- Polish should reference the shared system

## Asteroids Polish Case Study

Despite limited hardware, Asteroids achieves excellent polish through coherence:

### Visual-Audio Consistency
- Large asteroid → Deep boom, large debris
- Medium asteroid → Mid-pitch, medium debris
- Small asteroid → High ping, small debris
- Ship thruster → Lowest rumble (powerful device)

### Effect Cohesion
- Ship destruction → Breaks into component lines
- Asteroid destruction → Particle spray
- Consistent visual language

## Mario 64 Polish Case Study

### Three-Tier System
All interactions categorized as light/medium/heavy with corresponding:
- Animation intensity
- Sound pitch and volume
- Particle quantity
- Screen shake intensity

### Footstep Sophistication
- Sound varies by surface material
- Timing syncs with animation
- Volume scales with movement speed

### Mario's Vocalizations
- Rising yell during jump ascent
- Grunt on heavy landing
- "Wahoo!" on special jumps
- Reinforces motion with voice

### Impact Exaggeration
- Mario's fist enlarges during punch
- Foot enlarges during kick
- Sells the power of the impact

## Polish Implementation Checklist

For each player action, ensure:

- [ ] Immediate visual feedback (frame 1)
- [ ] Appropriate sound effect
- [ ] Animation supports the action
- [ ] Effect intensity matches action intensity
- [ ] Effects harmonize (don't contradict)
- [ ] Haptic feedback (if applicable)

## Common Polish Mistakes

### Over-Polish
Too many effects obscure the action. Know when to restrain.

### Inconsistent Polish
One action heavily polished, another bare. Feels uneven.

### Wrong Intensity
Light action with heavy polish (or vice versa). Creates confusion.

### Out of Sync
Sound slightly before or after visual. Breaks believability.

### Polish Without Purpose
Effects that don't reinforce an interaction. Just noise.

## The Minimum Viable Polish

If resources are limited, prioritize:

1. **Jump landing** — Players do this constantly
2. **Attack/hit confirmation** — Core gameplay feedback  
3. **Damage received** — Critical player information
4. **Movement sounds** — Grounds player in world
5. **UI feedback** — Confirms player inputs

## Testing Polish

### The Mute Test
Play with sound off. Can you still feel the impacts?
If not, visual polish is insufficient.

### The Blind Test  
Listen without watching. Can you tell what's happening?
If not, audio polish is insufficient.

### The Slow-Mo Test
Watch at reduced speed. Do effects align with actions?
Reveals timing issues.

### The Comparison Test
Compare to a polished reference game.
Note where your game feels "flat" by comparison.
