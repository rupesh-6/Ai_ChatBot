"""
Populate disease information in the database.

This script adds information about common diseases to the MongoDB database
to ensure the chatbot has reliable information to provide to users.
"""

import os
import pymongo
import google.generativeai as genai
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# List of common diseases to populate
DISEASES = [
    "gastroenteritis", "diarrhea", "flu", "common cold", "diabetes", 
    "hypertension", "asthma", "malaria", "dengue", "covid"
]

def populate_disease_data():
    # Get MongoDB URI from environment or use default
    mongodb_uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/medassist")
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set")
        return False
        
    try:
        # Configure Gemini API
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Connect to MongoDB
        client = pymongo.MongoClient(mongodb_uri)
        db = client.get_database()
        
        # Create disease_info collection if it doesn't exist
        if "disease_info" not in db.list_collection_names():
            db.create_collection("disease_info")
            print("Created disease_info collection")
        
        disease_collection = db.disease_info
        
        # Create index on name field if not exists
        disease_collection.create_index("name", unique=True)
        
        success_count = 0
        failure_count = 0
        
        # Process each disease
        for disease in DISEASES:
            print(f"Processing {disease}...")
            
            # Check if disease already exists in database
            existing = disease_collection.find_one({"name": disease.lower()})
            if existing:
                print(f"- {disease} already exists in database, skipping")
                continue
            
            # Create prompt for Gemini
            prompt = f"""
            Please provide accurate, concise information about the disease or condition '{disease}' in this format:
            
            1. What is {disease}?
            2. Common symptoms
            3. How is it transmitted/caused?
            4. Common treatments and medications
            5. Prevention measures
            
            Format the response in clear Markdown with appropriate headers.
            Make your answer concise but informative.
            """
            
            try:
                # Get response from Gemini
                response = model.generate_content(prompt)
                
                if response and hasattr(response, 'text'):
                    # Store disease information in database
                    disease_info = {
                        "name": disease.lower(),
                        "info": response.text,
                        "created_at": datetime.now(),
                        "source": "gemini"
                    }
                    
                    result = disease_collection.insert_one(disease_info)
                    
                    if result.inserted_id:
                        print(f"✅ Successfully added information for {disease}")
                        success_count += 1
                    else:
                        print(f"❌ Failed to add information for {disease}")
                        failure_count += 1
                else:
                    print(f"❌ Empty or invalid response for {disease}")
                    failure_count += 1
            except Exception as e:
                print(f"❌ Error processing {disease}: {str(e)}")
                failure_count += 1
        
        print(f"\nPopulation complete! Added {success_count} diseases, {failure_count} failures")
        return True
    
    except Exception as e:
        print(f"Error in disease population process: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("DISEASE INFORMATION DATABASE POPULATION")
    print("=" * 60)
    populate_disease_data()
