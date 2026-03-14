"""
Test translation quality - check if GoogleTranslator is actually translating
"""
from deep_translator import GoogleTranslator

# Test some sample English phrases
test_phrases = [
    "Welcome to Yonca",
    "Learning Platform",
    "Interactive Courses",
    "Course Description",
    "Resources",
    "Hello World",
    "This is a test",
    "Machine Learning Course"
]

print("=" * 80)
print("TESTING GOOGLE TRANSLATOR TO AZERBAIJANI")
print("=" * 80)

translator_az = GoogleTranslator(source='en', target='az')
translator_ru = GoogleTranslator(source='en', target='ru')

print("\nEnglish → Azerbaijani:")
print("-" * 80)
for phrase in test_phrases:
    try:
        translated = translator_az.translate(phrase)
        is_same = translated == phrase
        status = "❌ SAME" if is_same else "✓ Translated"
        print(f"{status} | EN: {phrase:30} → AZ: {translated}")
    except Exception as e:
        print(f"ERROR | EN: {phrase:30} → Error: {e}")

print("\n" + "=" * 80)
print("English → Russian:")
print("-" * 80)
for phrase in test_phrases:
    try:
        translated = translator_ru.translate(phrase)
        is_same = translated == phrase
        status = "❌ SAME" if is_same else "✓ Translated"
        print(f"{status} | EN: {phrase:30} → RU: {translated}")
    except Exception as e:
        print(f"ERROR | EN: {phrase:30} → Error: {e}")

print("\n" + "=" * 80)
print("DIAGNOSIS:")
print("=" * 80)
print("If Azerbaijani shows '❌ SAME' - GoogleTranslator may not support Azerbaijani well")
print("If Russian works but Azerbaijani doesn't - this confirms the issue")
print("\nPossible solutions:")
print("1. Use a different translation service for Azerbaijani")
print("2. Manually translate Azerbaijani content")
print("3. Try 'az-Latn' (Latin script) instead of 'az' language code")
print("=" * 80)
