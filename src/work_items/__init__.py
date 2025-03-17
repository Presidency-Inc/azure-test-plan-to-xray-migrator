"""
Work Items module for Azure Test Plan to Xray Migrator.

This module contains components for extracting and processing work items
that represent test cases in Azure DevOps.
"""

from src.work_items.work_item_extractor import WorkItemExtractor
from src.work_items.work_item_processor import WorkItemProcessor

__all__ = [
    'WorkItemExtractor',
    'WorkItemProcessor',
] 