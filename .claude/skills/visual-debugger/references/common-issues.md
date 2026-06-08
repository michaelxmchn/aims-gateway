# Common Visual Issues & Diagnostics

Common web application visual bugs and how to diagnose them with Playwright.

## Layout Issues

### Elements Overlapping

**Symptoms:**
- Elements appear on top of each other
- Content is hidden behind other elements
- Click targets are obscured

**Diagnosis:**
```typescript
// Take screenshot
mcp__playwright__browser_take_screenshot({ full_page: true })

// Check z-index and positioning
mcp__playwright__browser_evaluate({
  script: `
    const elements = document.querySelectorAll('.overlapping');
    return Array.from(elements).map(el => {
      const styles = window.getComputedStyle(el);
      return {
        element: el.className,
        zIndex: styles.zIndex,
        position: styles.position,
        top: styles.top,
        left: styles.left
      };
    });
  `
})
```

**Common causes:**
- Incorrect z-index values
- Absolute positioning conflicts
- Fixed headers/footers without proper spacing

### Responsive Breakpoint Issues

**Symptoms:**
- Layout breaks at certain screen sizes
- Elements overflow container
- Text becomes unreadable

**Diagnosis:**
```typescript
// Test at different viewports
const viewports = [
  { width: 375, height: 667, name: "Mobile" },
  { width: 768, height: 1024, name: "Tablet" },
  { width: 1920, height: 1080, name: "Desktop" }
];

for (const viewport of viewports) {
  mcp__playwright__browser_resize(viewport);
  mcp__playwright__browser_take_screenshot({
    full_page: true,
    path: `${viewport.name}.png`
  });

  // Check for overflow
  const overflow = mcp__playwright__browser_evaluate({
    script: `
      const elements = document.querySelectorAll('*');
      const overflowing = [];
      elements.forEach(el => {
        if (el.scrollWidth > el.clientWidth) {
          overflowing.push({
            element: el.tagName + '.' + el.className,
            scrollWidth: el.scrollWidth,
            clientWidth: el.clientWidth
          });
        }
      });
      return overflowing;
    `
  });
}
```

### Missing Spacing/Padding

**Symptoms:**
- Elements touching edges
- Text cramped
- No visual breathing room

**Diagnosis:**
```typescript
// Check computed spacing
mcp__playwright__browser_evaluate({
  script: `
    const element = document.querySelector('#cramped');
    const styles = window.getComputedStyle(element);
    return {
      padding: styles.padding,
      margin: styles.margin,
      width: styles.width,
      height: styles.height
    };
  `
})
```

## Rendering Issues

### Hidden/Invisible Elements

**Symptoms:**
- Elements don't appear
- Buttons can't be clicked
- Content missing

**Diagnosis:**
```typescript
// Check visibility
mcp__playwright__browser_evaluate({
  script: `
    const element = document.querySelector('#hidden');
    const styles = window.getComputedStyle(element);
    return {
      display: styles.display,
      visibility: styles.visibility,
      opacity: styles.opacity,
      width: styles.width,
      height: styles.height,
      offScreen: element.getBoundingClientRect().top < 0
    };
  `
})

// Take screenshot to verify
mcp__playwright__browser_take_screenshot({ full_page: true })
```

**Common causes:**
- `display: none`
- `visibility: hidden`
- `opacity: 0`
- Element positioned off-screen
- Zero width/height

### Flash of Unstyled Content (FOUC)

**Symptoms:**
- Page appears unstyled briefly
- Content jumps/shifts
- Styles load late

**Diagnosis:**
```typescript
// Navigate and immediately screenshot
mcp__playwright__browser_navigate({ url: "https://example.com" })
mcp__playwright__browser_take_screenshot()  // Before styles load

// Wait for styles
mcp__playwright__browser_wait_for({
  selector: "body.loaded",
  timeout: 2000
})
mcp__playwright__browser_take_screenshot()  // After styles load

// Check console for CSS load errors
const messages = mcp__playwright__browser_console_messages()
```

### Incorrect Colors/Fonts

**Symptoms:**
- Wrong colors displayed
- Fonts not loading
- Text rendering issues

**Diagnosis:**
```typescript
// Check computed styles
mcp__playwright__browser_evaluate({
  script: `
    const element = document.querySelector('h1');
    const styles = window.getComputedStyle(element);
    return {
      color: styles.color,
      fontFamily: styles.fontFamily,
      fontSize: styles.fontSize,
      fontWeight: styles.fontWeight,
      backgroundColor: styles.backgroundColor
    };
  `
})

// Check for font loading errors in network
const requests = mcp__playwright__browser_network_requests()
// Filter for .woff, .woff2, .ttf files with 4xx status
```

## Interaction Issues

### Buttons Not Responding

**Symptoms:**
- Clicks have no effect
- Hover states don't trigger
- Events not firing

**Diagnosis:**
```typescript
// Check if button is clickable
mcp__playwright__browser_evaluate({
  script: `
    const button = document.querySelector('button#submit');
    const styles = window.getComputedStyle(button);
    return {
      disabled: button.disabled,
      pointerEvents: styles.pointerEvents,
      cursor: styles.cursor,
      hasClickListener: !!button.onclick,
      zIndex: styles.zIndex
    };
  `
})

// Try clicking and monitor console
mcp__playwright__browser_click({ selector: "button#submit" })
const messages = mcp__playwright__browser_console_messages()
// Look for JavaScript errors
```

**Common causes:**
- `pointer-events: none`
- Element covered by overlay
- JavaScript errors preventing event handlers
- Button in disabled state
- Event listener not attached

### Form Fields Not Accepting Input

**Symptoms:**
- Can't type in input fields
- Inputs are read-only
- Values don't update

**Diagnosis:**
```typescript
// Check input state
mcp__playwright__browser_evaluate({
  script: `
    const input = document.querySelector('input#email');
    return {
      disabled: input.disabled,
      readOnly: input.readOnly,
      value: input.value,
      type: input.type
    };
  `
})

// Try typing and verify
mcp__playwright__browser_type({
  selector: "input#email",
  text: "test@example.com"
})

// Check if value updated
const updated = mcp__playwright__browser_evaluate({
  script: `return document.querySelector('input#email').value;`
})
```

### Hover Effects Not Working

**Symptoms:**
- No visual feedback on hover
- Tooltips don't appear
- Dropdown menus don't open

**Diagnosis:**
```typescript
// Hover over element
mcp__playwright__browser_hover({ selector: "#menu-trigger" })

// Take screenshot to check visual feedback
mcp__playwright__browser_take_screenshot()

// Check for tooltip/dropdown appearance
const visible = mcp__playwright__browser_evaluate({
  script: `
    const tooltip = document.querySelector('.tooltip');
    return tooltip && window.getComputedStyle(tooltip).display !== 'none';
  `
})
```

## Performance Issues

### Slow Page Load

**Symptoms:**
- Page takes long to become interactive
- White screen for extended period
- Resources load slowly

**Diagnosis:**
```typescript
// Navigate and monitor
mcp__playwright__browser_navigate({ url: "https://example.com" })

// Get network requests
const requests = mcp__playwright__browser_network_requests()
// Identify slow resources (duration > 3s)

// Check performance metrics
const perf = mcp__playwright__browser_evaluate({
  script: `
    const timing = performance.timing;
    return {
      domReady: timing.domContentLoadedEventEnd - timing.navigationStart,
      pageLoad: timing.loadEventEnd - timing.navigationStart,
      firstPaint: performance.getEntriesByType('paint')[0]?.startTime
    };
  `
})

// Monitor console for errors during load
const messages = mcp__playwright__browser_console_messages()
```

### Animation Janky/Stuttering

**Symptoms:**
- Choppy animations
- Scroll not smooth
- Visual stuttering

**Diagnosis:**
```typescript
// Check for expensive CSS
mcp__playwright__browser_evaluate({
  script: `
    const animated = document.querySelector('.animated');
    const styles = window.getComputedStyle(animated);
    return {
      willChange: styles.willChange,
      transform: styles.transform,
      animation: styles.animation
    };
  `
})

// Record before/during/after animation
mcp__playwright__browser_take_screenshot()
// Trigger animation
mcp__playwright__browser_take_screenshot()  // Mid-animation
// Wait for completion
mcp__playwright__browser_take_screenshot()  // After
```

## JavaScript Errors

### Console Errors Breaking Functionality

**Symptoms:**
- Features stop working
- Page partially functional
- Unexpected behavior

**Diagnosis:**
```typescript
// Navigate and capture all console messages
mcp__playwright__browser_navigate({ url: "https://example.com" })
const messages = mcp__playwright__browser_console_messages()

// Filter by type
// - error: Critical failures
// - warning: Potential issues
// - log: Debug information

// Perform actions that might trigger errors
mcp__playwright__browser_click({ selector: "button#action" })
const newMessages = mcp__playwright__browser_console_messages()
// Compare to identify new errors
```

**Common error types:**
- Uncaught TypeError
- Reference errors (undefined variables)
- Network request failures
- CORS errors
- Module loading failures

### Third-Party Script Failures

**Symptoms:**
- Analytics not tracking
- Chat widgets not loading
- External features missing

**Diagnosis:**
```typescript
// Check network for third-party requests
const requests = mcp__playwright__browser_network_requests()
// Filter for external domains (analytics.js, chat.js, etc.)
// Look for 4xx/5xx status codes

// Check console for related errors
const messages = mcp__playwright__browser_console_messages()
// Look for errors from external domains
```

## Authentication Issues

### Login Not Working

**Symptoms:**
- Can't log in
- Redirects fail
- Session not persisting

**Diagnosis:**
```typescript
// Fill login form
mcp__playwright__browser_type({
  selector: "input[name='email']",
  text: "test@example.com"
})
mcp__playwright__browser_type({
  selector: "input[name='password']",
  text: "password123"
})

// Monitor console during submit
mcp__playwright__browser_click({ selector: "button[type='submit']" })
const messages = mcp__playwright__browser_console_messages()

// Check network for auth request
const requests = mcp__playwright__browser_network_requests()
// Look for /login, /auth endpoints
// Check status codes and response

// Verify redirect occurred
const currentUrl = mcp__playwright__browser_evaluate({
  script: `return window.location.href;`
})
```

### Protected Pages Accessible Without Auth

**Symptoms:**
- Should redirect to login but doesn't
- Unauthorized access possible
- Security vulnerability

**Diagnosis:**
```typescript
// Navigate to protected page directly
mcp__playwright__browser_navigate({
  url: "https://app.example.com/admin"
})

// Check if redirected to login
const url = mcp__playwright__browser_evaluate({
  script: `return window.location.href;`
})

// Or check for access denied message
mcp__playwright__browser_take_screenshot()
const snapshot = mcp__playwright__browser_snapshot()
```

## Mobile-Specific Issues

### Touch Targets Too Small

**Symptoms:**
- Hard to tap buttons on mobile
- Accidental clicks
- Poor usability

**Diagnosis:**
```typescript
// Switch to mobile viewport
mcp__playwright__browser_resize({
  width: 375,
  height: 667
})

// Measure touch targets
const sizes = mcp__playwright__browser_evaluate({
  script: `
    const buttons = document.querySelectorAll('button, a');
    return Array.from(buttons).map(btn => {
      const rect = btn.getBoundingClientRect();
      return {
        element: btn.textContent.trim(),
        width: rect.width,
        height: rect.height,
        tooSmall: rect.width < 44 || rect.height < 44  // 44px min
      };
    });
  `
})

mcp__playwright__browser_take_screenshot({ full_page: true })
```

### Viewport Meta Tag Issues

**Symptoms:**
- Page zoomed out on mobile
- Not responsive
- Desktop layout on mobile

**Diagnosis:**
```typescript
// Check viewport meta tag
const viewport = mcp__playwright__browser_evaluate({
  script: `
    const meta = document.querySelector('meta[name="viewport"]');
    return meta ? meta.content : 'MISSING';
  `
})

// Should be: width=device-width, initial-scale=1
```
