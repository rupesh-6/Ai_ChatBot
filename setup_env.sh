#!/bin/bash

# Script to set up environment variables for MedAssist

echo "MedAssist Environment Setup"
echo "=========================="

# Check if GEMINI_API_KEY is set
if [ -z "$GEMINI_API_KEY" ]; then
  echo "GEMINI_API_KEY is not set."
  read -p "Enter your Gemini API key: " gemini_key
  export GEMINI_API_KEY="$gemini_key"
  echo "export GEMINI_API_KEY='$gemini_key'" >> ~/.bashrc
  echo "GEMINI_API_KEY has been set for this session and added to your ~/.bashrc"
  echo "You may need to run 'source ~/.bashrc' to apply the changes in new terminals."
else
  echo "GEMINI_API_KEY is already set."
fi

# Check if MONGODB_URI is set
if [ -z "$MONGODB_URI" ]; then
  echo "MONGODB_URI is not set. Using default: mongodb://localhost:27017/medassist"
  export MONGODB_URI="mongodb://localhost:27017/medassist"
  echo "export MONGODB_URI='mongodb://localhost:27017/medassist'" >> ~/.bashrc
else
  echo "MONGODB_URI is already set to: $MONGODB_URI"
fi

# Check if FLASK_SECRET_KEY is set
if [ -z "$FLASK_SECRET_KEY" ]; then
  # Generate a random secret key
  secret_key=$(python -c "import secrets; print(secrets.token_hex(16))")
  export FLASK_SECRET_KEY="$secret_key"
  echo "export FLASK_SECRET_KEY='$secret_key'" >> ~/.bashrc
  echo "FLASK_SECRET_KEY has been set to a random value for this session and added to your ~/.bashrc"
else
  echo "FLASK_SECRET_KEY is already set."
fi

echo "Environment setup complete."
echo "To set up the MongoDB database, run: python db_setup.py"
echo "To start the application, run: python app.py"
