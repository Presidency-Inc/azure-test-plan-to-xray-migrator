import os
import json
from logging.handlers import RotatingFileHandler
from datetime import datetime
from dotenv import load_dotenv

class ScopeClient:
    def __init__(self):
        load_dotenv()
        # Load list of projects to migrate
        input_file = os.path.join(os.path.dirname(__file__), '../config/migration_scope.json')
        with open(input_file, 'r', encoding='utf-8') as f:
            projects_to_migrate = json.load(f)
            print(f"Loaded {len(projects_to_migrate)} test cases")

        self.migration_projects = projects_to_migrate or []
        self.current_project = None
        self.current_suite = None

    def projects_counter(self):
        return len(self.migration_projects)

    def update_current_scope(self, source_plan_id, source_suite_id):
        """Update current migration state"""
        project = next((p for p in self.migration_projects 
                       if p['source_plan_id'] == source_plan_id and p['source_suite_id'] == source_suite_id), None)
        
        if not project:
            raise ValueError(f"Project {source_plan_id} not found")

        self.current_project = project
        

    def get_current_target_info(self):
        """Get current target information based on mode"""
        if not self.current_project:
            raise ValueError("No active migration context")
            
        return {
            'project_target_key': self.current_project['project_target_key'],
            'project_target_id': self.current_project['project_target_id'],
            'assignee': self.current_project['assignee'],
            'folder_path': self.current_project['folder_path']
        }
            
def main():
    try:
        # Example usage
        client = ScopeClient()
        
        print("Projects to migrate:")
        for project in client.migration_projects:
            print(f"ID: {project['source_project_id']}, Name: {project['project_target_id']}, Assignee: {project['assignee']}")
        
            
    except Exception as e:
        print(f"Main process failed: {str(e)}")
        raise

if __name__ == '__main__':
    main()
