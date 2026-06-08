/**
 * Reusable Performance Testing Helpers for Playwright MCP
 *
 * This file provides ready-to-use helpers for measuring React
 * application performance using Playwright MCP server.
 *
 * Usage: Copy relevant functions and adapt to your testing needs.
 */

import type { PlaywrightMCP } from '@modelcontextprotocol/server-playwright'

// ============================================================================
// CORE WEB VITALS
// ============================================================================

/**
 * Capture all Core Web Vitals metrics
 *
 * @returns Object with FCP, LCP, CLS, TTI, TBT
 */
export async function getCoreWebVitals(playwright: PlaywrightMCP) {
  const metrics = await playwright.browser_evaluate({
    script: `
      JSON.stringify({
        // First Contentful Paint
        fcp: (() => {
          const entry = performance.getEntriesByName('first-contentful-paint')[0]
          return entry ? entry.startTime : null
        })(),

        // Largest Contentful Paint
        lcp: (() => {
          const entries = performance.getEntriesByType('largest-contentful-paint')
          return entries.length > 0 ? entries[entries.length - 1].startTime : null
        })(),

        // Cumulative Layout Shift
        cls: (() => {
          const entries = performance.getEntriesByType('layout-shift')
          return entries
            .filter(entry => !entry.hadRecentInput)
            .reduce((sum, entry) => sum + entry.value, 0)
        })(),

        // Time to Interactive (approximation)
        tti: (() => {
          const nav = performance.timing
          return nav.domInteractive - nav.navigationStart
        })(),

        // Total Blocking Time
        tbt: (() => {
          const longTasks = performance.getEntriesByType('longtask')
          return longTasks.reduce((sum, task) => {
            const blockingTime = Math.max(0, task.duration - 50)
            return sum + blockingTime
          }, 0)
        })(),

        // Total page size
        transferSize: (() => {
          const resources = performance.getEntriesByType('resource')
          return resources.reduce((sum, r) => sum + (r.transferSize || 0), 0)
        })()
      })
    `
  })

  return JSON.parse(metrics)
}

/**
 * Evaluate metrics against targets
 *
 * @param metrics Output from getCoreWebVitals()
 * @returns Object with pass/fail status for each metric
 */
export function evaluateMetrics(metrics: any) {
  return {
    fcp: {
      value: metrics.fcp,
      target: 1800,
      pass: metrics.fcp < 1800,
      rating: metrics.fcp < 1800 ? 'good' : metrics.fcp < 3000 ? 'needs-improvement' : 'poor'
    },
    lcp: {
      value: metrics.lcp,
      target: 2500,
      pass: metrics.lcp < 2500,
      rating: metrics.lcp < 2500 ? 'good' : metrics.lcp < 4000 ? 'needs-improvement' : 'poor'
    },
    cls: {
      value: metrics.cls,
      target: 0.1,
      pass: metrics.cls < 0.1,
      rating: metrics.cls < 0.1 ? 'good' : metrics.cls < 0.25 ? 'needs-improvement' : 'poor'
    },
    tti: {
      value: metrics.tti,
      target: 3800,
      pass: metrics.tti < 3800,
      rating: metrics.tti < 3800 ? 'good' : metrics.tti < 7300 ? 'needs-improvement' : 'poor'
    }
  }
}

// ============================================================================
// MEMORY LEAK DETECTION
// ============================================================================

/**
 * Measure heap growth to detect memory leaks
 *
 * @param playwright Playwright MCP instance
 * @param actions Function containing user interactions to test
 * @returns Heap growth percentage
 */
export async function detectMemoryLeak(
  playwright: PlaywrightMCP,
  actions: (p: PlaywrightMCP) => Promise<void>
) {
  // Force garbage collection if available
  await playwright.browser_evaluate({
    script: 'if (window.gc) window.gc()'
  })

  // Get initial heap size
  const initialHeap = await playwright.browser_evaluate({
    script: 'performance.memory.usedJSHeapSize'
  })

  // Perform actions (navigate, interact, return to start)
  await actions(playwright)

  // Force GC again
  await playwright.browser_evaluate({
    script: 'if (window.gc) window.gc()'
  })

  // Wait for GC to complete
  await new Promise(resolve => setTimeout(resolve, 1000))

  // Get final heap size
  const finalHeap = await playwright.browser_evaluate({
    script: 'performance.memory.usedJSHeapSize'
  })

  const heapGrowth = ((finalHeap - initialHeap) / initialHeap) * 100

  return {
    initialHeap,
    finalHeap,
    growthPercentage: heapGrowth,
    leakDetected: heapGrowth > 10 // >10% growth indicates potential leak
  }
}

/**
 * Check for common leak sources in React
 */
export async function checkLeakSources(playwright: PlaywrightMCP) {
  return await playwright.browser_evaluate({
    script: `
      JSON.stringify({
        // Event listeners
        eventListeners: (() => {
          const elements = document.querySelectorAll('*')
          let count = 0
          elements.forEach(el => {
            const listeners = getEventListeners(el)
            count += Object.values(listeners).flat().length
          })
          return count
        })(),

        // Timers (rough count)
        activeTimers: (() => {
          // This is approximate - browser doesn't expose timer count
          return 'Check DevTools Performance tab for timer activity'
        })(),

        // Detached DOM nodes
        detachedNodes: (() => {
          // This requires DevTools Memory profiler
          return 'Run heap snapshot and filter for "Detached"'
        })()
      })
    `
  })
}

// ============================================================================
// RENDERING PERFORMANCE
// ============================================================================

/**
 * Measure frame rate during scrolling
 * Tests if app maintains 60fps during interaction
 */
export async function measureScrollPerformance(playwright: PlaywrightMCP, scrollTarget: string) {
  await playwright.browser_evaluate({
    script: `
      window.fpsData = []
      window.lastFrameTime = performance.now()

      function measureFrame() {
        const now = performance.now()
        const fps = 1000 / (now - window.lastFrameTime)
        window.fpsData.push(fps)
        window.lastFrameTime = now

        if (window.fpsData.length < 120) { // 2 seconds at 60fps
          requestAnimationFrame(measureFrame)
        }
      }

      requestAnimationFrame(measureFrame)
    `
  })

  // Perform scroll
  const element = await playwright.browser_click({
    selector: scrollTarget
  })

  // Scroll down
  await playwright.browser_evaluate({
    script: `
      const el = document.querySelector('${scrollTarget}')
      el.scrollTop = el.scrollHeight
    `
  })

  // Wait for FPS measurement to complete
  await new Promise(resolve => setTimeout(resolve, 2500))

  // Get FPS data
  const fpsMetrics = await playwright.browser_evaluate({
    script: `
      JSON.stringify({
        avgFps: window.fpsData.reduce((a, b) => a + b, 0) / window.fpsData.length,
        minFps: Math.min(...window.fpsData),
        maxFps: Math.max(...window.fpsData),
        frameDrops: window.fpsData.filter(fps => fps < 30).length
      })
    `
  })

  return JSON.parse(fpsMetrics)
}

/**
 * Count React re-renders using React DevTools
 * Note: Requires React DevTools extension or development build
 */
export async function countReRenders(playwright: PlaywrightMCP, componentName: string) {
  // This requires React DevTools hook to be available
  const renderCount = await playwright.browser_evaluate({
    script: `
      // Access React DevTools global hook
      const hook = window.__REACT_DEVTOOLS_GLOBAL_HOOK__
      if (!hook) {
        JSON.stringify({ error: 'React DevTools not available' })
      } else {
        // This is a simplified example - actual implementation would
        // need to integrate with React DevTools profiling API
        JSON.stringify({
          message: 'Enable React DevTools Profiler and record interaction',
          instructions: [
            '1. Open React DevTools',
            '2. Go to Profiler tab',
            '3. Click Record',
            '4. Perform interaction',
            '5. Stop recording',
            '6. Check Flamegraph for render counts'
          ]
        })
      }
    `
  })

  return JSON.parse(renderCount)
}

// ============================================================================
// NETWORK PERFORMANCE
// ============================================================================

/**
 * Analyze network requests for performance issues
 */
export async function analyzeNetworkRequests(playwright: PlaywrightMCP) {
  const requests = await playwright.browser_network_requests()

  // Parse and analyze requests
  const analysis = {
    totalRequests: requests.length,
    totalSize: 0,
    blocking: [],
    sequential: [],
    largePayloads: [],
    slowRequests: [],
    cacheHits: 0,
    cacheMisses: 0
  }

  requests.forEach((req: any) => {
    analysis.totalSize += req.size || 0

    // Check for blocking resources
    if (req.resourceType === 'script' || req.resourceType === 'stylesheet') {
      if (!req.async && !req.defer) {
        analysis.blocking.push(req.url)
      }
    }

    // Check for large payloads (>500KB)
    if (req.size > 500000) {
      analysis.largePayloads.push({
        url: req.url,
        size: req.size,
        type: req.resourceType
      })
    }

    // Check for slow requests (>1s)
    if (req.duration > 1000) {
      analysis.slowRequests.push({
        url: req.url,
        duration: req.duration
      })
    }

    // Check cache status
    if (req.fromCache) {
      analysis.cacheHits++
    } else {
      analysis.cacheMisses++
    }
  })

  return analysis
}

/**
 * Detect sequential loading patterns (waterfall issues)
 */
export async function detectWaterfalls(playwright: PlaywrightMCP) {
  const timing = await playwright.browser_evaluate({
    script: `
      JSON.stringify(
        performance.getEntriesByType('resource').map(entry => ({
          name: entry.name,
          startTime: entry.startTime,
          duration: entry.duration,
          initiatorType: entry.initiatorType
        }))
      )
    `
  })

  const resources = JSON.parse(timing)

  // Sort by start time
  resources.sort((a: any, b: any) => a.startTime - b.startTime)

  // Detect sequential chains (resource B starts after A finishes)
  const chains: any[] = []
  let currentChain: any[] = []

  for (let i = 0; i < resources.length - 1; i++) {
    const current = resources[i]
    const next = resources[i + 1]

    // If next resource starts after current finishes (with small buffer)
    if (next.startTime > current.startTime + current.duration - 50) {
      currentChain.push(current)
    } else {
      if (currentChain.length > 2) { // Chain of 3+ resources
        chains.push([...currentChain])
      }
      currentChain = []
    }
  }

  return {
    chains,
    longestChain: chains.reduce((max, chain) =>
      chain.length > max.length ? chain : max, [])
  }
}

// ============================================================================
// IMAGE OPTIMIZATION
// ============================================================================

/**
 * Audit images for optimization opportunities
 */
export async function auditImages(playwright: PlaywrightMCP) {
  return await playwright.browser_evaluate({
    script: `
      JSON.stringify(
        Array.from(document.images).map(img => ({
          src: img.src,
          naturalWidth: img.naturalWidth,
          naturalHeight: img.naturalHeight,
          displayWidth: img.width,
          displayHeight: img.height,
          format: img.src.split('.').pop()?.split('?')[0],
          lazy: img.loading === 'lazy',
          hasExplicitDimensions: img.hasAttribute('width') && img.hasAttribute('height'),
          oversized: img.naturalWidth > img.width * 2 || img.naturalHeight > img.height * 2,
          modernFormat: ['webp', 'avif'].includes(img.src.split('.').pop()?.split('?')[0]?.toLowerCase() || '')
        }))
      )
    `
  })
}

// ============================================================================
// BUNDLE SIZE ANALYSIS
// ============================================================================

/**
 * Analyze JavaScript bundle sizes
 * Note: This should be run as a Bash command, not in browser
 */
export function analyzeBundleSize() {
  return {
    command: 'npx webpack-bundle-analyzer build/static/js/*.js --mode static --open false --report report.html',
    extractSizes: 'ls -lh build/static/js/*.js | awk \'{print $5, $9}\'',
    notes: [
      'Look for:',
      '- Libraries >50KB (consider alternatives)',
      '- Duplicate dependencies',
      '- Unused exports (tree shaking issues)',
      '- Opportunities for code splitting'
    ]
  }
}

// ============================================================================
// LIGHTHOUSE INTEGRATION
// ============================================================================

/**
 * Run Lighthouse audit programmatically
 * Note: Requires lighthouse package installed
 */
export async function runLighthouse(url: string) {
  return {
    command: `npx lighthouse ${url} --output=json --output-path=./lighthouse-report.json --chrome-flags="--headless"`,
    parseResults: `cat lighthouse-report.json | jq '{performance: .categories.performance.score, accessibility: .categories.accessibility.score, bestPractices: .categories["best-practices"].score, seo: .categories.seo.score}'`
  }
}

// ============================================================================
// COMPREHENSIVE PERFORMANCE TEST
// ============================================================================

/**
 * Run full performance audit
 * Combines all checks into single report
 */
export async function runFullAudit(playwright: PlaywrightMCP, url: string) {
  console.log('Starting comprehensive performance audit...')

  // Navigate to page
  await playwright.browser_navigate({ url })
  await playwright.browser_wait_for({
    selector: 'body',
    state: 'attached',
    timeout: 10000
  })

  // Wait for page to settle
  await new Promise(resolve => setTimeout(resolve, 2000))

  // Collect all metrics
  const results = {
    coreWebVitals: await getCoreWebVitals(playwright),
    network: await analyzeNetworkRequests(playwright),
    waterfalls: await detectWaterfalls(playwright),
    images: JSON.parse(await auditImages(playwright)),
    timestamp: new Date().toISOString()
  }

  // Evaluate against targets
  results.evaluation = evaluateMetrics(results.coreWebVitals)

  return results
}

// ============================================================================
// REPORT GENERATION
// ============================================================================

/**
 * Generate human-readable performance report
 */
export function generateReport(auditResults: any) {
  const { coreWebVitals, evaluation, network, images } = auditResults

  let report = '# Performance Audit Report\n\n'
  report += `**Generated**: ${auditResults.timestamp}\n\n`

  report += '## Core Web Vitals\n\n'
  report += '| Metric | Value | Target | Status |\n'
  report += '|--------|-------|--------|--------|\n'

  Object.entries(evaluation).forEach(([metric, data]: [string, any]) => {
    const status = data.pass ? '✅ PASS' : '❌ FAIL'
    const value = typeof data.value === 'number' ? data.value.toFixed(2) : data.value
    report += `| ${metric.toUpperCase()} | ${value}ms | <${data.target}ms | ${status} |\n`
  })

  report += '\n## Network Analysis\n\n'
  report += `- Total Requests: ${network.totalRequests}\n`
  report += `- Total Size: ${(network.totalSize / 1024 / 1024).toFixed(2)}MB\n`
  report += `- Cache Hit Rate: ${((network.cacheHits / network.totalRequests) * 100).toFixed(1)}%\n`

  if (network.blocking.length > 0) {
    report += '\n### ⚠️ Blocking Resources\n'
    network.blocking.forEach((url: string) => {
      report += `- ${url}\n`
    })
  }

  if (network.largePayloads.length > 0) {
    report += '\n### ⚠️ Large Payloads (>500KB)\n'
    network.largePayloads.forEach((item: any) => {
      report += `- ${item.url} (${(item.size / 1024).toFixed(0)}KB)\n`
    })
  }

  report += '\n## Image Optimization\n\n'
  const oversizedImages = images.filter((img: any) => img.oversized)
  const nonModernFormat = images.filter((img: any) => !img.modernFormat)
  const missingDimensions = images.filter((img: any) => !img.hasExplicitDimensions)

  report += `- Total Images: ${images.length}\n`
  report += `- Oversized: ${oversizedImages.length}\n`
  report += `- Non-modern format: ${nonModernFormat.length}\n`
  report += `- Missing dimensions: ${missingDimensions.length}\n`

  report += '\n## Recommendations\n\n'

  const recommendations: string[] = []

  if (!evaluation.fcp.pass) recommendations.push('- Reduce FCP by optimizing critical rendering path')
  if (!evaluation.lcp.pass) recommendations.push('- Improve LCP by optimizing largest element (image/text block)')
  if (!evaluation.cls.pass) recommendations.push('- Fix CLS by adding explicit dimensions to images/ads')
  if (!evaluation.tti.pass) recommendations.push('- Reduce TTI by minimizing JavaScript execution time')
  if (network.blocking.length > 0) recommendations.push('- Add async/defer to blocking scripts')
  if (network.largePayloads.length > 0) recommendations.push('- Compress or split large payloads')
  if (oversizedImages.length > 0) recommendations.push('- Resize oversized images to display dimensions')
  if (nonModernFormat.length > 0) recommendations.push('- Convert images to WebP/AVIF format')

  recommendations.forEach(rec => report += `${rec}\n`)

  return report
}
