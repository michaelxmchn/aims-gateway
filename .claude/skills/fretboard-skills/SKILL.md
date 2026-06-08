---
name: guitar-fretboard
description: Create interactive guitar fretboard visualizations for scales, chords, CAGED system, triads, intervals, and note positions. Use this skill when users ask to build guitar learning tools, visualize scales/modes/pentatonics on the fretboard, show chord shapes, display CAGED patterns, create interval diagrams, or build any guitar theory visualization as React artifacts. Supports standard tuning, custom tunings, and comprehensive music theory for guitar.
---

# Guitar Fretboard Visualization Skill

Create interactive React artifacts for guitar fretboard visualizations with proper music theory.

## Core Music Theory Reference

### Notes and Intervals

```javascript
const NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const STANDARD_TUNING = ['E', 'A', 'D', 'G', 'B', 'E'] // low to high (6th to 1st string)

// Semitone intervals from root
const INTERVALS = {
  root: 0, minor2nd: 1, major2nd: 2, minor3rd: 3, major3rd: 4,
  perfect4th: 5, tritone: 6, perfect5th: 7, minor6th: 8,
  major6th: 9, minor7th: 10, major7th: 11, octave: 12
}
```

### Scale Formulas (semitones from root)

```javascript
const SCALES = {
  major: [0, 2, 4, 5, 7, 9, 11],           // W-W-H-W-W-W-H
  minor: [0, 2, 3, 5, 7, 8, 10],           // W-H-W-W-H-W-W (natural minor)
  majorPentatonic: [0, 2, 4, 7, 9],        // 1-2-3-5-6
  minorPentatonic: [0, 3, 5, 7, 10],       // 1-b3-4-5-b7
  blues: [0, 3, 5, 6, 7, 10],              // minor pentatonic + b5
  dorian: [0, 2, 3, 5, 7, 9, 10],          // mode 2
  phrygian: [0, 1, 3, 5, 7, 8, 10],        // mode 3
  lydian: [0, 2, 4, 6, 7, 9, 11],          // mode 4
  mixolydian: [0, 2, 4, 5, 7, 9, 10],      // mode 5
  locrian: [0, 1, 3, 5, 6, 8, 10],         // mode 7
  harmonicMinor: [0, 2, 3, 5, 7, 8, 11],
  melodicMinor: [0, 2, 3, 5, 7, 9, 11]
}
```

### CAGED System Forms

The CAGED system uses 5 moveable chord shapes (C, A, G, E, D) that connect across the fretboard:

```javascript
const CAGED_ROOT_POSITIONS = {
  // Fret offsets where root appears for each form (relative to form position)
  C: { string6: null, string5: 3, string4: null, string3: null, string2: 1, string1: null },
  A: { string6: null, string5: 0, string4: 2, string3: 2, string2: null, string1: null },
  G: { string6: 3, string5: null, string4: 0, string3: 0, string2: null, string1: 3 },
  E: { string6: 0, string5: null, string4: 2, string3: null, string2: 0, string1: 0 },
  D: { string6: null, string5: null, string4: 0, string3: 2, string2: 3, string1: null }
}
```

## Fretboard Component Architecture

### Core Helper Functions

```javascript
// Get note at any fret position
const getNoteAtFret = (openNote, fret) => {
  const startIndex = NOTES.indexOf(openNote)
  return NOTES[(startIndex + fret) % 12]
}

// Check if note is in scale
const isNoteInScale = (note, rootNote, scaleFormula) => {
  const rootIndex = NOTES.indexOf(rootNote)
  const noteIndex = NOTES.indexOf(note)
  const interval = (noteIndex - rootIndex + 12) % 12
  return scaleFormula.includes(interval)
}

// Get interval name from root
const getInterval = (rootNote, note) => {
  const rootIndex = NOTES.indexOf(rootNote)
  const noteIndex = NOTES.indexOf(note)
  return (noteIndex - rootIndex + 12) % 12
}

// Get degree in scale (1-7 for diatonic, 1-5 for pentatonic)
const getScaleDegree = (note, rootNote, scaleFormula) => {
  const interval = getInterval(rootNote, note)
  return scaleFormula.indexOf(interval) + 1
}
```

### Fretboard Layout Constants

```javascript
const FRETS = 15          // Standard display: 15 frets
const STRINGS = 6         // 6-string guitar
const FRET_MARKERS = [3, 5, 7, 9, 12, 15, 17, 19, 21, 24]  // Single dot positions
const DOUBLE_MARKERS = [12, 24]  // Double dot positions
```

## Implementation Patterns

### Pattern 1: Complete Fretboard with Scale Highlighting

Display all frets with selected scale notes highlighted:

```jsx
const Fretboard = ({ rootNote, scale, tuning = STANDARD_TUNING }) => {
  const scaleFormula = SCALES[scale]
  
  return (
    <div className="fretboard">
      {/* Nut (open strings) */}
      <div className="nut">
        {tuning.map((note, string) => (
          <NoteMarker 
            key={string}
            note={note}
            isRoot={note === rootNote}
            inScale={isNoteInScale(note, rootNote, scaleFormula)}
          />
        ))}
      </div>
      
      {/* Frets */}
      {Array.from({ length: FRETS }, (_, fret) => (
        <div key={fret} className="fret">
          {tuning.map((openNote, string) => {
            const note = getNoteAtFret(openNote, fret + 1)
            return (
              <NoteMarker
                key={string}
                note={note}
                isRoot={note === rootNote}
                inScale={isNoteInScale(note, rootNote, scaleFormula)}
                showDegree={true}
                degree={getScaleDegree(note, rootNote, scaleFormula)}
              />
            )
          })}
        </div>
      ))}
    </div>
  )
}
```

### Pattern 2: Pentatonic Box Patterns

Display the 5 pentatonic patterns:

```javascript
// Pattern positions for minor pentatonic (frets relative to pattern start)
const PENTATONIC_PATTERNS = {
  pattern1: { // Root position (minor) / Pattern 5 (relative major)
    startFret: 0,  // relative to root
    positions: [
      [0, 3], [0, 3], [0, 2], [0, 2], [0, 3], [0, 3]  // [fret offsets per string]
    ]
  },
  pattern2: { startFret: 3 },
  pattern3: { startFret: 5 },
  pattern4: { startFret: 7 },
  pattern5: { startFret: 10 }
}
```

### Pattern 3: CAGED Chord Forms

```jsx
const CAGEDChord = ({ form, rootNote, tonality = 'major' }) => {
  // Calculate fret position based on root note and form
  const getFormPosition = () => {
    // Each CAGED form has specific root string and offset
    const formRoots = { C: 5, A: 5, G: 6, E: 6, D: 4 }
    // ... calculate position
  }
  
  return (
    <div className="caged-form">
      {/* Render chord shape at calculated position */}
    </div>
  )
}
```

### Pattern 4: Triad Visualizations

```javascript
const TRIADS = {
  major: [0, 4, 7],      // R-3-5
  minor: [0, 3, 7],      // R-b3-5
  diminished: [0, 3, 6], // R-b3-b5
  augmented: [0, 4, 8]   // R-3-#5
}

// String groupings for triads
const TRIAD_SETS = [
  [1, 2, 3],  // strings 1-2-3
  [2, 3, 4],  // strings 2-3-4
  [3, 4, 5],  // strings 3-4-5
  [4, 5, 6]   // strings 4-5-6
]
```

## Styling Guidelines

### Color Schemes for Notes

```css
/* Recommended semantic colors */
.root { background: #ef4444; }      /* Red - root note */
.third { background: #22c55e; }     /* Green - 3rd */
.fifth { background: #3b82f6; }     /* Blue - 5th */
.seventh { background: #a855f7; }   /* Purple - 7th */
.blue-note { background: #06b6d4; } /* Cyan - blues note */
.scale-note { background: #6b7280; } /* Gray - other scale notes */
```

### Fretboard CSS Structure

```css
.fretboard {
  display: flex;
  flex-direction: row;
  background: linear-gradient(to bottom, #78350f, #451a03);
  border-radius: 4px;
  padding: 8px;
}

.string {
  height: 2px;
  background: linear-gradient(to bottom, #d4d4d4, #a3a3a3);
}

.fret-wire {
  width: 3px;
  background: #a8a29e;
}

.fret-marker {
  width: 12px;
  height: 12px;
  background: #fafaf9;
  border-radius: 50%;
  opacity: 0.3;
}
```

## Feature Implementations

### Interactive Features

1. **Note Selection**: Click to highlight/select notes
2. **Scale Selector**: Dropdown for root note + scale type
3. **Pattern Navigation**: Buttons to cycle through patterns
4. **Audio Playback**: Optional Tone.js integration for note sounds
5. **Hover Information**: Show note name, interval, scale degree

### Display Modes

1. **All Notes**: Show every note on fretboard
2. **Scale Only**: Show only notes in selected scale
3. **Intervals**: Show interval numbers instead of note names
4. **Degrees**: Show scale degrees (1, 2, 3, etc.)
5. **Patterns**: Highlight specific positional patterns

## Usage Examples

**User Request**: "Show me the A minor pentatonic scale on the fretboard"
→ Render fretboard with A minor pentatonic highlighted, root notes emphasized

**User Request**: "Create a CAGED chord diagram for C major"  
→ Show all 5 CAGED forms for C major across the fretboard

**User Request**: "Visualize the 5 pentatonic box patterns in E minor"
→ Create 5 separate fretboard sections showing each pattern position

**User Request**: "Show me all the triads in G major"
→ Display triads on different string sets with chord quality labels

## See Also

- `references/scales.md` - Complete scale formulas and theory
- `references/caged.md` - Detailed CAGED system patterns
- `references/intervals.md` - Interval theory and fretboard mapping
