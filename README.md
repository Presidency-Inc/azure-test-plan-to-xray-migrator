# Azure Test Plans to Xray Jira Migrator

A tool to migrate test plans, test cases, and test results from Azure Test Plans to Xray for Jira.

## Overview

This project provides a comprehensive solution for migrating testing data from Azure Test Plans to Xray for Jira. The migration process consists of three main phases:

1. **Extraction**: Extract all test data from Azure Test Plans
2. **Mapping**: Map the Azure Test Plans data structure to Xray's data structure
3. **Loading**: Load the mapped data into Xray for Jira

## Project Structure

```
azure-test-plan-to-xray-migrator/
├── .env                    # Environment variables for configuration
├── requirements.txt        # Python dependencies
├── docs/                   # Documentation
│   ├── CSV_EXTRACTION.md   # Documentation for CSV-based extraction
│   ├── EXTRACTION_PROCESS.md # Documentation for the extraction process
│   └── schemas/            # JSON schemas for data structures
├── output/                 # Output directory for extracted and mapped data
│   └── data/
│       ├── extraction/     # Extracted data from Azure Test Plans
│       └── mapping/        # Mapped data ready for Xray import
├── scripts/                # Utility scripts
│   └── run_csv_extraction.py # Script for running CSV-based extraction
└── src/                    # Source code
    ├── config/             # Configuration modules
    ├── extractors/         # Data extraction modules
    ├── mappers/            # Data mapping modules
    ├── loaders/            # Data loading modules
    ├── utils/              # Utility functions
    └── main.py             # Main entry point
```

## Setup

1. Clone the repository
2. Create a virtual environment: `python -m venv venv`
3. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - macOS/Linux: `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Create a `.env` file with the following variables:
   ```
   ORGANIZATION_URL=https://dev.azure.com/your-organization
   PERSONAL_ACCESS_TOKEN=your-azure-devops-pat
   PROJECT_NAME=your-project-name
   ```

## Usage

### Extract All Test Plans

Run the main script to extract all test plans from your Azure DevOps project:

```bash
python src/main.py
```

### Extract Specific Test Plans from CSV

You can extract specific test plans by providing a CSV file with Azure DevOps URLs:

```bash
# Monolithic output (all plans in one set of files)
python src/main.py --csv path/to/your/file.csv

# Modular output (separate files for each test plan + combined files)
python src/main.py --csv path/to/your/file.csv --modular
```

Alternatively, you can use the dedicated extraction script:

```bash
python scripts/run_csv_extraction.py path/to/your/file.csv [--modular]
```

For detailed information about the CSV format and extraction process, see [CSV-Based Extraction](docs/CSV_EXTRACTION.md).

## Output Formats

The extraction process supports two output formats:

### 1. Monolithic Output (Default)

All extracted data is combined into a single set of files:

- `test_plans.json`: Test plans with their hierarchical structure
- `test_suites.json`: Test suites
- `test_cases.json`: Test cases with steps
- `test_points.json`: Test points
- `test_results.json`: Test results
- `test_configurations.json`: Test configurations
- `test_variables.json`: Test variables
- `extraction_summary.json`: Summary of the extraction process

### 2. Modular Output (With `--modular` flag)

In addition to the monolithic output, each test plan gets its own set of files in a `modular` subdirectory. This is useful when dealing with large test plans that need to be processed separately.

## Development

### Adding New Features

1. **Extractors**: Extend the `AzureTestExtractor` class in `src/extractors/azure_test_extractor.py`
2. **Mappers**: Create mapper classes in `src/mappers/` directory
3. **Loaders**: Create loader classes in `src/loaders/` directory

## Documentation

- [CSV-Based Extraction](docs/CSV_EXTRACTION.md): Detailed information about CSV-based extraction
- [Extraction Process](docs/EXTRACTION_PROCESS.md): In-depth explanation of the extraction process

## License

This project is licensed under the MIT License - see the LICENSE file for details. 