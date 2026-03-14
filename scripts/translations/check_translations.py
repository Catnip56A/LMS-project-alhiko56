from yonca import create_app, db
from yonca.models import ContentTranslation

app = create_app()
with app.app_context():
    count = ContentTranslation.query.count()
    print(f'Total translations in database: {count}')
    
    if count == 0:
        print("\n❌ NO TRANSLATIONS FOUND!")
        print("\nYou need to run translation first:")
        print("1. Go to http://localhost:5000/admin")
        print("2. Click the green '🌐 Translate Content' button")
        print("3. Wait for it to complete")
        print("\nOR run manually:")
        print("  python translate_all_content.py")
    else:
        print(f'\n✓ Courses: {ContentTranslation.query.filter_by(content_type="course").count()}')
        print(f'✓ Resources: {ContentTranslation.query.filter_by(content_type="resource").count()}')
        print(f'✓ Home content: {ContentTranslation.query.filter_by(content_type="home_content").count()}')
        print(f'✓ Course content: {ContentTranslation.query.filter_by(content_type="course_content").count()}')
        print(f'✓ Folders: {ContentTranslation.query.filter_by(content_type="course_content_folder").count()}')
