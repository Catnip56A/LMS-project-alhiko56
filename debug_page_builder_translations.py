#!/usr/bin/env python
"""
Debug script to check if page builder translations exist in the database
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

os.environ['FLASK_ENV'] = 'development'

from yonca import create_app
from yonca.models import ContentTranslation, Course

app = create_app()

with app.app_context():
    # Find courses with page_builder_data
    courses = Course.query.filter(Course.page_builder_data != None).limit(5).all()
    
    print("=" * 80)
    print("PAGE BUILDER TRANSLATION DEBUG")
    print("=" * 80)
    
    if not courses:
        print("❌ No courses with page_builder_data found!")
    else:
        print(f"\n✓ Found {len(courses)} courses with page_builder_data")
        
        for course in courses:
            print(f"\n📚 Course: {course.title} (ID: {course.id})")
            
            if not course.page_builder_data:
                print("  ❌ No page builder data")
                continue
            
            blocks = course.page_builder_data
            print(f"  Blocks: {len(blocks)}")
            
            # Check for translations for this course
            translations = ContentTranslation.query.filter_by(
                content_type='course',
                content_id=course.id
            ).filter(
                ContentTranslation.field_name.startswith('page_builder[')
            ).all()
            
            print(f"  Translations found: {len(translations)}")
            
            if translations:
                print("  Translation entries:")
                for trans in translations:
                    print(f"    - {trans.field_name} -> {trans.target_language}")
                    print(f"      Text: {trans.translated_text[:60]}...")
            else:
                print(f"  ⚠️  No translations found for page builder content!")
                print(f"     Check if auto_translate_page_builder was called after saving")
            
            # Show block details
            print(f"\n  Block details:")
            for i, block in enumerate(blocks):
                block_type = block.get('type', '')
                block_id = block.get('id', '')
                settings = block.get('settings', {})
                
                print(f"    Block {i}: type={block_type}, id={block_id}")
                
                if block_type == 'plain-text':
                    text = settings.get('text', '')
                    print(f"      Text: {text[:60]}...")
                elif block_type == 'hero':
                    title = settings.get('title', '')
                    print(f"      Title: {title[:60]}...")
                elif block_type == 'carousel':
                    items = settings.get('items', [])
                    print(f"      Items: {len(items)}")
    
    print("\n" + "=" * 80)
    print("To fix translations not appearing:")
    print("1. Make sure Flask app is running")
    print("2. Go to admin > Courses > Page Builder")
    print("3. Edit some content and click SAVE")
    print("4. Watch Flask terminal for debug output")
    print("5. Run this script again to verify translations were saved")
    print("=" * 80)
