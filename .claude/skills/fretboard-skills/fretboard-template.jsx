// Guitar Fretboard Template - Interactive React Component
// This is a complete, working template for guitar fretboard visualizations

import React, { useState, useMemo } from 'react'

// ==================== MUSIC THEORY CONSTANTS ====================

const NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
const STANDARD_TUNING = ['E', 'A', 'D', 'G', 'B', 'E'] // Low to High (6th to 1st)

const SCALES = {
  major: [0, 2, 4, 5, 7, 9, 11],
  minor: [0, 2, 3, 5, 7, 8, 10],
  majorPentatonic: [0, 2, 4, 7, 9],
  minorPentatonic: [0, 3, 5, 7, 10],
  blues: [0, 3, 5, 6, 7, 10],
  dorian: [0, 2, 3, 5, 7, 9, 10],
  phrygian: [0, 1, 3, 5, 7, 8, 10],
  mixolydian: [0, 2, 4, 5, 7, 9, 10],
  harmonicMinor: [0, 2, 3, 5, 7, 8, 11]
}

const SCALE_NAMES = {
  major: 'Major',
  minor: 'Natural Minor',
  majorPentatonic: 'Major Pentatonic',
  minorPentatonic: 'Minor Pentatonic',
  blues: 'Blues',
  dorian: 'Dorian',
  phrygian: 'Phrygian',
  mixolydian: 'Mixolydian',
  harmonicMinor: 'Harmonic Minor'
}

// ==================== HELPER FUNCTIONS ====================

const getNoteAtFret = (openNote, fret) => {
  const startIndex = NOTES.indexOf(openNote)
  return NOTES[(startIndex + fret) % 12]
}

const getInterval = (rootNote, note) => {
  const rootIndex = NOTES.indexOf(rootNote)
  const noteIndex = NOTES.indexOf(note)
  return (noteIndex - rootIndex + 12) % 12
}

const isNoteInScale = (note, rootNote, scaleFormula) => {
  const interval = getInterval(rootNote, note)
  return scaleFormula.includes(interval)
}

const getScaleDegree = (note, rootNote, scaleFormula) => {
  const interval = getInterval(rootNote, note)
  const degree = scaleFormula.indexOf(interval)
  return degree >= 0 ? degree + 1 : null
}

// ==================== COLOR SCHEMES ====================

const DEGREE_COLORS = {
  1: '#ef4444', // Root - Red
  2: '#f97316', // 2nd - Orange
  3: '#22c55e', // 3rd - Green
  4: '#14b8a6', // 4th - Teal
  5: '#3b82f6', // 5th - Blue
  6: '#8b5cf6', // 6th - Violet
  7: '#ec4899', // 7th - Pink
  blue: '#06b6d4' // Blue note - Cyan
}

// ==================== COMPONENTS ====================

const NoteMarker = ({ note, isRoot, inScale, degree, isBlueNote, showNote = true }) => {
  if (!inScale) return <div className="w-6 h-6" />
  
  let bgColor = DEGREE_COLORS[degree] || '#6b7280'
  if (isBlueNote) bgColor = DEGREE_COLORS.blue
  
  return (
    <div 
      className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold
        ${isRoot ? 'ring-2 ring-white ring-offset-1 ring-offset-gray-800' : ''}`}
      style={{ backgroundColor: bgColor, color: 'white' }}
    >
      {showNote ? note : degree}
    </div>
  )
}

const FretMarkers = ({ fret }) => {
  const singleMarkers = [3, 5, 7, 9, 15, 17, 19, 21]
  const doubleMarkers = [12, 24]
  
  if (doubleMarkers.includes(fret)) {
    return (
      <div className="absolute inset-0 flex flex-col justify-around items-center py-2 pointer-events-none">
        <div className="w-3 h-3 rounded-full bg-gray-400 opacity-40" />
        <div className="w-3 h-3 rounded-full bg-gray-400 opacity-40" />
      </div>
    )
  }
  
  if (singleMarkers.includes(fret)) {
    return (
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="w-3 h-3 rounded-full bg-gray-400 opacity-40" />
      </div>
    )
  }
  
  return null
}

const Fretboard = ({ 
  rootNote, 
  scale, 
  tuning = STANDARD_TUNING, 
  fretCount = 15,
  showNotes = true,
  showOpenStrings = true 
}) => {
  const scaleFormula = SCALES[scale]
  const isBlues = scale === 'blues'
  const blueNoteInterval = 6 // The tritone/b5
  
  // Reverse tuning for display (high E on top)
  const displayTuning = [...tuning].reverse()
  
  return (
    <div className="bg-gradient-to-b from-amber-900 to-amber-950 rounded-lg p-4 overflow-x-auto">
      <div className="flex">
        {/* Nut / Open strings */}
        {showOpenStrings && (
          <div className="flex flex-col gap-1 pr-2 border-r-4 border-gray-300">
            {displayTuning.map((openNote, idx) => {
              const inScale = isNoteInScale(openNote, rootNote, scaleFormula)
              const degree = getScaleDegree(openNote, rootNote, scaleFormula)
              const isBlueNote = isBlues && getInterval(rootNote, openNote) === blueNoteInterval
              return (
                <NoteMarker
                  key={idx}
                  note={openNote}
                  isRoot={openNote === rootNote}
                  inScale={inScale}
                  degree={degree}
                  isBlueNote={isBlueNote}
                  showNote={showNotes}
                />
              )
            })}
          </div>
        )}
        
        {/* Frets */}
        {Array.from({ length: fretCount }, (_, fretIdx) => (
          <div key={fretIdx} className="relative flex flex-col gap-1 px-1 border-r-2 border-gray-500">
            <FretMarkers fret={fretIdx + 1} />
            {displayTuning.map((openNote, stringIdx) => {
              const note = getNoteAtFret(openNote, fretIdx + 1)
              const inScale = isNoteInScale(note, rootNote, scaleFormula)
              const degree = getScaleDegree(note, rootNote, scaleFormula)
              const isBlueNote = isBlues && getInterval(rootNote, note) === blueNoteInterval
              return (
                <div key={stringIdx} className="relative">
                  {/* String line */}
                  <div 
                    className="absolute left-0 right-0 h-0.5 top-1/2 -translate-y-1/2 z-0"
                    style={{ 
                      backgroundColor: stringIdx < 3 ? '#d4d4d4' : '#a3a3a3',
                      height: stringIdx < 2 ? '1px' : stringIdx < 4 ? '2px' : '3px'
                    }}
                  />
                  <div className="relative z-10">
                    <NoteMarker
                      note={note}
                      isRoot={note === rootNote}
                      inScale={inScale}
                      degree={degree}
                      isBlueNote={isBlueNote}
                      showNote={showNotes}
                    />
                  </div>
                </div>
              )
            })}
            {/* Fret number */}
            <div className="text-xs text-gray-400 text-center mt-1">{fretIdx + 1}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ==================== MAIN APP ====================

export default function GuitarFretboardApp() {
  const [rootNote, setRootNote] = useState('A')
  const [scale, setScale] = useState('minorPentatonic')
  const [showNotes, setShowNotes] = useState(true)
  
  const scaleNotes = useMemo(() => {
    const formula = SCALES[scale]
    const rootIndex = NOTES.indexOf(rootNote)
    return formula.map(interval => NOTES[(rootIndex + interval) % 12])
  }, [rootNote, scale])
  
  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-3xl font-bold mb-2">
            {rootNote} {SCALE_NAMES[scale]}
          </h1>
          <p className="text-gray-400">
            Notes: {scaleNotes.join(' - ')}
          </p>
        </div>
        
        {/* Controls */}
        <div className="flex flex-wrap gap-4 justify-center bg-gray-800 rounded-lg p-4">
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium">Root:</label>
            <select 
              value={rootNote}
              onChange={(e) => setRootNote(e.target.value)}
              className="bg-gray-700 rounded px-3 py-1.5 text-sm"
            >
              {NOTES.map(note => (
                <option key={note} value={note}>{note}</option>
              ))}
            </select>
          </div>
          
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium">Scale:</label>
            <select 
              value={scale}
              onChange={(e) => setScale(e.target.value)}
              className="bg-gray-700 rounded px-3 py-1.5 text-sm"
            >
              {Object.entries(SCALE_NAMES).map(([key, name]) => (
                <option key={key} value={key}>{name}</option>
              ))}
            </select>
          </div>
          
          <button
            onClick={() => setShowNotes(!showNotes)}
            className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium"
          >
            Show: {showNotes ? 'Notes' : 'Degrees'}
          </button>
        </div>
        
        {/* Fretboard */}
        <Fretboard 
          rootNote={rootNote}
          scale={scale}
          showNotes={showNotes}
        />
        
        {/* Legend */}
        <div className="flex flex-wrap gap-3 justify-center text-sm">
          {Object.entries(DEGREE_COLORS).map(([degree, color]) => (
            <div key={degree} className="flex items-center gap-1.5">
              <div 
                className="w-4 h-4 rounded-full"
                style={{ backgroundColor: color }}
              />
              <span className="text-gray-300">
                {degree === 'blue' ? 'Blue Note' : `${degree}${['st','nd','rd'][degree-1] || 'th'}`}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
