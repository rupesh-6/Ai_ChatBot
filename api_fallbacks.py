"""
API fallback module for MedAssist.

This module provides backup API methods for retrieving medical information
when the primary methods fail.
"""

import os
import json
import requests
import re
from dotenv import load_dotenv

load_dotenv()

class FallbackAPI:
    """Class to handle alternative API methods for retrieving medical information"""
    
    @staticmethod
    def get_disease_info(disease_name):
        """
        Try alternative APIs to get disease information.
        Returns (info_text, success_bool)
        """
        # Try multiple methods in sequence until one works
        
        # Try Wikipedia API first (good for general disease information)
        wiki_info = FallbackAPI._try_wikipedia_api(disease_name)
        if wiki_info:
            return wiki_info, True
            
        # Try Health.gov API
        health_gov_info = FallbackAPI._try_health_gov_api(disease_name)
        if health_gov_info:
            return health_gov_info, True
        
        # Return failure if all methods fail
        return None, False
    
    @staticmethod
    def _try_wikipedia_api(disease_name):
        """Try to get information from Wikipedia API"""
        try:
            # Clean the disease name for the API
            clean_term = disease_name.strip().lower().replace(" ", "_")
            
            # First get the proper page title
            url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={clean_term}&format=json"
            response = requests.get(url, timeout=5)
            data = response.json()
            
            if "query" in data and "search" in data["query"] and len(data["query"]["search"]) > 0:
                # Get the proper page title
                page_title = data["query"]["search"][0]["title"]
                
                # Now get the page extract
                extract_url = f"https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exintro&titles={page_title}&format=json&explaintext=1"
                extract_response = requests.get(extract_url, timeout=5)
                extract_data = extract_response.json()
                
                # Extract the page content
                if "query" in extract_data and "pages" in extract_data["query"]:
                    pages = extract_data["query"]["pages"]
                    page_id = next(iter(pages))
                    if "extract" in pages[page_id]:
                        extract = pages[page_id]["extract"]
                        
                        # Format as markdown
                        formatted_info = f"""## Information About {disease_name.title()}

### What is {disease_name.title()}?
{extract[:300]}...

### Source
This information is based on general medical knowledge. For more detailed or personalized information, please consult with a healthcare professional.

*Would you like to set a reminder for any medications related to this condition? Please specify which medication.*
"""
                        return formatted_info
            
            return None
        except Exception as e:
            print(f"Wikipedia API error: {str(e)}")
            return None
    
    @staticmethod
    def _try_health_gov_api(disease_name):
        """Try to get information from Health.gov API"""
        try:
            # Use Health.gov API to search for content
            url = f"https://health.gov/myhealthfinder/api/v3/topicsearch.json?keyword={disease_name}"
            response = requests.get(url, timeout=5)
            data = response.json()
            
            if "Result" in data and "Resources" in data["Result"] and "Resource" in data["Result"]["Resources"]:
                resources = data["Result"]["Resources"]["Resource"]
                if len(resources) > 0:
                    resource = resources[0]
                    title = resource.get("Title", "")
                    sections = resource.get("Sections", {}).get("Section", [])
                    
                    if sections:
                        content = ""
                        for section in sections:
                            if "Content" in section:
                                content += section["Content"] + "\n\n"
                        
                        # Clean HTML tags
                        content = re.sub(r'<[^>]+>', '', content)
                        
                        # Format as markdown
                        formatted_info = f"""## Information About {disease_name.title()}

### {title}
{content[:500]}...

### Source
This information is from Health.gov. For more detailed or personalized information, please consult with a healthcare professional.

*Would you like to set a reminder for any medications related to this condition? Please specify which medication.*
"""
                        return formatted_info
            
            return None
        except Exception as e:
            print(f"Health.gov API error: {str(e)}")
            return None

# Basic lookup of common conditions as backup method
COMMON_DISEASES = {
    "gastroenteritis": """## Information About Gastroenteritis

### What is Gastroenteritis?
Gastroenteritis is an inflammation of the lining of the intestines caused by a virus, bacteria, or parasites. It's commonly known as the stomach flu.

### Common Symptoms
- Watery diarrhea
- Abdominal cramps and pain
- Nausea, vomiting
- Occasional fever
- Headache and muscle aches

### How is it Transmitted/Caused?
- Viral infection (most common)
- Bacterial infection from contaminated food or water
- Parasites
- Medication side effects
- Food allergies

### Common Treatments
- Rest and hydration
- Oral rehydration solutions
- Anti-diarrheal medications (in some cases)
- Antibiotics (only for certain bacterial infections)
- Probiotics may help recovery

### Prevention Measures
- Frequent handwashing
- Safe food handling and preparation
- Avoiding close contact with infected individuals
- Drinking clean, safe water
- Getting rotavirus vaccine (for infants)

*Would you like to set a reminder for any medications related to this condition? Please specify which medication.*""",

    # Add more common diseases as needed
}

def get_backup_disease_info(disease_name):
    """Get disease information from backup static data"""
    disease_lower = disease_name.lower()
    return COMMON_DISEASES.get(disease_lower)
