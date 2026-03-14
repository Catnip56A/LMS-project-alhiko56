#!/usr/bin/env python3
"""Test session and locale"""
from yonca import create_app
from flask import session

app = create_app()

with app.test_client() as client:
    with client.session_transaction() as sess:
        print(f"1. Initial session: {dict(sess)}")
    
    # Load homepage
    print("\n2. Loading homepage...")
    resp = client.get('/')
    print(f"   Status: {resp.status_code}")
    with client.session_transaction() as sess:
        print(f"   Session after load: {dict(sess)}")
    
    # Switch to Azeri
    print("\n3. Switching to Azeri...")
    resp = client.get('/set_language/az', follow_redirects=True)
    print(f"   Status: {resp.status_code}")
    print(f"   Final URL: {resp.request.path}")
    with client.session_transaction() as sess:
        print(f"   Session after switch: {dict(sess)}")
        print(f"   Language in session: {sess.get('language')}")
    
    # Check if button changed
    html = resp.data.decode('utf-8')
    if 'Azeri' in html:
        print("   ✓ Button shows 'Azeri'")
    elif 'English' in html:
        print("   ✗ Button still shows 'English'")
        # Check what current_locale value is
        import re
        match = re.search(r'/set_language/(\w+)">', html)
        if match:
            print(f"   Button links to: /set_language/{match.group(1)}")
    
    # Load page again to see if session persists
    print("\n4. Loading homepage again...")
    resp = client.get('/')
    with client.session_transaction() as sess:
        print(f"   Session: {dict(sess)}")
    
    html = resp.data.decode('utf-8')
    if 'Azeri' in html:
        print("   ✓ Button still shows 'Azeri' (session persisted)")
    elif 'English' in html:
        print("   ✗ Button reverted to 'English' (session lost)")
