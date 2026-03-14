"""
Test script to verify translation display in different languages
"""
from yonca import create_app, db
from yonca.models import Course, Resource, HomeContent, ContentTranslation
from yonca.content_translator import get_translated_content

app = create_app()

with app.app_context():
    print("=" * 80)
    print("TRANSLATION SYSTEM TEST")
    print("=" * 80)
    
    # Test 1: Check if translations exist in database
    print("\n1. Checking translation database...")
    translation_count = ContentTranslation.query.count()
    print(f"   Total translations in database: {translation_count}")
    
    if translation_count > 0:
        # Group by content type
        for content_type in ['course', 'resource', 'home_content', 'course_content', 'course_content_folder']:
            count = ContentTranslation.query.filter_by(content_type=content_type).count()
            if count > 0:
                print(f"   - {content_type}: {count} translations")
    
    # Test 2: Test course translation
    print("\n2. Testing course translations...")
    course = Course.query.first()
    if course:
        print(f"   Course: {course.title}")
        print(f"   English title: {course.title}")
        
        az_title = get_translated_content('course', course.id, 'title', course.title, 'az')
        ru_title = get_translated_content('course', course.id, 'title', course.title, 'ru')
        
        print(f"   Azerbaijani title: {az_title}")
        print(f"   Russian title: {ru_title}")
        
        if az_title != course.title:
            print("   ✓ Azerbaijani translation working!")
        else:
            print("   ✗ Azerbaijani translation not found (showing English)")
            
        if ru_title != course.title:
            print("   ✓ Russian translation working!")
        else:
            print("   ✗ Russian translation not found (showing English)")
    else:
        print("   No courses found in database")
    
    # Test 3: Test resource translation
    print("\n3. Testing resource translations...")
    resource = Resource.query.first()
    if resource:
        print(f"   Resource: {resource.title}")
        print(f"   English title: {resource.title}")
        
        az_title = get_translated_content('resource', resource.id, 'title', resource.title, 'az')
        ru_title = get_translated_content('resource', resource.id, 'title', resource.title, 'ru')
        
        print(f"   Azerbaijani title: {az_title}")
        print(f"   Russian title: {ru_title}")
        
        if az_title != resource.title:
            print("   ✓ Azerbaijani translation working!")
        else:
            print("   ✗ Azerbaijani translation not found (showing English)")
            
        if ru_title != resource.title:
            print("   ✓ Russian translation working!")
        else:
            print("   ✗ Russian translation not found (showing English)")
    else:
        print("   No resources found in database")
    
    # Test 4: Test home content translation
    print("\n4. Testing home content translations...")
    home = HomeContent.query.filter_by(is_active=True).first()
    if home:
        print(f"   Home content ID: {home.id}")
        
        if home.welcome_title:
            print(f"   English welcome: {home.welcome_title}")
            
            az_welcome = get_translated_content('home_content', home.id, 'welcome_title', home.welcome_title, 'az')
            ru_welcome = get_translated_content('home_content', home.id, 'welcome_title', home.welcome_title, 'ru')
            
            print(f"   Azerbaijani welcome: {az_welcome}")
            print(f"   Russian welcome: {ru_welcome}")
            
            if az_welcome != home.welcome_title:
                print("   ✓ Azerbaijani translation working!")
            else:
                print("   ✗ Azerbaijani translation not found (showing English)")
                
            if ru_welcome != home.welcome_title:
                print("   ✓ Russian translation working!")
            else:
                print("   ✗ Russian translation not found (showing English)")
    else:
        print("   No home content found in database")
    
    # Test 5: Show sample translations
    print("\n5. Sample translations from database:")
    sample_translations = ContentTranslation.query.limit(5).all()
    for trans in sample_translations:
        print(f"   - {trans.content_type} #{trans.content_id}, field '{trans.field_name}' -> {trans.target_language}")
        print(f"     Original: {trans.translated_text[:50]}..." if len(trans.translated_text) > 50 else f"     Translation: {trans.translated_text}")
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)
    print("\nTo test in browser:")
    print("1. Go to http://localhost:5000")
    print("2. Click the language dropdown in the top-right")
    print("3. Select 'Azərbaycanca' or 'Русский'")
    print("4. Content should display in the selected language")
    print("=" * 80)
