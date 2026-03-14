"""
Check what's actually in the database for Azerbaijani translations
"""
from yonca import create_app
app = create_app()
from yonca.models import ContentTranslation, db

with app.app_context():
    # Get a sample of Azerbaijani translations
    az_translations = ContentTranslation.query.filter_by(target_language='az').limit(20).all()
    
    print("=" * 100)
    print(f"AZERBAIJANI TRANSLATIONS IN DATABASE ({ContentTranslation.query.filter_by(target_language='az').count()} total)")
    print("=" * 100)
    
    for trans in az_translations:
        original = trans.translated_text[:50] + "..." if len(trans.translated_text) > 50 else trans.translated_text
        
        # Try to find the original English text for comparison
        en_trans = ContentTranslation.query.filter_by(
            content_type=trans.content_type,
            content_id=trans.content_id,
            field_name=trans.field_name,
            target_language='en'
        ).first()
        
        source_lang = trans.source_language
        is_same_as_source = False
        
        # If source is English and we have an English translation, compare
        if source_lang == 'en' and en_trans:
            is_same_as_source = trans.translated_text == en_trans.translated_text
        
        status = "⚠️  SAME AS ENGLISH" if is_same_as_source else "✓  Translated"
        
        print(f"\n{status}")
        print(f"  Type: {trans.content_type}:{trans.content_id}.{trans.field_name}")
        print(f"  Source Lang: {source_lang}")
        print(f"  Azeri: {original}")
        
        if en_trans:
            en_text = en_trans.translated_text[:50] + "..." if len(en_trans.translated_text) > 50 else en_trans.translated_text
            print(f"  English: {en_text}")
    
    print("\n" + "=" * 100)
    print("\nNow checking for translations that are exactly the same...")
    print("=" * 100)
    
    # Find translations where Azeri = English
    all_az = ContentTranslation.query.filter_by(target_language='az').all()
    same_count = 0
    
    for trans in all_az:
        en_trans = ContentTranslation.query.filter_by(
            content_type=trans.content_type,
            content_id=trans.content_id,
            field_name=trans.field_name,
            target_language='en'
        ).first()
        
        # Also check the original source text from the actual model
        if trans.content_type == 'course':
            from yonca.models import Course
            course = Course.query.get(trans.content_id)
            if course and hasattr(course, trans.field_name):
                source_text = getattr(course, trans.field_name)
                if trans.translated_text == source_text:
                    same_count += 1
                    print(f"\n⚠️  {trans.content_type}:{trans.content_id}.{trans.field_name}")
                    print(f"   Original: {source_text[:70]}")
                    print(f"   Azeri:    {trans.translated_text[:70]}")
        
        elif trans.content_type == 'resource':
            from yonca.models import Resource
            resource = Resource.query.get(trans.content_id)
            if resource and hasattr(resource, trans.field_name):
                source_text = getattr(resource, trans.field_name)
                if trans.translated_text == source_text:
                    same_count += 1
                    print(f"\n⚠️  {trans.content_type}:{trans.content_id}.{trans.field_name}")
                    print(f"   Original: {source_text[:70]}")
                    print(f"   Azeri:    {trans.translated_text[:70]}")
    
    print("\n" + "=" * 100)
    print(f"SUMMARY: {same_count} out of {len(all_az)} Azeri translations are identical to source")
    print("=" * 100)
