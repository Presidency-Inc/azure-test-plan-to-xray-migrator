import os
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

class TestCaseBatcher:
    def __init__(self, chunk_size=2):
        self.chunk_size = chunk_size
        # Fix paths to be relative to script location
        self.base_dir = os.path.dirname(__file__)
        self.import_folder = os.path.join(self.base_dir, '../importFiles')
        self.output_folder = os.path.join(self.base_dir, '../finalImportFiles')
        self.logger = self._setup_logging()
        
        # Ensure output directory exists
        os.makedirs(self.output_folder, exist_ok=True)
        self.logger.info(f"Import folder path: {self.import_folder}")
        self.logger.info(f"Output folder path: {self.output_folder}")
        
    def _setup_logging(self):
        """Configure logging with both file and console handlers"""
        log_dir = os.path.join(self.base_dir, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = os.path.join(log_dir, f'batcher_{timestamp}.log')
        
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
        )
        
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10*1024*1024, backupCount=5
        )
        file_handler.setFormatter(formatter)
        
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        logger = logging.getLogger('batcher')
        logger.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger

    def save_chunk(self, chunk, output_file):
        """Save a chunk of test cases to a file"""
        try:
            output_path = os.path.join(self.output_folder, output_file)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(chunk, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Successfully saved chunk to {output_path}")
        except Exception as e:
            self.logger.error(f"Error saving chunk to {output_file}: {str(e)}")
            raise

    def batch_file(self, source_file):
        """Split a single source file into batched files of 50 test cases each"""
        try:
            self.logger.info(f"Starting to batch file: {source_file}")
            project_id = source_file.split('_')[2].split('.')[0]
            
            input_path = os.path.join(self.import_folder, source_file)
            self.logger.debug(f"Reading from input path: {input_path}")
            
            if not os.path.exists(input_path):
                self.logger.error(f"Input file not found: {input_path}")
                return
                
            with open(input_path, 'r', encoding='utf-8') as f:
                test_cases = json.load(f)
            
            total_cases = len(test_cases)
            self.logger.info(f"Found {total_cases} test cases to batch in {source_file}")
            
            # Split into chunks and save
            for i, chunk_start in enumerate(range(0, total_cases, self.chunk_size)):
                chunk = test_cases[chunk_start:chunk_start + self.chunk_size]
                output_file = f"test_cases_{project_id}_{i+1}.json"
                self.logger.debug(f"Creating batch {i+1} with {len(chunk)} test cases")
                self.save_chunk(chunk, output_file)
                
            self.logger.info(f"Successfully batched {source_file} into {i+1} files")
            
        except Exception as e:
            self.logger.error(f"Error processing file {source_file}: {str(e)}")
            raise

    def process_all_files(self):
        """Process all test case files in the import folder"""
        try:
            self.logger.info("Starting to process all files")
            if not os.path.exists(self.import_folder):
                self.logger.error(f"Import folder not found: {self.import_folder}")
                return
                
            files_to_process = []
            for filename in os.listdir(self.import_folder):
                if (filename.startswith('test_cases_') and 
                    filename.endswith('.json') and 
                    not any(x in filename for x in ['SFDC', 'SFSTARS'])):
                    files_to_process.append(filename)
            
            if not files_to_process:
                self.logger.warning("No files found to process")
                return
                
            self.logger.info(f"Found {len(files_to_process)} files to process: {files_to_process}")
            
            for filename in files_to_process:
                self.batch_file(filename)
                
            self.logger.info("Completed processing all files")
        except Exception as e:
            self.logger.error(f"Error in process_all_files: {str(e)}")
            raise

def main():
    batcher = TestCaseBatcher()
    batcher.process_all_files()

if __name__ == '__main__':
    main()