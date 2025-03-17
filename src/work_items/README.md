# Work Items Module

This module handles the extraction, processing, and integration of work item data from Azure DevOps, focusing specifically on test case work items.

## Purpose

The main purpose of this module is to enhance the test case extraction process by retrieving detailed test case information stored in work items. This includes:

- Test steps with actions and expected results
- Test preconditions
- Test parameters and parameter values
- Automation status
- Attachments metadata

## Components

### 1. WorkItemExtractor

Located in `work_item_extractor.py`, this class is responsible for:

- Extracting work item IDs from test cases
- Defining essential test case fields to retrieve
- Retrieving work items in batches from Azure DevOps API
- Coordinating the extraction process

### 2. WorkItemProcessor

Located in `work_item_processor.py`, this class is responsible for:

- Processing raw work item data into structured formats
- Parsing XML content in work item fields (steps, parameters)
- Enhancing test cases with detailed work item data
- Saving processed data to JSON files

## Integration

This module integrates with the existing extraction process in the following way:

1. After extracting test plans, suites, and test cases, the `extract_entire_project` method calls the work item extraction process
2. Work item IDs are extracted from the test cases
3. Work items are retrieved and processed
4. Test cases are enhanced with work item data
5. Both raw work items and enhanced test cases are saved to separate JSON files

## Data Flow

```
Azure DevOps API → AzureDevOpsClient → WorkItemExtractor → WorkItemProcessor → Enhanced Test Cases
```

## Usage

The work item extraction process is automatically included in the `extract_entire_project` method. When you run:

```bash
python -m src.main --extract-project --project-name <project_name>
```

The following files will be included in the extraction results:

- `work_items.json`: Contains processed work items with structured test steps
- `enhanced_test_cases.json`: Contains test cases enhanced with work item data

## Field Mapping

The following important Azure DevOps fields are extracted for test cases:

| Azure DevOps Field               | Description                        |
|----------------------------------|------------------------------------|
| System.Id                        | Unique identifier                  |
| System.Title                     | Test case title                    |
| System.Description               | Test case description              |
| Microsoft.VSTS.TCM.Steps         | Test steps (actions and results)   |
| Microsoft.VSTS.TCM.Parameters    | Parameter definitions              |
| Microsoft.VSTS.TCM.LocalDataSource | Parameter values                 |
| Microsoft.VSTS.TCM.Prerequisites | Test preconditions                 |
| Microsoft.VSTS.Common.Priority   | Test priority                      |
| Microsoft.VSTS.TCM.AutomationStatus | Automation status (Y/N)         |
| System.State                     | Current state                      |
| System.Tags                      | Test tags                          |

## Future Enhancements

Planned enhancements for future versions:

1. Attachment downloading and processing
2. Test history and results integration
3. Associated automation details
4. Comment and discussion extraction 