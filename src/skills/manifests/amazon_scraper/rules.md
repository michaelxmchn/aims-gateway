<!-- AIMS Protocol | Version 1.0.0 | Last Updated: 2026-06-09 | Hermes-Verified -->

# Amazon Competitor Scraper — Operation Rules

## Purpose
Scrape Amazon product listing pages for a given search term and return structured competitor intelligence data. Use this skill when the user needs to research product pricing, competition, or market positioning on Amazon.

## Input Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `search_term` | string | **YES** | — | The product keyword or phrase to search (e.g., "wireless headphones", "yoga mat") |
| `max_results` | number | no | 10 | How many products to return (1–50). Higher values take longer. |
| `sort_by` | string | no | "relevance" | Sort order: `relevance`, `price_low_high`, `price_high_low`, `rating`, `newest` |

## Output Format

The skill returns a JSON object with exactly this structure:

```json
{
  "search_term": "wireless headphones",
  "total_found": 42,
  "products": [
    {
      "title": "Sony WH-1000XM5 Wireless Noise Cancelling Headphones",
      "asin": "B09Y3ZZ8ZZ",
      "price": 348.00,
      "currency": "USD",
      "rating": 4.6,
      "review_count": 12453,
      "seller": "Amazon.com",
      "prime_eligible": true,
      "sponsored": false,
      "url": "https://www.amazon.com/dp/B09Y3ZZ8ZZ"
    }
  ]
}
```

## Operating Rules

### 1. Rate Limiting & Politeness
- **Minimum 2-second delay** between consecutive requests to Amazon.
- If an HTTP 503 (Service Unavailable) or 429 (Too Many Requests) is received, **wait 10 seconds** and retry once. If it fails again, return an error — do not hammer the server.
- Respect `robots.txt` disallow rules for Amazon's search pages.

### 2. Data Quality Rules
- Always return prices as numeric floats (not strings like "$348.00"). Strip currency symbols and commas.
- If a product has no reviews, set `review_count` to 0 and `rating` to `null`.
- The `prime_eligible` field must be a boolean. If unclear from the page, default to `false`.
- The `sponsored` field must accurately reflect whether the listing is a sponsored ad. Check for "Sponsored" labels in the listing.

### 3. Error Handling
- If the search term returns zero results, do NOT fabricate data. Return `{ "products": [], "total_found": 0, "search_term": "..." }`.
- If Amazon shows a CAPTCHA or bot-detection page, abort immediately and return error: "Amazon bot detection triggered — manual intervention required."
- Network timeouts: set a 15-second timeout per request. On timeout, retry once.

### 4. Privacy & Compliance
- Do NOT attempt to scrape customer PII (personally identifiable information) such as reviewer names, purchase histories, or addresses.
- Do NOT scrape pages behind the login wall (e.g., "Your Orders", "Your Account").
- This skill is for **public product listing data only**.

### 5. Output Constraints
- The output MUST be valid JSON parseable by `json.loads()`.
- Every product entry MUST have all fields populated (use `null` for missing data, never omit the field).
- Sort the returned products by the requested `sort_by` parameter. If `sort_by` is not recognized, default to `relevance`.

## Example Usage

**User:** "Find me the top 5 best-selling noise cancelling headphones on Amazon"

→ `{ "search_term": "noise cancelling headphones", "max_results": 5, "sort_by": "relevance" }`

**User:** "What are the cheapest yoga mats on Amazon? Show me 20."

→ `{ "search_term": "yoga mat", "max_results": 20, "sort_by": "price_low_high" }`

## Notes for the AI Agent
- This skill requires network access (HTTP/HTTPS). Ensure the runtime environment allows outbound connections to `www.amazon.com`.
- The skill's results are a snapshot in time. Prices and availability change frequently.
- When presenting results to the user, summarize competitive insights (price range, average rating, top sellers) rather than just dumping the raw JSON.
