# Scales Reference

Complete scale formulas and pentatonic patterns for guitar fretboard visualization.

## Scale Formulas (Semitones from Root)

### Major Modes
| Mode | Formula | Intervals | Character |
|------|---------|-----------|-----------|
| Ionian (Major) | 0,2,4,5,7,9,11 | 1-2-3-4-5-6-7 | Bright, happy |
| Dorian | 0,2,3,5,7,9,10 | 1-2-b3-4-5-6-b7 | Minor with bright 6th |
| Phrygian | 0,1,3,5,7,8,10 | 1-b2-b3-4-5-b6-b7 | Spanish/exotic |
| Lydian | 0,2,4,6,7,9,11 | 1-2-3-#4-5-6-7 | Dreamy, floating |
| Mixolydian | 0,2,4,5,7,9,10 | 1-2-3-4-5-6-b7 | Dominant, bluesy |
| Aeolian (Natural Minor) | 0,2,3,5,7,8,10 | 1-2-b3-4-5-b6-b7 | Sad, dark |
| Locrian | 0,1,3,5,6,8,10 | 1-b2-b3-4-b5-b6-b7 | Unstable, diminished |

### Pentatonic Scales
| Scale | Formula | Notes (from C) |
|-------|---------|----------------|
| Major Pentatonic | 0,2,4,7,9 | C-D-E-G-A |
| Minor Pentatonic | 0,3,5,7,10 | C-Eb-F-G-Bb |
| Blues | 0,3,5,6,7,10 | C-Eb-F-Gb-G-Bb |

### Other Common Scales
| Scale | Formula |
|-------|---------|
| Harmonic Minor | 0,2,3,5,7,8,11 |
| Melodic Minor (asc) | 0,2,3,5,7,9,11 |
| Whole Tone | 0,2,4,6,8,10 |
| Diminished (W-H) | 0,2,3,5,6,8,9,11 |
| Diminished (H-W) | 0,1,3,4,6,7,9,10 |

## Pentatonic Pattern Positions

### Minor Pentatonic - 5 Box Patterns

Each pattern spans approximately 4 frets. Root note positions marked with (R).

**Pattern 1** (Root Position for Minor)
```
e|---(R)----3---|
B|---(R)----3---|
G|---0------2---|
D|---0------2---|
A|---(R)----3---|
E|---(R)----3---|
```

**Pattern 2**
```
e|---0------3---|
B|---0------2---|
G|---0------(R)-|
D|---0------3---|
A|---0------3---|
E|---0------3---|
```

**Pattern 3**
```
e|---0------2---|
B|---(R)----2---|
G|---0------2---|
D|---0------2---|
A|---0------2---|
E|---0------2---|
```

**Pattern 4**
```
e|---0------3---|
B|---0------3---|
G|---0------2---|
D|---(R)----2---|
A|---0------3---|
E|---0------3---|
```

**Pattern 5**
```
e|---0------3---|
B|---0------3---|
G|---0------3---|
D|---0------2---|
A|---0------2---|
E|---(R)----3---|
```

## Relative Major/Minor Relationships

- A minor pentatonic = C major pentatonic (3 semitones apart)
- E minor pentatonic = G major pentatonic
- Pattern 1 minor = Pattern 5 relative major (same shapes, different root)

## Scale Implementation Code

```javascript
const SCALES = {
  // Major modes
  major: [0, 2, 4, 5, 7, 9, 11],
  dorian: [0, 2, 3, 5, 7, 9, 10],
  phrygian: [0, 1, 3, 5, 7, 8, 10],
  lydian: [0, 2, 4, 6, 7, 9, 11],
  mixolydian: [0, 2, 4, 5, 7, 9, 10],
  minor: [0, 2, 3, 5, 7, 8, 10],
  locrian: [0, 1, 3, 5, 6, 8, 10],
  
  // Pentatonics
  majorPentatonic: [0, 2, 4, 7, 9],
  minorPentatonic: [0, 3, 5, 7, 10],
  blues: [0, 3, 5, 6, 7, 10],
  
  // Other
  harmonicMinor: [0, 2, 3, 5, 7, 8, 11],
  melodicMinor: [0, 2, 3, 5, 7, 9, 11],
  wholeTone: [0, 2, 4, 6, 8, 10]
}

// Get all notes in a scale
const getScaleNotes = (rootNote, scaleType) => {
  const NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
  const rootIndex = NOTES.indexOf(rootNote)
  const formula = SCALES[scaleType]
  return formula.map(interval => NOTES[(rootIndex + interval) % 12])
}
```

## Scale Degree Colors

Recommended color coding for fretboard visualization:

| Degree | Interval | Color | Hex |
|--------|----------|-------|-----|
| 1 (Root) | Unison | Red | #ef4444 |
| 2 | Major 2nd | Orange | #f97316 |
| b3 | Minor 3rd | Yellow | #eab308 |
| 3 | Major 3rd | Green | #22c55e |
| 4 | Perfect 4th | Teal | #14b8a6 |
| b5 | Tritone | Cyan | #06b6d4 |
| 5 | Perfect 5th | Blue | #3b82f6 |
| b6 | Minor 6th | Indigo | #6366f1 |
| 6 | Major 6th | Violet | #8b5cf6 |
| b7 | Minor 7th | Purple | #a855f7 |
| 7 | Major 7th | Pink | #ec4899 |
