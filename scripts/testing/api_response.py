"""
Test the API endpoint to see what it returns
"""
import requests

# Test without session (should default to English)
response = requests.get('http://127.0.0.1:5000/api/courses')
courses = response.json()

print("=" * 100)
print("API RESPONSE - Course Titles (without session)")
print("=" * 100)
for course in courses[:3]:
    print(f"ID {course['id']}: {course['title']}")

print("\n" + "=" * 100)
print("EXPLANATION:")
print("=" * 100)
print("The API returns course titles based on the user's session locale.")
print("If you're logged in, the system should use your selected language.")
print("\nTo see Azerbaijani, you need to:")
print("1. Be logged in")
print("2. Have 'az' selected as your language")
print("3. The session must pass the locale to the API")
print("\nThe issue is likely that the API isn't reading your session locale correctly.")
