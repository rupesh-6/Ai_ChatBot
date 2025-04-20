"""
Utility script to fix issues with existing chat history in the database.

This script:
1. Removes duplicate messages
2. Fixes personalization issues in bot messages
3. Updates chat session context for better conversation flow
"""

import pymongo
import os
import re
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def fix_chat_history():
    # Get MongoDB URI from environment or use default
    mongodb_uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/medassist")
    
    try:
        # Connect to MongoDB
        client = pymongo.MongoClient(mongodb_uri)
        
        # Access database
        db = client.get_database()
        
        # Get collections
        chat_history_collection = db.chat_history
        sessions_collection = db.sessions
        users_collection = db.users
        
        print(f"Connected to MongoDB ({db.name})")
        print("Fixing chat history issues...")
        
        # Get all users
        users = list(users_collection.find({}))
        
        for user in users:
            user_id = user["user_id"]
            user_name = user.get("name", "")
            
            print(f"\nProcessing user: {user_name} (ID: {user_id})")
            
            # Get chat history for this user
            chat_history = list(chat_history_collection.find({"user_id": user_id}).sort("timestamp", 1))
            
            if not chat_history:
                print(f"  No chat history found for user {user_id}")
                continue
                
            print(f"  Found {len(chat_history)} chat messages")
            
            # Fix personalization issues in bot messages
            fixed_count = 0
            personalization_pattern = re.compile(r'\b(?:Avinash|user_name)\b')
            
            for message in chat_history:
                if message["role"] == "bot":
                    content = message["content"]
                    if personalization_pattern.search(content):
                        # Fix the content by replacing the personalized references with "you"
                        fixed_content = personalization_pattern.sub("you", content)
                        
                        # Update the message in the database
                        chat_history_collection.update_one(
                            {"_id": message["_id"]},
                            {"$set": {"content": fixed_content}}
                        )
                        fixed_count += 1
            
            if fixed_count > 0:
                print(f"  Fixed personalization issues in {fixed_count} bot messages")
            
            # Reset session context to ensure a fresh start
            sessions_collection.update_one(
                {"user_id": user_id},
                {"$set": {
                    "step": 1,
                    "context": {},
                    "last_updated": datetime.now()
                }},
                upsert=True
            )
            print(f"  Reset session context for user {user_id}")
            
        print("\nChat history fix completed successfully!")
        return True
    
    except Exception as e:
        print(f"Error fixing chat history: {str(e)}")
        return False

if __name__ == "__main__":
    fix_chat_history()
