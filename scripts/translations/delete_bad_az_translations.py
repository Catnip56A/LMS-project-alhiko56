"""
Delete all Azerbaijani translations that are identical to English source
"""
from yonca import create_app
app = create_app()
from yonca.models import ContentTranslation, Course, Resource, db

with app.app_context():
    print("=" * 100)
    print("DELETING BAD AZERBAIJANI TRANSLATIONS")
    print("=" * 100)
    
    # Get all Azeri translations
    all_az = ContentTranslation.query.filter_by(target_language='az').all()
    deleted_count = 0
    
    for trans in all_az:
        source_text = None
        
        # Get the original source text from the actual model
        if trans.content_type == 'course':
            course = db.session.get(Course, trans.content_id)
            if course and hasattr(course, trans.field_name):
                source_text = getattr(course, trans.field_name)
        
        elif trans.content_type == 'resource':
            resource = db.session.get(Resource, trans.content_id)
            if resource and hasattr(resource, trans.field_name):
                source_text = getattr(resource, trans.field_name)
        
        # If translation is identical to source, delete it
        if source_text and trans.translated_text == source_text:
            deleted_count += 1
            print(f"Deleting: {trans.content_type}:{trans.content_id}.{trans.field_name}")
            print(f"  Text: {trans.translated_text[:70]}")
            db.session.delete(trans)
    
    # Also delete all cached translations in Translation table for Azeri
    from yonca.models import Translation
    cached_az = Translation.query.filter_by(target_language='az').all()
    cached_deleted = len(cached_az)
    
    for trans in cached_az:
        db.session.delete(trans)
    
    db.session.commit()
    
    print("\n" + "=" * 100)
    print(f"SUMMARY: Deleted {deleted_count} bad ContentTranslations and {cached_deleted} cached Translations")
    print("=" * 100)
