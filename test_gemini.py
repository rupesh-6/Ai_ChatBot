"""
Test script for Gemini API integration.

This script tests if your Gemini API key is working properly 
by making a simple request to the Gemini 2.0 Flash model.

Usage:
    python test_gemini.py

Set your GEMINI_API_KEY environment variable before running:
    export GEMINI_API_KEY=your_api_key_here
"""

import os
import sys
import requests
import json

def test_with_requests():
    """Test Gemini API using direct HTTP requests (curl equivalent)"""
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set")
        print("Please set it with: export GEMINI_API_KEY=your_api_key_here")
        return False
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    data = {
        "contents": [{
            "parts": [{"text": "What are the three most important features of a good medication reminder system?"}]
        }]
    }
    
    print("Testing Gemini API with direct HTTP request...")
    
    try:
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            result = response.json()
            print("\n✅ Gemini API is working properly!")
            print("\nResponse from Gemini:")
            print("-" * 50)
            
            # Extract and print the response text
            if "candidates" in result and len(result["candidates"]) > 0:
                if "content" in result["candidates"][0] and "parts" in result["candidates"][0]["content"]:
                    parts = result["candidates"][0]["content"]["parts"]
                    for part in parts:
                        if "text" in part:
                            print(part["text"])
            return True
        else:
            print(f"\n❌ Error: API request failed with status code {response.status_code}")
            print(f"Response: {response.text}")
            return False
    
    except Exception as e:
        print(f"\n❌ Error making API request: {str(e)}")
        return False

def test_with_google_generativeai():
    """Test Gemini API using the google-generativeai library"""
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set")
        print("Please set it with: export GEMINI_API_KEY=your_api_key_here")
        return False
    
    try:
        import google.generativeai as genai
        
        print("Testing Gemini API with google-generativeai library...")
        
        # Configure the client
        genai.configure(api_key=api_key)
        
        # Test model instantiation
        try:
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            # Test model execution
            response = model.generate_content("What are the three most important features of a good medication reminder system?")
            
            if response:
                print("\n✅ Gemini API is working properly with google-generativeai library!")
                print("\nResponse from Gemini:")
                print("-" * 50)
                print(response.text)
                return True
        except Exception as e:
            print(f"\n❌ Error using gemini-2.0-flash model: {str(e)}")
            print("The model name may be incorrect or not available.")
            return False
            
    except ImportError:
        print("\n❌ Error: google-generativeai package not installed")
        print("Please install it with: pip install google-generativeai")
        return False
    except Exception as e:
        print(f"\n❌ Error setting up google-generativeai: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("GEMINI API TESTER")
    print("=" * 60)
    
    # Try both methods
    result1 = test_with_requests()
    print("\n" + "=" * 60 + "\n")
    result2 = test_with_google_generativeai()
    
    print("\n" + "=" * 60)
    if result1 or result2:
        print("\n✅ At least one test method worked. Your API key is valid.")
        print("You may need to check your model name if one method failed.")
    else:
        print("\n❌ All test methods failed. Please check your API key and connection.")
    print("=" * 60)
