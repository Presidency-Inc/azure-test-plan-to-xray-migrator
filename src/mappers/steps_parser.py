import xml.etree.ElementTree as ET
import html

def get_attached_files(workItem):
    if not isinstance(workItem, dict):
        return []  # Return an empty list if workItem is not a dictionary

    relations = workItem.get("relations")
    if not isinstance(relations, list):
        return []  # Return an empty list if relations are missing or not a list

    attached_files = [relation for relation in relations if isinstance(relation, dict) and relation.get("rel") == "AttachedFile"]
    
    return attached_files

def parse_steps(xml_string):
    if not xml_string:
        return []
        
    try:
        root = ET.fromstring(xml_string)
        steps = []
        
        for step in root.findall("step"):
            parameterized_strings = step.findall("parameterizedString")
            
            # Extract text content from HTML without the HTML tags
            def extract_text(html_string):
                if not html_string:
                    return "--"
                # Create a parser to extract just the text content
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html_string, 'html.parser')
                return soup.get_text().strip() or "--"
            
            # Safely access parameterized_strings elements
            action = "--"
            data = "--"
            result = "--"
            
            if parameterized_strings and len(parameterized_strings) > 0:
                if parameterized_strings[0].text is not None:
                    action = extract_text(html.unescape(parameterized_strings[0].text))
                
                if len(parameterized_strings) > 1 and parameterized_strings[1].text is not None:
                    data = extract_text(html.unescape(parameterized_strings[1].text))
                
                if len(parameterized_strings) > 2 and parameterized_strings[2].text is not None:
                    result = extract_text(html.unescape(parameterized_strings[2].text))
            
            steps.append({
                "action": action,
                "data": data,
                "result": result
            })
        
        return steps
    except ET.ParseError:
        # Handle case where xml_string is not valid XML
        return []
