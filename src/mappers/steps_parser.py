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
            
            # Extract text content from HTML with proper line breaks for block elements
            def extract_text(html_string):
                if not html_string:
                    return "--"
                # Create a parser to extract the text content with proper formatting
                from bs4 import BeautifulSoup, NavigableString
                import re
                
                soup = BeautifulSoup(html_string, 'html.parser')
                
                # Function to handle block elements and add line breaks
                def process_element(element):
                    texts = []
                    for child in element.children:
                        if isinstance(child, NavigableString):
                            text = child.strip()
                            if text:
                                texts.append(text)
                        else:
                            # Add line breaks before block elements
                            if child.name in ['p', 'ul', 'ol', 'li', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                                if texts and not texts[-1].endswith('\n'):
                                    texts.append('\n')
                            
                            # Process the child element
                            child_text = process_element(child)
                            if child_text:
                                texts.append(child_text)
                            
                            # Add line breaks after block elements
                            if child.name in ['p', 'ul', 'ol', 'li', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br']:
                                texts.append('\n')
                    
                    return ' '.join(texts)
                
                # Process the entire soup
                result = process_element(soup)
                
                # Clean up excessive whitespace and line breaks
                result = re.sub(r'\s*\n\s*', '\n', result)
                result = re.sub(r'\n{3,}', '\n\n', result)
                
                return result.strip() or "--"
            
            # Safely access parameterized_strings elements
            action = "--"
            result = "--"
            
            if parameterized_strings and len(parameterized_strings) > 0:
                if parameterized_strings[0].text is not None:
                    action = extract_text(html.unescape(parameterized_strings[0].text))
                
                if len(parameterized_strings) > 1 and parameterized_strings[1].text is not None:
                    result = extract_text(html.unescape(parameterized_strings[1].text))
                            
            steps.append({
                "action": action,
                "result": result
            })
        
        return steps
    except ET.ParseError:
        # Handle case where xml_string is not valid XML
        return []
