# Intervals Reference

Complete interval theory for guitar fretboard visualization.

## Interval Table

| Semitones | Name | Abbreviation | Quality |
|-----------|------|--------------|---------|
| 0 | Unison/Root | R, 1 | Perfect |
| 1 | Minor 2nd | m2, b2 | Minor |
| 2 | Major 2nd | M2, 2 | Major |
| 3 | Minor 3rd | m3, b3 | Minor |
| 4 | Major 3rd | M3, 3 | Major |
| 5 | Perfect 4th | P4, 4 | Perfect |
| 6 | Tritone/Aug 4th/Dim 5th | TT, #4, b5 | Augmented/Diminished |
| 7 | Perfect 5th | P5, 5 | Perfect |
| 8 | Minor 6th | m6, b6 | Minor |
| 9 | Major 6th | M6, 6 | Major |
| 10 | Minor 7th | m7, b7 | Minor |
| 11 | Major 7th | M7, 7 | Major |
| 12 | Octave | Oct, 8 | Perfect |

## Fretboard Interval Shapes

### Same String
Moving along a single string, each fret = 1 semitone.

### Adjacent String Patterns (Standard Tuning)

**Strings 6→5, 5→4, 4→3, 2→1** (4th apart = 5 semitones):
- Same fret = Perfect 4th up
- 2 frets higher = Perfect 5th up
- 2 frets lower = Minor 3rd up

**Strings 3→2** (Major 3rd apart = 4 semitones):
- Same fret = Major 3rd up
- 1 fret higher = Perfect 4th up
- 3 frets lower = Root/Unison

### Octave Shapes

```
Pattern 1: 2 strings + 2 frets (strings 6-4, 5-3, 4-2)
  ●───────
  ───●───
  
Pattern 2: 2 strings + 3 frets (strings 3-1 due to B string offset)
  ●───────
  ────●───
  
Pattern 3: 3 strings, same fret (strings 6-1, plus 2 for B offset)
```

## Interval Visualization Code

```javascript
const INTERVALS = {
  0: { name: 'Root', short: 'R', quality: 'perfect' },
  1: { name: 'Minor 2nd', short: 'b2', quality: 'minor' },
  2: { name: 'Major 2nd', short: '2', quality: 'major' },
  3: { name: 'Minor 3rd', short: 'b3', quality: 'minor' },
  4: { name: 'Major 3rd', short: '3', quality: 'major' },
  5: { name: 'Perfect 4th', short: '4', quality: 'perfect' },
  6: { name: 'Tritone', short: 'b5', quality: 'diminished' },
  7: { name: 'Perfect 5th', short: '5', quality: 'perfect' },
  8: { name: 'Minor 6th', short: 'b6', quality: 'minor' },
  9: { name: 'Major 6th', short: '6', quality: 'major' },
  10: { name: 'Minor 7th', short: 'b7', quality: 'minor' },
  11: { name: 'Major 7th', short: '7', quality: 'major' }
}

// Get interval between two notes
const getInterval = (rootNote, targetNote) => {
  const NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
  const rootIndex = NOTES.indexOf(rootNote)
  const targetIndex = NOTES.indexOf(targetNote)
  return (targetIndex - rootIndex + 12) % 12
}

// Color coding by interval quality
const INTERVAL_COLORS = {
  perfect: '#3b82f6',    // Blue
  major: '#22c55e',      // Green
  minor: '#eab308',      // Yellow
  diminished: '#ef4444', // Red
  augmented: '#a855f7'   // Purple
}
```

## Chord Quality by Intervals

| Chord Type | Formula | Intervals |
|------------|---------|-----------|
| Major | R-3-5 | 0-4-7 |
| Minor | R-b3-5 | 0-3-7 |
| Diminished | R-b3-b5 | 0-3-6 |
| Augmented | R-3-#5 | 0-4-8 |
| Major 7th | R-3-5-7 | 0-4-7-11 |
| Dominant 7th | R-3-5-b7 | 0-4-7-10 |
| Minor 7th | R-b3-5-b7 | 0-3-7-10 |
| Minor 7b5 | R-b3-b5-b7 | 0-3-6-10 |
| Diminished 7th | R-b3-b5-bb7 | 0-3-6-9 |

## Triads Reference

### Triad Inversions

| Inversion | Order | Intervals from bass |
|-----------|-------|---------------------|
| Root | R-3-5 | 0-4-7 |
| 1st | 3-5-R | 0-3-8 |
| 2nd | 5-R-3 | 0-5-9 |

### Triad String Sets

```javascript
const TRIAD_SETS = [
  { strings: [1, 2, 3], name: 'Top 3' },
  { strings: [2, 3, 4], name: 'Middle-High' },
  { strings: [3, 4, 5], name: 'Middle-Low' },
  { strings: [4, 5, 6], name: 'Bottom 3' }
]
```

### Diatonic Triads in Major Key

| Degree | Numeral | Quality | Example in C |
|--------|---------|---------|--------------|
| 1 | I | Major | C |
| 2 | ii | Minor | Dm |
| 3 | iii | Minor | Em |
| 4 | IV | Major | F |
| 5 | V | Major | G |
| 6 | vi | Minor | Am |
| 7 | vii° | Diminished | B° |

## Fretboard Interval Mapping

```jsx
const IntervalFretboard = ({ rootNote }) => {
  const NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
  const TUNING = ['E', 'A', 'D', 'G', 'B', 'E']
  
  const getNoteAtFret = (openNote, fret) => {
    const startIndex = NOTES.indexOf(openNote)
    return NOTES[(startIndex + fret) % 12]
  }
  
  return (
    <div className="interval-fretboard">
      {TUNING.map((openNote, stringIndex) => (
        <div key={stringIndex} className="string">
          {Array.from({ length: 13 }, (_, fret) => {
            const note = getNoteAtFret(openNote, fret)
            const interval = getInterval(rootNote, note)
            return (
              <div 
                key={fret}
                className="fret-position"
                style={{ backgroundColor: INTERVAL_COLORS[INTERVALS[interval].quality] }}
              >
                {INTERVALS[interval].short}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}
```
