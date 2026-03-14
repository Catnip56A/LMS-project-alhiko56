"""
Clear ALL translation caches and check what's there
"""
from yonca import create_app
app = create_app()
from yonca.models import Translation, ContentTranslation, db

with app.app_context():
    print("=" * 100)
    
    # Check Translation cache table
    az_cached = Translation.query.filter_by(target_language='az').all()
    print(f"Translation cache (az): {len(az_cached)} entries")
    
    # Show some examples
    for trans in az_cached[:5]:
        print(f"  Source: {trans.source_text[:50]}")
        print(f"  Target: {trans.translated_text[:50]}")
        print(f"  Same? {trans.source_text == trans.translated_text}")
        print()
    
    # Check ContentTranslation table
    az_content = ContentTranslation.query.filter_by(target_language='az').all()
    print(f"ContentTranslation (az): {len(az_content)} entries")
    
    print("\n" + "=" * 100)
    print("CLEARING ALL AZERBAIJANI CACHES...")
    print("=" * 100)
    
    # Delete from both tables
    for trans in az_cached:
        db.session.delete(trans)
    
    for trans in az_content:
        db.session.delete(trans)
    
    db.session.commit()
    
    print(f"Deleted {len(az_cached)} from Translation cache")
    print(f"Deleted {len(az_content)} from ContentTranslation")
    print("\nNow re-run the translation from the admin panel!")
