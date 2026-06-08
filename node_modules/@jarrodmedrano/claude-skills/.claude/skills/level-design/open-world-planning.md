# Open-World Level Design Planning

Based on Chapter 12: "Level Design Planning for Open-World Games" by Joel Burgess (Bethesda Game Studios).

## The Three Elements

Open-world planning requires three living documents that evolve throughout development:

1. **The World Map** — Spatial visualization
2. **The Master List** — High-level data tracking (Excel)
3. **The Directory** — Per-location details (Wiki)

---

## Element 1: The World Map

### Purpose
The map is the most vital piece of design documentation. It instantly communicates setting, scale, regions, and anchor locations.

### Key Questions
- Where does the game take place? (real vs fictional)
- What subregions exist within the map?
- What is the scale and density?
- What major geographical features exist?
- What natural boundaries can you leverage?

### Working with Real-World Locations

**Advantages:**
- Pre-existing history and culture
- Geography already makes sense
- Reference material abundant

**Challenges:**
- 100% accuracy rarely equals good gameplay
- Must balance authenticity with playability
- Need to understand *essence*, not just details

**Fallout Approach:**
Get relative positions and surroundings correct for landmarks. Highlight evocative elements. Omit less useful details.

### Subregions

Create variety within the larger world:
- Different biomes
- Different cultures
- Different moods

**Skyrim's Seasonal Subregions:**
- The Rift: perpetual autumn
- Haafinagar: bleak winter
- Falkreath: eternal spring

No actual seasons simulated—each region *is* a season.

### Transitions Between Subregions
- Leave ample room to blend
- Use geographical features (cliffs, rivers) for sharper transitions
- Water boundaries make rapid shifts more believable

### Orienting Features

Include landmarks visible from anywhere:
- **Skyrim**: High Hrothgar at center
- **Fallout 4**: Boston skyline (Mass Fusion building's distinctive crown)

Two-point orientation systems work well (financial district + Trinity Tower).

### Boundaries

**Natural boundaries (preferred):**
- Water (oceans, lakes, rivers)
- Cliffs
- Dense forests/marshes
- Mountains

**Artificial boundaries (avoid when possible):**
- Invisible walls with "You cannot go that way"
- Fences that should be climbable
- Any barrier that draws attention

**Making Boundaries Work:**
- GTAV: Swim out far enough and sharks eat you
- Ark: Exhaustion + marine enemies before invisible wall
- Buffer of "boring space" before hard boundary

---

## Element 2: The Master List

### Purpose
A spreadsheet tracking every location with filterable, sortable data. Best tool for high-level analysis.

### Basic Columns
| Name | X | Y | Designer | Quest | Footprint |
|------|---|---|----------|-------|-----------|
| Diamond City | 5 | -6 | Jane | MQ101 | Lg |
| Sanctuary | -2 | 4 | Bob | MQ001 | Md |

### Coordinate System
Use units that match your game engine. Bethesda uses "cells" consistently across games.

### Plotting the Map

Create a scatter graph in Excel:
1. X/Y data from location columns
2. Set axis bounds to match map proportions
3. Use map image as plot background
4. Plot points overlay on map

Now you can visualize location distribution automatically.

### Footprint Radii

Track location sizes (Sm/Md/Lg) and visualize with different marker sizes on the scatter plot.

**Note:** Footprint ≠ complexity. A tiny exterior might hide a massive underground area.

### Filter Visualizations

Add columns for:
- Encounter type
- Difficulty
- Architectural style
- Quest associations
- Development status

Filter columns to see distribution patterns instantly.

### Quest Route Visualization

Plot quest sequences as line series:
1. Create list of locations in quest order
2. Add as new data series
3. Display as connected line

Instantly see the physical journey players will take.

---

## Element 3: The Directory

### Purpose
Long-form documentation for individual locations. Where designers track detailed, evolving information.

### Platform
Wiki works best (MediaWiki recommended). Collaborative, searchable, categorizable.

### Per-Location Pages Should Include:

**Header Data:**
- Designer assigned
- Quadrant/coordinates
- Encounter type
- Difficulty rating
- Quest associations

**Body Sections:**
- Overview: What is this place?
- Goals: What experience should it deliver?
- Walkthrough: How to test/reach it
- Pass notes: Feedback from each iteration
- Known issues: Current bugs and workarounds
- To-do: Designer's personal task list

### Category Tags
Enable filtering by:
- Designer name
- Development pass status
- Location type
- Quest line

### Naming Convention
Simple codes: DN004 = Dungeon #4
Use consistently across master list and directory.

---

## POI Density

### Definition
The frequency of points of interest in a given area.

### The Spectrum

**Sparse (Just Cause):**
- Long drives between locations
- Vehicles essential
- World feels vast and empty (intentionally)

**Dense (GTA cities):**
- Compressed real-world distances
- Something around every corner
- Theme park feel

**Non-uniform (Fallout 4, Skyrim):**
- Urban cores dense
- Rural areas sparse
- Small pockets of density for towns

### Consider Travel Method
- On foot: higher density needed
- Vehicle: can afford sparser distribution
- Fast travel: density matters less for return visits

---

## Anchor Locations

Locations you know must exist early:
- Story-critical places
- Real-world landmarks (if applicable)
- Major navigation features
- Key narrative beats

Plot these first. Other locations fill around them.

### Wish List Locations
Ideas you'd like to include but aren't critical:
- Minor landmarks
- Novel encounter concepts
- Infrastructure (power stations, farms)
- World-building details

Build wish list to roughly equal target location count.

---

## Iterative Development Passes

### Pass Zero: Pitch
- Complete master list exists
- Directory template established
- No technical requirements
- Each location assigned to a designer

### Pass One: Layout
- Basic environment art in place
- "Graybox" equivalent with modular kits
- Spatial relationships established

### Pass Two: Gameplay
- Core gameplay systems available
- Enemy placement and encounters
- First draft of pacing and challenge

### Pass Three: Content Complete
- All content present (if rough)
- "Ship with shame" milestone
- Everything playable end-to-end

### Art Pass
- Lighting, atmospherics, clutter
- Visual polish
- Collaboration between designers and artists

### Pass Four+: Polish
- Bug fixes
- Balance tuning
- Additional passes for problem areas or promising locations

---

## Practical Wisdom

### Documentation Lifecycle
> "We ship games, not documents."

Keep documentation useful but don't over-maintain. Let documents go fallow once they've served their purpose.

### Metrics and Scheduling
- Base estimates on average/below-average designers
- Plan for worst case
- Leave emergency time

> "No plan survives first contact with the enemy."

### Pride of Ownership
Try to keep designers with their locations throughout development. Ownership motivates.

### Map as Communication
The map unifies team perception. Print large versions. Reference constantly. It's your shared mental model.

---

## Summary

1. **Map first** — Establishes shared vision
2. **Master list** — Tracks and visualizes high-level data
3. **Directory** — Captures per-location detail
4. **Iterate** — Plan for multiple passes
5. **Density matters** — Defines exploration feel
6. **Natural boundaries** — Beat artificial walls
7. **Anchor then fill** — Critical locations first, then expand
