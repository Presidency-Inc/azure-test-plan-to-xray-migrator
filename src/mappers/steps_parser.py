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
    root = ET.fromstring(xml_string)
    steps = []
    
    for step in root.findall("step"):
        parameterized_strings = step.findall("parameterizedString")
        
        # Extract text content from HTML without the HTML tags
        def extract_text(html_string):
            if not html_string:
                return ""
            # Create a parser to extract just the text content
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_string, 'html.parser')
            return soup.get_text().strip()
        
        action = extract_text(html.unescape(parameterized_strings[0].text)) if len(parameterized_strings) > 0 else ""
        data = extract_text(html.unescape(parameterized_strings[1].text)) if len(parameterized_strings) > 1 else ""
        result = extract_text(html.unescape(parameterized_strings[2].text)) if len(parameterized_strings) > 2 else ""
        
        steps.append({
            "action": action,
            "data": data,
            "result": result
        })
    
    return steps
