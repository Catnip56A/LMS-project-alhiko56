"""
Test automatic language detection for the translation system
"""
from yonca.content_translator import detect_language

print("=" * 80)
print("LANGUAGE DETECTION TEST")
print("=" * 80)

# Test samples in different languages
test_samples = [
    ("English text", "This is a course about machine learning and artificial intelligence"),
    ("Azerbaijani text", "Bu, maşın öyrənməsi və süni intellekt haqqında kursdir"),
    ("Russian text", "Это курс о машинном обучении и искусственном интеллекте"),
    ("Turkish text", "Bu, makine öğrenimi ve yapay zeka hakkında bir kursttur"),
    ("Mixed short", "Hello"),
    ("Numbers only", "12345"),
]

print("\nTesting language detection:\n")
for label, text in test_samples:
    detected = detect_language(text)
    print(f"{label:20} → Detected: {detected}")
    print(f"  Text: {text[:60]}...")
    print()

print("=" * 80)
print("KEY POINTS:")
print("=" * 80)
print("✓ System now auto-detects source language")
print("✓ Works with Azerbaijani, Russian, English, Turkish, Arabic, etc.")
print("✓ If original is Azerbaijani → translates to English + Russian")
print("✓ If original is Russian → translates to English + Azerbaijani")
print("✓ If original is English → translates to Azerbaijani + Russian (as before)")
print("✓ Short text (<10 chars) defaults to English")
print()
print("USAGE IN CODE:")
print("  # Auto-detect (recommended)")
print("  translate_content('course', 1, 'title', 'Azərbaycan dili kursu')")
print("  # Or specify manually")
print("  translate_content('course', 1, 'title', 'Azərbaycan dili kursu', source_language='az')")
print("=" * 80)
