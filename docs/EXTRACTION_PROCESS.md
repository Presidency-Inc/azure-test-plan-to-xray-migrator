# Azure Test Plans Extraction Process

This document provides an in-depth explanation of the extraction process from Azure Test Plans, covering both full extraction and CSV-based selective extraction.

## Extraction Architecture

The extraction process follows these main steps:

1. Initialize the Azure Client with the necessary credentials
2. Query the Azure DevOps API for test plans data
3. Extract related test suites, test cases, test points, and test results
4. Save the extracted data to JSON files

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│                 │     │              │     │                 │
│  Azure DevOps   │◄────┤ Azure Client │◄────┤  Extractor      │
│  API            │     │              │     │                 │
│                 │     │              │     │                 │
└────────┬────────┘     └──────────────┘     └─────────┬───────┘
         │                                             │
         │                                             │
         ▼                                             ▼
┌─────────────────┐                          ┌─────────────────┐
│                 │                          │                 │
│  Test Plan      │                          │  JSON Output    │
│  Data           │                          │  Files          │
│                 │                          │                 │
└─────────────────┘                          └─────────────────┘
```

## Full Extraction

When running the extraction without a CSV file, the process extracts all test plans from the project:

1. Retrieve all test plans
2. For each test plan, retrieve all test suites
3. For each test suite, retrieve all test cases
4. For all test cases, retrieve test points
5. For all test points, retrieve test results

## CSV-Based Extraction

When providing a CSV file, the extraction becomes more selective:

1. Parse the CSV file using the `AzureTestPlanCSVParser`
2. Extract plan IDs and suite IDs from Azure DevOps URLs in the CSV
3. Retrieve only the specific test plans and suites mentioned in the CSV
4. Extract test cases, test points, and test results only for those specific plans/suites

### CSV Parser Implementation

The CSV parser has the following responsibilities:

- Read and validate the CSV file format
- Extract Azure DevOps URLs from the specified column
- Parse the URLs to extract plan IDs and suite IDs
- Create a mapping between plans and their suites
- Provide methods to retrieve unique plan IDs and plan-suite mappings

## Data Structure

The extracted data is organized in the following hierarchy:

- **Test Plans**: Top-level objects containing multiple test suites
- **Test Suites**: Groups of test cases, potentially arranged in a hierarchy
- **Test Cases**: Detailed test specifications with steps, expected results, etc.
- **Test Points**: Instances of test cases with configurations
- **Test Results**: Execution results for test points, including pass/fail status

## Output Format

The extraction process generates several JSON files:

- `test_plans.json`: Contains all extracted test plans
- `test_suites.json`: Contains all extracted test suites
- `test_cases.json`: Contains all extracted test cases
- `test_points.json`: Contains all extracted test points
- `test_results.json`: Contains all extracted test results
- `extraction_summary.json`: Summary of the extraction process

When using CSV-based extraction, an additional file is generated:
- `csv_mapping.json`: Contains the mapping between CSV data and extracted plans/suites

## Error Handling

The extraction process includes robust error handling:

- Connection errors to Azure DevOps API
- Authentication and permission issues
- Invalid or missing data in the CSV file
- Rate limiting and throttling by the Azure DevOps API
- Unexpected data formats or structures

## Performance Considerations

To optimize performance, the extraction process:

- Uses asynchronous requests to the Azure DevOps API
- Implements batching for retrieving multiple items
- Caches data to avoid redundant API calls
- Provides progress indicators for long-running extractions
- Handles pagination for large result sets

## Next Steps After Extraction

After extraction, the data is ready for the mapping phase, where it will be transformed into the Xray data model format before loading it into Jira. 