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
├── output/                 # Output directory for extracted and mapped data
│   └── data/
│       ├── extraction/     # Extracted data from Azure Test Plans
│       └── mapping/        # Mapped data ready for Xray import
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

Run the main script to start the migration process:

```bash
python src/main.py
```

The script will:
1. Extract all test plans data from Azure Test Plans
2. Save the extracted data to the `output/data/extraction` directory
3. (Future) Map the data to Xray format
4. (Future) Load the data into Xray for Jira

## Extracted Data

The extraction process will create a timestamped directory in `output/data/extraction` containing the following files:

- `test_plans.json`: All test plans with their hierarchical structure
- `test_configurations.json`: All test configurations
- `test_variables.json`: All test variables
- `test_points.json`: All test points
- `test_results.json`: All test results
- `extraction_summary.json`: Summary of the extraction process

## Development

### Adding New Features

1. **Extractors**: Extend the `AzureTestExtractor` class in `src/extractors/azure_test_extractor.py`
2. **Mappers**: Create mapper classes in `src/mappers/` directory
3. **Loaders**: Create loader classes in `src/loaders/` directory

## License

This project is licensed under the MIT License - see the LICENSE file for details. 