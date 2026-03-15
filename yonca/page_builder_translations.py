"""
Page Builder Translation Support

Handles extraction, storage, and retrieval of translatable content from page builder blocks.
"""

def extract_translatable_fields(block):
    """
    Extract all translatable text fields from a block.
    Returns a dict of {field_name: text_value, ...}
    """
    translatable = {}
    block_type = block.get('type', '')
    settings = block.get('settings', {})
    
    if block_type == 'plain-text':
        if settings.get('text'):
            translatable['text'] = settings['text']
    
    elif block_type == 'hero':
        if settings.get('title'):
            translatable['title'] = settings['title']
        if settings.get('subtitle'):
            translatable['subtitle'] = settings['subtitle']
    
    elif block_type == 'text-image':
        if settings.get('text'):
            translatable['text'] = settings['text']
    
    elif block_type == 'buttons':
        buttons = settings.get('buttons', [])
        for idx, button in enumerate(buttons):
            if button.get('text'):
                translatable[f'button_{idx}_text'] = button['text']
    
    elif block_type == 'carousel':
        items = settings.get('items', [])
        for idx, item in enumerate(items):
            if item.get('title'):
                translatable[f'item_{idx}_title'] = item['title']
            if item.get('description'):
                translatable[f'item_{idx}_description'] = item['description']
    
    return translatable


def get_translation_keys_for_block(course_id, block_id):
    """Generate translation key prefix for a block"""
    return f"page_builder_{course_id}_block_{block_id}"


def extract_all_translatable_content(course_id, page_builder_data):
    """
    Extract all translatable content from page_builder_data.
    Returns a dict: {translation_key: text_value, ...}
    """
    translatable_content = {}
    
    if not page_builder_data:
        return translatable_content
    
    for block in page_builder_data:
        block_id = block.get('id', '')
        fields = extract_translatable_fields(block)
        
        key_prefix = get_translation_keys_for_block(course_id, block_id)
        for field_name, text_value in fields.items():
            key = f"{key_prefix}_{field_name}"
            translatable_content[key] = text_value
    
    return translatable_content


def apply_translations_to_block(block, translations_dict):
    """
    Apply translations to a block's translatable fields.
    Returns the modified block with translated content.
    """
    import copy
    block = copy.deepcopy(block)
    
    block_type = block.get('type', '')
    settings = block.get('settings', {})
    
    if block_type == 'plain-text':
        # Handled by template
        pass
    
    elif block_type == 'hero':
        # Handled by template
        pass
    
    elif block_type == 'text-image':
        # Handled by template
        pass
    
    elif block_type == 'buttons':
        buttons = settings.get('buttons', [])
        for idx, button in enumerate(buttons):
            translated = translations_dict.get(f'button_{idx}_text')
            if translated:
                button['text'] = translated
    
    elif block_type == 'carousel':
        items = settings.get('items', [])
        for idx, item in enumerate(items):
            title_key = f'item_{idx}_title'
            desc_key = f'item_{idx}_description'
            
            if title_key in translations_dict:
                item['title'] = translations_dict[title_key]
            if desc_key in translations_dict:
                item['description'] = translations_dict[desc_key]
    
    return block


def get_translations_for_block(course_id, block_id, translations_dict):
    """
    Extract translations for a specific block from the full translations dict.
    Returns: {field_name: translated_text, ...}
    """
    key_prefix = get_translation_keys_for_block(course_id, block_id)
    block_translations = {}
    
    for key, value in translations_dict.items():
        if key.startswith(key_prefix + '_'):
            field_name = key.replace(key_prefix + '_', '')
            block_translations[field_name] = value
    
    return block_translations
