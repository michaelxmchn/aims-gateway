# Playwright Patterns

Advanced patterns for effective visual debugging with Playwright.

## Network Monitoring

Monitor network requests to debug API calls and resource loading:

```typescript
// Get all network requests
const requests = mcp__playwright__browser_network_requests()

// Filter for specific patterns
// Look for:
// - Failed requests (status 4xx, 5xx)
// - Slow requests (duration > 3s)
// - Large payloads (size > 1MB)
// - API endpoints
```

**Use cases:**
- Debug API errors
- Identify slow resources
- Check API response data
- Verify request headers/cookies

## Dialog Handling

Handle browser alerts, confirms, and prompts:

```typescript
// Handle dialog before triggering action
mcp__playwright__browser_handle_dialog({
  action: "accept",  // or "dismiss"
  promptText: "optional text for prompts"
})

// Then perform action that triggers dialog
mcp__playwright__browser_click({ selector: "button#delete" })
```

**Common scenarios:**
- Confirm dialogs on delete actions
- Alert messages
- Prompt inputs
- Authentication popups

## File Upload Testing

Test file upload functionality:

```typescript
// Upload file
mcp__playwright__browser_file_upload({
  selector: "input[type='file']",
  filePath: "/path/to/test-file.pdf"
})

// Verify upload
mcp__playwright__browser_wait_for({
  selector: ".upload-success",
  timeout: 10000
})
```

## JavaScript Execution

Run custom JavaScript for advanced debugging:

```typescript
// Get computed styles
mcp__playwright__browser_evaluate({
  script: `
    const element = document.querySelector('#target');
    const styles = window.getComputedStyle(element);
    return {
      display: styles.display,
      opacity: styles.opacity,
      visibility: styles.visibility
    };
  `
})

// Scroll to element
mcp__playwright__browser_evaluate({
  script: `
    document.querySelector('#bottom-element').scrollIntoView();
  `
})

// Check local storage
mcp__playwright__browser_evaluate({
  script: `return localStorage.getItem('userToken');`
})
```

**Use cases:**
- Get computed CSS properties
- Access local/session storage
- Manipulate DOM for testing
- Trigger JavaScript functions
- Read application state

## Multi-Tab Testing

Test features that open new tabs:

```typescript
// List current tabs
const tabs = mcp__playwright__browser_tab_list()

// Click link that opens new tab
mcp__playwright__browser_click({ selector: "a[target='_blank']" })

// Switch to new tab
const updatedTabs = mcp__playwright__browser_tab_list()
const newTab = updatedTabs.find(tab => !tabs.includes(tab))
mcp__playwright__browser_tab_select({ tabId: newTab.id })

// Test in new tab
// ...

// Close and return to original
mcp__playwright__browser_tab_close({ tabId: newTab.id })
```

## Waiting Strategies

Different waiting approaches for different scenarios:

**Wait for element:**
```typescript
// Wait for selector to appear
mcp__playwright__browser_wait_for({
  selector: ".loading-complete",
  timeout: 5000
})
```

**Wait for navigation:**
```typescript
// After clicking link
mcp__playwright__browser_click({ selector: "a#next-page" })
// Playwright automatically waits for navigation
```

**Wait for state:**
```typescript
// Wait for element to be visible and enabled
mcp__playwright__browser_wait_for({
  selector: "button#submit",
  state: "visible",
  timeout: 5000
})
```

**Custom wait with evaluate:**
```typescript
// Wait for custom condition
mcp__playwright__browser_evaluate({
  script: `
    return new Promise(resolve => {
      const check = () => {
        if (window.appReady) resolve(true);
        else setTimeout(check, 100);
      };
      check();
    });
  `
})
```

## Screenshot Strategies

Different screenshot approaches for different needs:

**Full page:**
```typescript
mcp__playwright__browser_take_screenshot({
  full_page: true,
  path: "full-page.png"
})
```

**Specific element:**
```typescript
mcp__playwright__browser_take_screenshot({
  selector: "#component",
  full_page: false,
  path: "component.png"
})
```

**Viewport only:**
```typescript
mcp__playwright__browser_take_screenshot({
  full_page: false,
  path: "viewport.png"
})
```

## Error Recovery Patterns

Handle common errors gracefully:

**Element not found:**
```typescript
// Take screenshot to diagnose
mcp__playwright__browser_take_screenshot({ full_page: true })

// Check DOM snapshot
const snapshot = mcp__playwright__browser_snapshot()
// Analyze snapshot for actual selectors

// Adjust selector and retry
```

**Timing issues:**
```typescript
// Add explicit wait before action
mcp__playwright__browser_wait_for({
  selector: "button#submit",
  timeout: 10000
})

mcp__playwright__browser_click({ selector: "button#submit" })
```

**Overlapping elements:**
```typescript
// Scroll to element first
mcp__playwright__browser_evaluate({
  script: `document.querySelector('#target').scrollIntoView({
    behavior: 'smooth',
    block: 'center'
  });`
})

// Wait for scroll to complete
await new Promise(resolve => setTimeout(resolve, 500))

// Then click
mcp__playwright__browser_click({ selector: "#target" })
```

## Accessibility Testing

Check accessibility of elements:

```typescript
// Get ARIA attributes
mcp__playwright__browser_evaluate({
  script: `
    const button = document.querySelector('button#submit');
    return {
      role: button.getAttribute('role'),
      ariaLabel: button.getAttribute('aria-label'),
      ariaDisabled: button.getAttribute('aria-disabled'),
      ariaExpanded: button.getAttribute('aria-expanded')
    };
  `
})

// Check keyboard navigation
mcp__playwright__browser_press_key({ key: "Tab" })
mcp__playwright__browser_take_screenshot()  // Verify focus indicator

mcp__playwright__browser_press_key({ key: "Enter" })
// Verify action triggered
```

## Performance Monitoring

Monitor page performance:

```typescript
// Get performance metrics via JavaScript
mcp__playwright__browser_evaluate({
  script: `
    const perfData = window.performance.timing;
    const loadTime = perfData.loadEventEnd - perfData.navigationStart;
    const domReady = perfData.domContentLoadedEventEnd - perfData.navigationStart;

    return {
      loadTime: loadTime,
      domReady: domReady,
      resources: performance.getEntriesByType('resource').length
    };
  `
})
```

## Session Persistence

Maintain session across multiple tests:

```typescript
// Login once
// Navigate and login...

// Test multiple pages without re-authenticating
mcp__playwright__browser_navigate({ url: "https://app.example.com/dashboard" })
// Session cookies persist

mcp__playwright__browser_navigate({ url: "https://app.example.com/settings" })
// Still authenticated
```

## Conditional Logic Patterns

Make decisions based on page state:

```typescript
// Check if element exists
const snapshot = mcp__playwright__browser_snapshot()

if (snapshot.includes('id="login-required"')) {
  // Perform login flow
  // ...
} else {
  // Already logged in, proceed
  // ...
}
```

## Debugging AJAX/SPA Applications

Handle dynamic content:

```typescript
// Navigate to SPA
mcp__playwright__browser_navigate({ url: "https://spa.example.com" })

// Wait for initial load
mcp__playwright__browser_wait_for({
  selector: "[data-loaded='true']",
  timeout: 10000
})

// Click navigation (triggers AJAX)
mcp__playwright__browser_click({ selector: "a#users" })

// Wait for content update
mcp__playwright__browser_wait_for({
  selector: ".user-list",
  timeout: 5000
})

// Monitor network requests
const requests = mcp__playwright__browser_network_requests()
// Check for API calls
```
