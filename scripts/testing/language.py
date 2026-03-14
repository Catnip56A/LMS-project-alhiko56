#!/usr/bin/env python3
"""Test language switching"""
import requests

# Test initial load
print("1. Testing initial page load...")
session = requests.Session()
response = session.get('http://127.0.0.1:5000/')
print(f"   Status: {response.status_code}")
print(f"   Cookies: {session.cookies.get_dict()}")

# Check for language button
if 'English' in response.text:
    print("   ✓ Found 'English' in page")
elif 'Azeri' in response.text:
    print("   ✓ Found 'Azeri' in page")
elif 'Russian' in response.text:
    print("   ✓ Found 'Russian' in page")
else:
    print("   ✗ No language button found")

# Test switching to Azerbaijani
print("\n2. Switching to Azerbaijani...")
response = session.get('http://127.0.0.1:5000/set_language/az', allow_redirects=True)
print(f"   Status: {response.status_code}")
print(f"   Cookies: {session.cookies.get_dict()}")
print(f"   Final URL: {response.url}")

# Check button changed
if 'Azeri' in response.text:
    print("   ✓ Button shows 'Azeri'")
elif 'English' in response.text:
    print("   ✗ Button still shows 'English'")

# Check if content exists
if 'Home' in response.text or 'Ana' in response.text:
    print("   ✓ Content visible")
else:
    print("   ✗ Content missing")

# Test switching to Russian
print("\n3. Switching to Russian...")
response = session.get('http://127.0.0.1:5000/set_language/ru', allow_redirects=True)
print(f"   Status: {response.status_code}")

if 'Russian' in response.text:
    print("   ✓ Button shows 'Russian'")
elif 'Azeri' in response.text:
    print("   ✗ Button still shows 'Azeri'")

# Check for Russian content
if 'Дом' in response.text or 'Курсы' in response.text:
    print("   ✓ Russian content visible!")
else:
    print("   ✗ Russian content missing")

# Test switching back to English
print("\n4. Switching to English...")
response = session.get('http://127.0.0.1:5000/set_language/en', allow_redirects=True)
print(f"   Status: {response.status_code}")

if 'English' in response.text:
    print("   ✓ Button shows 'English'")
elif 'Russian' in response.text:
    print("   ✗ Button still shows 'Russian'")

if 'Home' in response.text and 'Courses' in response.text:
    print("   ✓ English content visible")
else:
    print("   ✗ English content missing")
