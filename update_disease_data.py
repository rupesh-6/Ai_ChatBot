"""
Update database with common disease information.

This script adds common disease information to the database to improve
the bot's responses to disease queries.
"""

import os
import pymongo
import datetime
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Common diseases to add to the database
COMMON_DISEASES = [
    "gastroenteritis", "diarrhea", "ulcerative colitis", "crohn's disease",
    "irritable bowel syndrome", "acid reflux", "gerd", "celiac disease",
    "food poisoning", "norovirus", "rotavirus", "e. coli infection"
]

def update_disease_data():
    try:
        # Configure Gemini API
        GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
        if not GEMINI_API_KEY:
            print("Error: GEMINI_API_KEY environment variable not set")
            return False
            
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Connect to MongoDB
        MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/medassist")
        client = pymongo.MongoClient(MONGODB_URI)
        db = client.get_database()
        
        # Create disease_info collection if it doesn't exist
        if "disease_info" not in db.list_collection_names():
            db.create_collection("disease_info")
            print("Created disease_info collection")
        
        disease_collection = db.disease_info
        
        # Create disease_info collection index
        disease_collection.create_index("name", unique=True)
        
        print(f"Updating information for {len(COMMON_DISEASES)} diseases...")
        
        for disease in COMMON_DISEASES:
            # Check if we already have this disease
            existing = disease_collection.find_one({"name": disease})
            if existing:
                print(f"Disease {disease} already exists, skipping...")
                continue
                
            print(f"Fetching information for {disease}...")
            
            # Generate disease information using Gemini
            prompt = f"""
            Please provide accurate, concise information about the disease or condition '{disease}' in this format:
            
            1. What is {disease}?
            2. Common symptoms
            3. How is it transmitted/caused?
            4. Common treatments and medications
            5. Prevention measures
            
            Format the response in clear Markdown with appropriate headers.
            Make your answer concise, medical-grade, and informative.
            """
            
            try:
                response = model.generate_content(prompt)
                
                if response and hasattr(response, 'text'):
                    # Store in database
                    disease_data = {
                        "name": disease,
                        "info": response.text,
                        "last_updated": datetime.datetime.now()
                    }
                    
                    disease_collection.insert_one(disease_data)
                    print(f"Added information for {disease}")
                else:
                    print(f"Error: No response for {disease}")
            except Exception as e:
                print(f"Error generating content for {disease}: {str(e)}")
        
        print("Disease information update completed!")
        return True
        
    except Exception as e:
        print(f"Error updating disease data: {str(e)}")
        return False

if __name__ == "__main__":
    update_disease_data()
