"""
Check if about company translations exist
"""
from yonca import create_app
app = create_app()
from yonca.models import ContentTranslation, HomeContent, db

with app.app_context():
    home_content = HomeContent.query.filter_by(is_active=True).first()
    if not home_content:
        print("No active home content found!")
        exit(1)
    
    print("=" * 100)
    print(f"ABOUT COMPANY TRANSLATIONS FOR HOME_CONTENT ID {home_content.id}")
    print("=" * 100)
    
    about_fields = [
        'about_welcome_title', 'about_subtitle',
        'about_features_title', 'about_features_subtitle',
        'about_gallery_title', 'about_gallery_subtitle'
    ]
    
    for field in about_fields:
        az_trans = ContentTranslation.query.filter_by(
            content_type='home_content',
            content_id=home_content.id,
            field_name=field,
            target_language='az'
        ).first()
        
        ru_trans = ContentTranslation.query.filter_by(
            content_type='home_content',
            content_id=home_content.id,
            field_name=field,
            target_language='ru'
        ).first()
        
        original = getattr(home_content, field, 'NOT FOUND')
        
        print(f"\n{field}:")
        print(f"  Original: {original}")
        print(f"  Azeri:    {az_trans.translated_text if az_trans else 'NOT FOUND'}")
        print(f"  Russian:  {ru_trans.translated_text if ru_trans else 'NOT FOUND'}")
    
    # Check about_features JSON array
    print("about_features JSON array:")
    about_features = getattr(home_content, 'about_features', [])
    if about_features:
        for i, feature in enumerate(about_features):
            print(f"  Feature {i}: {feature}")
            
            # Check translations for title and description
            title_az = ContentTranslation.query.filter_by(
                content_type='home_content',
                content_id=home_content.id,
                field_name=f'about_features[{i}].title',
                target_language='az'
            ).first()
            
            desc_az = ContentTranslation.query.filter_by(
                content_type='home_content',
                content_id=home_content.id,
                field_name=f'about_features[{i}].description',
                target_language='az'
            ).first()
            
            print(f"    Title AZ: {title_az.translated_text if title_az else 'NOT FOUND'}")
            print(f"    Desc AZ:  {desc_az.translated_text if desc_az else 'NOT FOUND'}")
    
    print("\n" + "=" * 100)