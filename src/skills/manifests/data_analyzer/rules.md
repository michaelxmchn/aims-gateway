<!-- AIMS Protocol | Version 1.0.0 | Last Updated: 2026-06-09 | Hermes-Verified -->

# Data Analyzer — Operation Rules

## Purpose
Analyze a CSV dataset and return statistical summaries, correlation insights, and data quality reports. Useful for quick data exploration without writing Python code.

## Input Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_path` | string | **YES** | — | Absolute path to the CSV file on disk |
| `analysis_type` | string | no | "summary" | Type: `summary`, `correlation`, `quality`, or `full` |

## Output Format

The skill returns a JSON object:

```json
{
  "report": "# Data Analysis Report\n\n## Summary Statistics\n...",
  "row_count": 1500
}
```

The `report` field contains a markdown-formatted analysis report.

## Analysis Rules by Type

### Summary Analysis
- For numeric columns: count, mean, std, min, 25%, 50%, 75%, max
- For categorical columns: count, unique, top, frequency
- For datetime columns: min, max, range in days
- Include a column-by-column data type summary

### Correlation Analysis
- Compute Pearson correlation matrix for all numeric columns
- Identify the top 5 strongest positive and negative correlations
- Flag any correlation with |r| > 0.8 as "strong correlation"
- Include a correlation heatmap description (text-based)

### Data Quality Analysis
- Report missing value counts and percentages per column
- Report duplicate row count
- Detect and flag outliers using IQR method (Q1 - 1.5*IQR, Q3 + 1.5*IQR)
- Flag columns with >50% missing values as "unreliable"
- Check for inconsistent data types within columns

### Full Analysis
- Runs all three analyses above and combines them into one report

## Operating Rules

### 1. File Handling
- The CSV file MUST exist at the provided `file_path`. If not found, return an error.
- Auto-detect delimiter (comma, tab, semicolon) by sampling the first 5 lines.
- Auto-detect encoding (try UTF-8 first, fall back to latin-1).
- Skip empty lines and lines with only whitespace.

### 2. Data Handling Rules
- Do NOT modify the original CSV file — analysis is read-only.
- For files larger than 100MB, warn the user and abort (MVP limitation).
- If the CSV has fewer than 2 rows of data, return error: "Dataset too small for analysis."
- Columns with all null values should be noted but excluded from numeric analysis.

### 3. Privacy Rules
- Do NOT output raw cell values that could be PII (email addresses, phone numbers, SSNs).
- If a column name contains keywords like "email", "phone", "ssn", "address", mask the sample values.
- Summary statistics (mean, std, counts) are safe — individual row data is not.

### 4. Output Constraints
- The `report` field MUST be valid markdown with proper table formatting.
- The `row_count` MUST match the actual number of data rows (excluding the header).
- All numeric values in output should be rounded to 2 decimal places.

## Notes for the AI Agent
- This skill requires read access to the local filesystem.
- For large datasets, suggest the user narrow the analysis scope before running.
- When presenting, start with the data quality overview (how much is missing/clean) before diving into statistics.
