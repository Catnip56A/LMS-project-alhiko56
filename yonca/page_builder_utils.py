"""Utilities for the no-code page builder"""
import re
import html
from markupsafe import Markup

def extract_youtube_id(input_str):
    """
    Extract YouTube video ID from various URL formats or direct ID
    
    Handles:
    - Direct ID: dQw4w9WgXcQ
    - Long URL: https://www.youtube.com/watch?v=dQw4w9WgXcQ
    - Short URL: https://youtu.be/dQw4w9WgXcQ
    - With parameters: https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s
    """
    if not input_str:
        return ""
    
    # If it's already just an ID (11 characters, alphanumeric with - and _)
    if len(input_str) == 11 and re.match(r'^[a-zA-Z0-9_-]{11}$', input_str):
        return input_str
    
    # Try to extract from different YouTube URL formats
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]{11})',
        r'youtu\.be\/([a-zA-Z0-9_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, input_str)
        if match:
            return match.group(1)
    
    # If no pattern matched, try to find any 11-character sequence that looks like a video ID
    match = re.search(r'([a-zA-Z0-9_-]{11})', input_str)
    if match:
        return match.group(1)
    
    return input_str.strip()

def preserve_html_tags(text):
    """
    Ensure HTML tags in text are preserved and not escaped.
    Handles both literal HTML tags and HTML entities.
    
    Args:
        text (str): Text that may contain HTML tags or entities
        
    Returns:
        str: Text with HTML tags unescaped and preserved
    """
    if not text:
        return text
    
    # Unescape HTML entities (convert &lt; to <, &amp; to &, etc.)
    unescaped_text = html.unescape(text)
    
    # Return as is - if it contains HTML tags, they will be preserved
    return unescaped_text

def render_page_builder_blocks(blocks):
    """
    Convert page builder JSON blocks to HTML for display
    
    Args:
        blocks (list): List of block dictionaries from page_builder_data
        
    Returns:
        str: HTML string of rendered blocks
    """
    print(f"DEBUG RENDER: Called with blocks type: {type(blocks)}, length: {len(blocks) if blocks else 0}")  # Debug
    
    if not blocks or not isinstance(blocks, list):
        print(f"DEBUG RENDER: Returning empty string, blocks is falsy or not list")  # Debug
        return ""
    
    print(f"DEBUG RENDER: Processing {len(blocks)} blocks")  # Debug
    html_parts = []
    
    for block in blocks:
        block_type = block.get('type', '')
        settings = block.get('settings', {})
        
        # Get sizing from settings
        padding = settings.get('padding', '20')
        width = settings.get('width', '100')
        
        # Build container styles
        container_style = f"padding: {padding}px; width: {width}%; margin: 0 auto; box-sizing: border-box;"
        
        if block_type == 'plain-text':
            text = preserve_html_tags(settings.get('text', ''))
            font_size = settings.get('fontSize', '16')
            weight = settings.get('weight', 'normal')
            text_align = settings.get('textAlign', 'left')
            color = settings.get('color', '#333333')
            line_height = settings.get('lineHeight', '1.6')
            italic = 'italic' if settings.get('italic') else 'normal'
            underline = 'underline' if settings.get('underline') else 'none'
            
            text_style = f"white-space: pre-wrap; font-size: {font_size}px; font-weight: {weight}; text-align: {text_align}; color: {color}; line-height: {line_height}; font-style: {italic}; text-decoration: {underline};"
            html = f'<div style="{container_style}"><p style="{text_style}">{text}</p></div>'
            html_parts.append(html)
            print(f"DEBUG RENDER: Added plain-text block")  # Debug
            
        elif block_type == 'hero':
            title = preserve_html_tags(settings.get('title', ''))
            subtitle = preserve_html_tags(settings.get('subtitle', ''))
            image_url = settings.get('image', '')
            title_font_size = settings.get('titleFontSize', '48')
            title_weight = settings.get('titleWeight', 'bold')
            subtitle_font_size = settings.get('subtitleFontSize', '24')
            subtitle_color = settings.get('subtitleColor', '#ffffff')
            
            image_html = f'<img src="{image_url}" style="width: 100%; height: auto; border-radius: 8px; margin-bottom: 20px;" />' if image_url else ''
            
            html = f'''<div style="{container_style}; text-align: center; background: linear-gradient(135deg, #1e5919 0%, #337a2c 100%); color: white; border-radius: 12px;">
                <div style="padding: {padding}px;">
                    {image_html}
                    <h1 style="font-size: {title_font_size}px; font-weight: {title_weight}; margin: 20px 0; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">{title}</h1>
                    <p style="font-size: {subtitle_font_size}px; margin: 10px 0; opacity: 0.95; color: {subtitle_color};">{subtitle}</p>
                </div>
            </div>'''
            html_parts.append(html)
            print(f"DEBUG RENDER: Added hero block")  # Debug
            
        elif block_type == 'text-image':
            text = preserve_html_tags(settings.get('text', ''))
            image_url = settings.get('image', '')
            image_position = settings.get('imagePosition', 'right')
            
            if not image_url:
                # Just show text if no image
                html = f'<div style="{container_style}"><p style="white-space: pre-wrap; line-height: 1.6;">{text}</p></div>'
            else:
                image_html = f'<img src="{image_url}" style="width: 100%; height: auto; border-radius: 8px;" />'
                text_html = f'<p style="white-space: pre-wrap; line-height: 1.6;">{text}</p>'
                
                if image_position == 'left':
                    html = f'''<div style="{container_style}; display: grid; grid-template-columns: 1fr 1fr; gap: 20px; align-items: center;">
                        <div>{image_html}</div>
                        <div>{text_html}</div>
                    </div>'''
                else:  # right
                    html = f'''<div style="{container_style}; display: grid; grid-template-columns: 1fr 1fr; gap: 20px; align-items: center;">
                        <div>{text_html}</div>
                        <div>{image_html}</div>
                    </div>'''
            
            html_parts.append(html)
            
        elif block_type == 'buttons':
            buttons_data = settings.get('buttons', [])
            button_font_size = settings.get('buttonFontSize', '16')
            button_font_weight = settings.get('buttonFontWeight', 'bold')
            
            buttons_html = '<div style="display: flex; gap: 15px; flex-wrap: wrap; justify-content: center;">'
            for button in buttons_data:
                text = preserve_html_tags(button.get('text', 'Button'))
                url = button.get('url', '#')
                style = button.get('style', 'primary')
                
                # Button styling based on style (using website theme colors)
                if style == 'primary':
                    btn_style = "background: #337a2c; color: white;"
                elif style == 'secondary':
                    btn_style = "background: #809c13; color: white;"
                elif style == 'danger':
                    btn_style = "background: #dc3545; color: white;"
                else:  # default
                    btn_style = "background: #1e5919; color: white;"
                
                buttons_html += f'''<a href="{url}" style="{btn_style} padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: {button_font_weight}; font-size: {button_font_size}px; display: inline-block; transition: all 0.3s ease;">
                    {text}
                </a>'''
            
            buttons_html += '</div>'
            html = f'<div style="{container_style}">{buttons_html}</div>'
            html_parts.append(html)
            
        elif block_type == 'youtube':
            video_id_input = settings.get('videoId', '')
            height = settings.get('height', '400')
            
            print(f"DEBUG YOUTUBE: video_id_input = '{video_id_input}', height = {height}")
            
            if video_id_input:
                # Extract clean video ID from various formats
                video_id = extract_youtube_id(video_id_input)
                print(f"DEBUG YOUTUBE: Extracted video_id = '{video_id}' (length: {len(video_id) if video_id else 0})")
                
                if video_id and len(video_id) == 11:  # Valid YouTube ID is 11 chars
                    embed_url = f"https://www.youtube.com/embed/{video_id}?rel=0"
                    print(f"DEBUG YOUTUBE: Generated embed_url = {embed_url}")
                    print(f"DEBUG YOUTUBE: Rendering iframe for video ID: {video_id}")
                    
                    # Test alternative embed URL format
                    alt_embed_url = f"https://www.youtube-nocookie.com/embed/{video_id}?rel=0"
                    print(f"DEBUG YOUTUBE: Alternative embed URL: {alt_embed_url}")
                    
                    html = f'''<div style="{container_style}">
                        <iframe width="100%" height="{height}" src="{embed_url}" frameborder="0" 
                            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
                            allowfullscreen style="border-radius: 8px;"></iframe>
                        <!-- DEBUG: video_id={video_id}, embed_url={embed_url} -->
                    </div>'''
                    html_parts.append(html)
                    print(f"DEBUG YOUTUBE: Iframe HTML generated successfully")
                else:
                    # Invalid video ID format
                    print(f"DEBUG YOUTUBE: Invalid video ID - showing error message. video_id='{video_id}', len={len(video_id) if video_id else 0}")
                    html = f'''<div style="{container_style}; background: #fff3cd; padding: 20px; border-radius: 8px; text-align: center;">
                        <p style="color: #856404; margin: 0;">Invalid YouTube video ID format</p>
                        <small style="color: #856404;">Please use: dQw4w9WgXcQ or https://youtube.com/watch?v=dQw4w9WgXcQ</small>
                    </div>'''
                    html_parts.append(html)
                
        elif block_type == 'carousel':
            items = settings.get('items', [])
            alignment = settings.get('alignment', 'centered')
            autoplay = settings.get('autoplay', False)
            interval = settings.get('interval', 3000)
            item_title_font_size = settings.get('itemTitleFontSize', '24')
            item_title_weight = settings.get('itemTitleWeight', 'bold')
            item_description_font_size = settings.get('itemDescriptionFontSize', '16')
            carousel_id = f"carousel_{block.get('id', 'default')}"
            
            if items:
                # Determine layout based on alignment
                if alignment == 'centered':
                    # Single centered carousel with proper height constraint
                    items_html = ''
                    for idx, item in enumerate(items):
                        image = item.get('image', '')
                        title = preserve_html_tags(item.get('title', ''))
                        description = preserve_html_tags(item.get('description', ''))
                        
                        image_html = f'<img src="{image}" style="width: 100%; height: 400px; object-fit: cover; border-radius: 8px; margin-bottom: 15px;" />' if image else '<div style="width: 100%; height: 400px; background: #e9ecef; border-radius: 8px; margin-bottom: 15px;"></div>'
                        
                        items_html += f'''<div class="carousel-item" style="display: none; animation: fadeIn 0.5s; min-height: 500px; width: 100%;">
                            {image_html}
                            <h3 style="font-size: {item_title_font_size}px; font-weight: {item_title_weight}; margin: 10px 0; color: #333;">{title}</h3>
                            <p style="font-size: {item_description_font_size}px; color: #666; line-height: 1.6;">{description}</p>
                        </div>'''
                    
                    # Navigation dots
                    dots_html = '<div style="text-align: center; margin-top: 20px; display: flex; justify-content: center; gap: 8px;">'
                    for idx in range(len(items)):
                        dots_html += f'<button class="carousel-dot" onclick="showCarouselSlide(\'{carousel_id}\', {idx})" style="width: 12px; height: 12px; border-radius: 50%; border: 2px solid #337a2c; background: white; cursor: pointer; transition: all 0.3s;" data-slide="{idx}"></button>'
                    dots_html += '</div>'
                    
                    # Navigation arrows
                    nav_html = f'''
                        <button onclick="nextCarouselSlide('{carousel_id}')" style="position: absolute; right: 10px; top: 50%; transform: translateY(-50%); background: rgba(51, 122, 44, 0.8); color: white; border: none; padding: 10px 15px; border-radius: 5px; cursor: pointer; font-size: 18px; z-index: 10; hover: opacity 0.9;">→</button>
                        <button onclick="prevCarouselSlide('{carousel_id}')" style="position: absolute; left: 10px; top: 50%; transform: translateY(-50%); background: rgba(51, 122, 44, 0.8); color: white; border: none; padding: 10px 15px; border-radius: 5px; cursor: pointer; font-size: 18px; z-index: 10;">←</button>
                    '''
                    
                    autoplay_script = ''
                    if autoplay:
                        autoplay_script = f'''
                        <script>
                            (function() {{
                                let currentSlide_{carousel_id} = 0;
                                function autoAdvance() {{
                                    nextCarouselSlide('{carousel_id}');
                                }}
                                setInterval(autoAdvance, {interval});
                            }})();
                        </script>
                        '''
                    
                    html = f'''<div style="{container_style}; position: relative; margin-bottom: 20px;">
                        <div id="{carousel_id}" style="position: relative; min-height: 500px; overflow: hidden;">
                            {items_html}
                            {nav_html}
                        </div>
                        {dots_html}
                        {autoplay_script}
                    </div>'''
                    
                else:
                    # Dual layout (left or right) - show 2 items side by side
                    item1 = items[0] if len(items) > 0 else {'image': '', 'title': '', 'description': ''}
                    item2 = items[1] if len(items) > 1 else {'image': '', 'title': '', 'description': ''}
                    
                    img1_html = f'<img src="{item1.get("image", "")}" style="width: 100%; height: 350px; object-fit: cover; border-radius: 8px; margin-bottom: 15px;" />' if item1.get('image') else '<div style="width: 100%; height: 350px; background: #e9ecef; border-radius: 8px; margin-bottom: 15px;"></div>'
                    img2_html = f'<img src="{item2.get("image", "")}" style="width: 100%; height: 350px; object-fit: cover; border-radius: 8px; margin-bottom: 15px;" />' if item2.get('image') else '<div style="width: 100%; height: 350px; background: #e9ecef; border-radius: 8px; margin-bottom: 15px;"></div>'
                    
                    item1_title = preserve_html_tags(item1.get('title', ''))
                    item1_desc = preserve_html_tags(item1.get('description', ''))
                    item2_title = preserve_html_tags(item2.get('title', ''))
                    item2_desc = preserve_html_tags(item2.get('description', ''))
                    
                    item1_html = f'''<div style="flex: 1; min-width: 0;">
                        {img1_html}
                        <h3 style="font-size: {item_title_font_size}px; font-weight: {item_title_weight}; margin: 10px 0; color: #333;">{item1_title}</h3>
                        <p style="font-size: {item_description_font_size}px; color: #666; line-height: 1.6;">{item1_desc}</p>
                    </div>'''
                    
                    item2_html = f'''<div style="flex: 1; min-width: 0;">
                        {img2_html}
                        <h3 style="font-size: {item_title_font_size}px; font-weight: {item_title_weight}; margin: 10px 0; color: #333;">{item2_title}</h3>
                        <p style="font-size: {item_description_font_size}px; color: #666; line-height: 1.6;">{item2_desc}</p>
                    </div>'''
                    
                    if alignment == 'left':
                        html = f'''<div style="{container_style}; display: flex; gap: 30px; align-items: flex-start; margin-bottom: 20px;">
                            {item1_html}
                            {item2_html}
                        </div>'''
                    else:  # right
                        html = f'''<div style="{container_style}; display: flex; gap: 30px; align-items: flex-start; flex-direction: row-reverse; margin-bottom: 20px;">
                            {item1_html}
                            {item2_html}
                        </div>'''
                
                html_parts.append(html)
    
    # Add carousel JavaScript functions at the end
    carousel_script = '''
    <script>
    function showCarouselSlide(carouselId, slideIndex) {
        const carousel = document.getElementById(carouselId);
        if (!carousel) return;
        
        const slides = carousel.querySelectorAll('.carousel-item');
        const dots = document.querySelectorAll(`[data-carousel="${carouselId}"] .carousel-dot`);
        
        slides.forEach((slide, idx) => {
            slide.style.display = idx === slideIndex ? 'block' : 'none';
        });
        
        document.querySelectorAll('.carousel-dot').forEach((dot, idx) => {
            dot.style.background = idx === slideIndex ? '#337a2c' : 'white';
        });
    }
    
    function nextCarouselSlide(carouselId) {
        const carousel = document.getElementById(carouselId);
        if (!carousel) return;
        
        const slides = carousel.querySelectorAll('.carousel-item');
        const current = Array.from(slides).findIndex(s => s.style.display !== 'none');
        const next = (current + 1) % slides.length;
        showCarouselSlide(carouselId, next);
    }
    
    function prevCarouselSlide(carouselId) {
        const carousel = document.getElementById(carouselId);
        if (!carousel) return;
        
        const slides = carousel.querySelectorAll('.carousel-item');
        const current = Array.from(slides).findIndex(s => s.style.display !== 'none');
        const prev = (current - 1 + slides.length) % slides.length;
        showCarouselSlide(carouselId, prev);
    }
    
    // Initialize first slide of all carousels
    document.addEventListener('DOMContentLoaded', function() {
        document.querySelectorAll('[id^="carousel_"]').forEach(carousel => {
            const firstItem = carousel.querySelector('.carousel-item');
            if (firstItem) {
                firstItem.style.display = 'block';
                const dots = document.querySelectorAll('.carousel-dot');
                if (dots.length > 0) {
                    dots[0].style.background = '#667eea';
                }
            }
        });
    });
    
    // Add CSS for animations
    const style = document.createElement('style');
    style.textContent = `
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
    `;
    document.head.appendChild(style);
    </script>
    '''
    
    return '\n'.join(html_parts) + carousel_script
