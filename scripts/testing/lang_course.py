from yonca import create_app
app = create_app()

with app.test_client() as client:
    # First, set language to Azerbaijani
    print('Setting language to Azerbaijani...')
    response = client.get('/set_language/az', follow_redirects=True)
    print(f'Response status: {response.status_code}')

    # Check if session has the language
    with client.session_transaction() as sess:
        print(f'Session language: {sess.get("language")}')

    # Now try to access a course page
    print('Accessing course page...')
    response2 = client.get('/course/1', follow_redirects=True)
    print(f'Course page response status: {response2.status_code}')

    # Check if the response contains translated content
    content = response2.get_data(as_text=True)
    if 'yeni' in content or 'Yonca-a' in content:
        print('✅ Found Azerbaijani translations in course page!')
    else:
        print('❌ No Azerbaijani translations found in course page')
        # Look for course title in content
        if 'translate_field' in content:
            print('Translation helpers found in template')