# CSV-Based Test Plan Extraction

This document explains how to use the CSV-based extraction feature to extract specific test plans from Azure Test Plans.

## CSV Format Requirements

The CSV file should have the following format:

1. The first row is a header row
2. The second row may contain column headers
3. From the third row onwards, data should follow this format:
   - Column 1: Test Suite Name
   - Column 2: Owner
   - Column 3: Email
   - Column 4: Azure DevOps URLs

The URLs in column 4 should follow the Azure DevOps format:
```
https://dev.azure.com/OrganizationName/ProjectName/_testPlans/define?planId=X&suiteId=Y
```

Multiple URLs can be included in the same cell, each on a new line.

Example CSV:
```
Test Suite ,,,,,,,,,,,,
Test Suite Name,Owner,Email,URL,Count,Automated,,,Key,Test Repository,Suite,Test Repository Folder,,
Advisor Insights,John Doe,john.doe@example.com,https://dev.azure.com/OrgName/Project/_testPlans/define?planId=218&suiteId=4135,685,,,PROJ,Test Repository/,Advisor Insights,Test Repository/Advisor Insights,,
Dashboard regression,Jane Smith,jane.smith@example.com,"https://dev.azure.com/OrgName/Project/_testPlans/define?planId=2010&suiteId=2021
https://dev.azure.com/OrgName/Project/_testPlans/define?planId=2318&suiteId=2332",540,YES,,PROJ,Test Repository/,Dashboard/Regression,Test Repository/Dashboard/Regression,,
```

## Running the Extraction with a CSV

To extract test plans based on a CSV file, use the `--csv` parameter when running the main script:

```bash
# Basic extraction (monolithic output)
python src/main.py --csv path/to/your/file.csv

# With modular output (separate files for each test plan)
python src/main.py --csv path/to/your/file.csv --modular
```

## Output Formats

The extraction process supports two output formats:

### 1. Monolithic Output (Default)

All extracted data is combined into a single set of files in the extraction directory:

- `test_plans.json`: All test plans specified in the CSV
- `test_suites.json`: All test suites specified in the CSV
- `test_cases.json`: All test cases from the specified test suites
- `test_points.json`: All test points associated with the extracted test cases
- `test_results.json`: All test results for the extracted test points
- `csv_mapping.json`: The original data from the CSV for reference
- `extraction_summary.json`: Summary of the extraction process with counts

### 2. Modular Output (With `--modular` flag)

In addition to the monolithic output, separate files are created for each test plan in a `modular` subdirectory:

```
output/data/extraction/[timestamp]/
├── [monolithic files as above]
└── modular/
    ├── plan_123/
    │   ├── test_plans.json       # Only contains plan 123
    │   ├── test_points.json      # Only test points for plan 123
    │   ├── test_results.json     # Only test results for plan 123
    │   ├── test_configurations.json  # All configurations (shared)
    │   ├── test_variables.json   # All variables (shared)
    │   └── extraction_summary.json
    ├── plan_456/
    │   └── [same structure as above]
    └── ...
```

This organization helps when you need to process each test plan separately.

## How It Works

1. The script parses the CSV file and extracts all Azure DevOps URLs
2. For each URL, it extracts the `planId` and `suiteId` parameters
3. The extractor then fetches only those specific test plans and suites
4. All related test cases, test points, and test results are also extracted
5. The original CSV mapping is included in the output for reference
6. If modular output is enabled, additional directories are created for each test plan

## Output Location

The extraction results will be saved in a timestamped directory under `output/data/extraction/` to ensure each extraction is preserved.

Each extraction will have a unique timestamp-based directory name, for example:
```
output/data/extraction/20230915_142302/
``` 