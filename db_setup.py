"""
MongoDB Setup Utility for MedAssist

This script initializes the MongoDB database and collections for MedAssist.
It's meant to be run once to set up the database structure.
"""

import pymongo
import os
from datetime import datetime
from werkzeug.security import generate_password_hash

def setup_database():
    # Get MongoDB URI from environment or use default
    mongodb_uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/medassist")
    
    try:
        # Connect to MongoDB
        client = pymongo.MongoClient(mongodb_uri)
        
        # Access database
        db = client.get_database()
        
        print(f"Connected to MongoDB ({db.name})")
        
        # Create collections with validation schemas
        
        # Users collection
        if "users" not in db.list_collection_names():
            db.create_collection("users", validator={
                "$jsonSchema": {
                    "bsonType": "object",
                    "required": ["email", "password_hash", "created_at"],
                    "properties": {
                        "email": {
                            "bsonType": "string",
                            "description": "User's email (used as username)"
                        },
                        "password_hash": {
                            "bsonType": "string",
                            "description": "Hashed password"
                        },
                        "name": {
                            "bsonType": "string",
                            "description": "User's name"
                        },
                        "user_id": {
                            "bsonType": "string",
                            "description": "Unique identifier for the user"
                        },
                        "created_at": {
                            "bsonType": "date",
                            "description": "The date user was created"
                        },
                        "age": {
                            "bsonType": ["string", "int", "null"],
                            "description": "User's age"
                        },
                        "conditions": {
                            "bsonType": ["array", "null"],
                            "description": "User's health conditions"
                        },
                        "custom_condition": {
                            "bsonType": ["string", "null"],
                            "description": "User's custom health condition"
                        },
                        "preferred_reminder_time": {
                            "bsonType": ["string", "null"],
                            "description": "User's preferred time for reminders"
                        },
                        "last_login": {
                            "bsonType": ["date", "null"],
                            "description": "Last login timestamp"
                        }
                    }
                }
            })
            print("Created users collection")
            
            # Create indexes
            db.users.create_index("email", unique=True)
            db.users.create_index("user_id", unique=True)
            print("Created indexes on users collection")
            
            # Create a default admin user
            default_admin = {
                "email": "admin@medassist.com",
                "password_hash": generate_password_hash("admin123"),
                "name": "Admin",
                "user_id": "admin_" + str(int(datetime.now().timestamp())),
                "created_at": datetime.now(),
                "conditions": [],
                "preferred_reminder_time": "08:00"
            }
            db.users.insert_one(default_admin)
            print("Created default admin user (admin@medassist.com / admin123)")
        
        # Medications collection
        if "medications" not in db.list_collection_names():
            db.create_collection("medications", validator={
                "$jsonSchema": {
                    "bsonType": "object",
                    "required": ["user_id", "name"],
                    "properties": {
                        "user_id": {
                            "bsonType": "string",
                            "description": "User ID this medication belongs to"
                        },
                        "name": {
                            "bsonType": "string",
                            "description": "Name of the medication"
                        },
                        "info": {
                            "bsonType": ["string", "null"],
                            "description": "Information about the medication"
                        },
                        "time": {
                            "bsonType": ["string", "null"],
                            "description": "Time for the daily reminder"
                        },
                        "condition": {
                            "bsonType": ["string", "null"],
                            "description": "Condition this medication is for"
                        },
                        "created_at": {
                            "bsonType": "date",
                            "description": "When this medication was added"
                        },
                        "last_taken": {
                            "bsonType": ["date", "null"],
                            "description": "When this medication was last taken"
                        }
                    }
                }
            })
            print("Created medications collection")
            
            # Create indexes
            db.medications.create_index([("user_id", 1), ("name", 1)], unique=True)
            print("Created index on medications collection")
        
        # Chat history collection
        if "chat_history" not in db.list_collection_names():
            db.create_collection("chat_history", validator={
                "$jsonSchema": {
                    "bsonType": "object",
                    "required": ["user_id", "role", "content", "timestamp"],
                    "properties": {
                        "user_id": {
                            "bsonType": "string",
                            "description": "User ID this chat message belongs to"
                        },
                        "role": {
                            "bsonType": "string",
                            "description": "Role (user or bot)"
                        },
                        "content": {
                            "bsonType": "string",
                            "description": "Message content"
                        },
                        "timestamp": {
                            "bsonType": "date",
                            "description": "When this message was sent"
                        }
                    }
                }
            })
            print("Created chat_history collection")
            
            # Create indexes
            db.chat_history.create_index("user_id")
            db.chat_history.create_index("timestamp")
            print("Created indexes on chat_history collection")
        
        # Sessions collection
        if "sessions" not in db.list_collection_names():
            db.create_collection("sessions")
            print("Created sessions collection")
            
            # Create indexes
            db.sessions.create_index("user_id")
            db.sessions.create_index("expiry")  # For session expiration
            print("Created indexes on sessions collection")
        
        print("\nDatabase setup completed successfully!")
        return True
    
    except Exception as e:
        print(f"Error setting up database: {str(e)}")
        return False

if __name__ == "__main__":
    setup_database()
