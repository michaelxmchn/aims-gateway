# CAGED System Reference

The CAGED system connects 5 open chord shapes (C, A, G, E, D) across the fretboard.

## CAGED Shape Order

The shapes connect in this order: **C → A → G → E → D → C** (repeating)

Each shape connects to the next, creating a continuous map of chord tones across the neck.

## Major Chord Shapes

### C Form
```
e|---0---
B|---1---  ← Root (1)
G|---0---
D|---2---
A|---3---  ← Root (1)
E|---x---
```
Root strings: 5, 2

### A Form
```
e|---0---
B|---2---
G|---2---
D|---2---
A|---0---  ← Root (1)
E|---x---
```
Root strings: 5

### G Form
```
e|---3---  ← Root (1)
B|---0---
G|---0---
D|---0---
A|---2---
E|---3---  ← Root (1)
```
Root strings: 6, 1

### E Form
```
e|---0---  ← Root (1)
B|---0---
G|---1---
D|---2---
A|---2---
E|---0---  ← Root (1)
```
Root strings: 6, 4, 1

### D Form
```
e|---2---
B|---3---
G|---2---
D|---0---  ← Root (1)
A|---x---
E|---x---
```
Root strings: 4

## CAGED Positions for Any Root

To find chord positions for any root note:

```javascript
const CAGED_POSITIONS = {
  // Fret offset from open position where root would be on primary root string
  C: { rootString: 5, openRootFret: 3 },   // C is at fret 3 on A string
  A: { rootString: 5, openRootFret: 0 },   // A is open on A string
  G: { rootString: 6, openRootFret: 3 },   // G is at fret 3 on E string
  E: { rootString: 6, openRootFret: 0 },   // E is open on E string
  D: { rootString: 4, openRootFret: 0 }    // D is open on D string
}

// Calculate barre position for any root
const getCAGEDPosition = (rootNote, form) => {
  const NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
  const config = CAGED_POSITIONS[form]
  
  // Get target root position on the root string
  const stringTuning = config.rootString === 6 ? 'E' : 
                       config.rootString === 5 ? 'A' : 'D'
  const stringStart = NOTES.indexOf(stringTuning)
  const targetRoot = NOTES.indexOf(rootNote)
  const fretPosition = (targetRoot - stringStart + 12) % 12
  
  return fretPosition - config.openRootFret
}
```

## CAGED Sequence Example: C Major

```
Position 1: C Form (open)     - Frets 0-3
Position 2: A Form            - Frets 3-5 (barre at 3)
Position 3: G Form            - Frets 5-8
Position 4: E Form            - Frets 8-10 (barre at 8)
Position 5: D Form            - Frets 10-13
Position 6: C Form (octave)   - Frets 12-15
```

## Minor CAGED Forms

For minor chords, lower the 3rd by one fret in each shape:

### Cm Form (from C)
```
e|---x---
B|---1---
G|---0---  ← b3 (lowered)
D|---1---  ← b3 (lowered)
A|---3---
E|---x---
```

### Am Form
```
e|---0---
B|---1---  ← b3 (lowered)
G|---2---
D|---2---
A|---0---
E|---x---
```

### Gm Form (partial - difficult full form)
```
e|---3---
B|---3---  ← b3 (lowered)
G|---0---
D|---0---
A|---1---  ← b3 (lowered)
E|---3---
```

### Em Form
```
e|---0---
B|---0---
G|---0---  ← b3 (lowered)
D|---2---
A|---2---
E|---0---
```

### Dm Form
```
e|---1---  ← b3 (lowered)
B|---3---
G|---2---
D|---0---
A|---x---
E|---x---
```

## CAGED Arpeggios

Each CAGED form defines an arpeggio pattern (R-3-5):

```javascript
const ARPEGGIO_PATTERNS = {
  C: {
    notes: [
      { string: 5, fret: 3, degree: 'R' },
      { string: 4, fret: 2, degree: '5' },
      { string: 3, fret: 0, degree: '3' },
      { string: 2, fret: 1, degree: 'R' },
      { string: 1, fret: 0, degree: '5' }
    ]
  },
  // ... similar for A, G, E, D
}
```

## Implementation: CAGED Chord Display

```jsx
const CAGEDForm = ({ rootNote, form, tonality = 'major' }) => {
  const position = getCAGEDPosition(rootNote, form)
  const isBarre = position > 0
  
  const SHAPES = {
    major: {
      C: [[null], [1], [0], [2], [3], [null]],
      A: [[0], [2], [2], [2], [0], [null]],
      G: [[3], [0], [0], [0], [2], [3]],
      E: [[0], [0], [1], [2], [2], [0]],
      D: [[2], [3], [2], [0], [null], [null]]
    }
  }
  
  const shape = SHAPES[tonality][form]
  
  return (
    <div className="caged-form">
      <h3>{rootNote} {tonality} - {form} Form</h3>
      <ChordDiagram 
        shape={shape}
        barrePosition={position}
        rootPositions={getRootPositions(form)}
      />
    </div>
  )
}
```

## CAGED Connection Points

Where each form connects to the next:

| From | To | Connection |
|------|-----|------------|
| C | A | The high 2 strings of C overlap with low strings of A |
| A | G | The bass note of A connects to treble of G |
| G | E | G's bass connects to E's treble |
| E | D | E's D string position connects to D form |
| D | C | D's treble connects to next C form |
