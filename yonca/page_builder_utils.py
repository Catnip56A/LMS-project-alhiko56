"""Utilities for the no-code page builder"""
import re
import html
import urllib.parse
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

def extract_google_drive_id(input_str):
    """
    Extract Google Drive file ID from various URL formats or direct ID.
    Converts to a public image URL that works without Google authentication.
    
    Handles:
    - Direct ID: 1a_B2c3D4e5F6g7H8i9J0k1L2m3N4o5P
    - View URL: https://drive.google.com/file/d/FILE_ID/view
    - View with sharing: https://drive.google.com/file/d/FILE_ID/view?usp=sharing
    - Open URL: https://drive.google.com/open?id=FILE_ID
    - Already converted: https://lh3.google.com/d/FILE_ID
    
    Returns:
    - Public image URL: https://lh3.google.com/d/FILE_ID
    - Works without Google authentication for publicly shared files
    - The file MUST be shared publicly or with "Anyone with the link"
    """
    if not input_str:
        return ""
    
    input_str = input_str.strip()
    
    # If it's already in proxy format, return as is
    if "/api/proxy-image/" in input_str:
        return input_str
    
    file_id = None
    
    # Pattern 1: /file/d/{FILE_ID}/view or /file/d/{FILE_ID}/ (Google Drive share link)
    match = re.search(r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)(?:/|[?&])', input_str)
    if match:
        file_id = match.group(1)
    
    # Pattern 2: /open?id={FILE_ID}
    if not file_id:
        match = re.search(r'drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)', input_str)
        if match:
            file_id = match.group(1)
    
    # Pattern 3: uc?export=view&id={FILE_ID}
    if not file_id:
        match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', input_str)
        if match:
            file_id = match.group(1)
    
    # Pattern 4: Maybe it's already lh3.google.com/d/{FILE_ID}
    if not file_id:
        match = re.search(r'lh3\.google(?:usercontent)?\.com/d/([a-zA-Z0-9_-]+)', input_str)
        if match:
            file_id = match.group(1)
    
    # Pattern 5: Maybe it's just the file ID directly (long alphanumeric string)
    if not file_id and len(input_str) > 20 and re.match(r'^[a-zA-Z0-9_-]+$', input_str):
        file_id = input_str
    
    if file_id:
        # Use our own proxy endpoint to serve the image (avoids CORB issues)
        return f"/api/proxy-image/{file_id}"
    
    # If we couldn't extract a file ID, return original string
    return input_str

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
    mobile_css_rules = []  # Collect mobile responsive CSS rules
    block_index = 0  # Track block index for unique IDs
    
    for block in blocks:
        block_type = block.get('type', '')
        settings = block.get('settings', {})
        
        # Unique ID for this block (used for mobile CSS targeting)
        block_id = f"block-{block_index}"
        
        # Get sizing from settings
        padding = settings.get('padding', '20')
        width = settings.get('width', '100')
        
        # Get scale setting
        scale = settings.get('scale', '100')
        
        # Build container styles with alignment and scale.
        # Keep positioning and scaling on different wrappers to avoid visual drift.
        width = width or '100'
        scale = scale or '100'

        try:
            width_value = float(width)
        except (TypeError, ValueError):
            width_value = 100.0
        width_value = max(1.0, min(width_value, 100.0))

        try:
            scale_factor = float(scale) / 100
        except (TypeError, ValueError):
            scale_factor = 1.0
        scale_factor = max(0.1, min(scale_factor, 3.0))

        # Handle custom positioning
        use_custom_position = settings.get('useCustomPosition', False)
        
        if use_custom_position:
            # For absolute positioning, parse coordinates intelligently
            # Desktop coordinates
            pos_x_raw = str(settings.get('posX', '0')).strip()
            pos_y_raw = str(settings.get('posY', '0')).strip()
            
            # Check if posX contains % (width) or just pixels
            pos_width = None
            pos_x = 0
            
            if '%' in pos_x_raw:
                # It's a width percentage
                try:
                    pos_width = float(pos_x_raw.replace('%', '').strip())
                    pos_width = max(1.0, min(pos_width, 100.0))
                except (TypeError, ValueError):
                    pos_width = 100
            else:
                # It's a pixel position
                try:
                    pos_x = int(pos_x_raw)
                except (TypeError, ValueError):
                    pos_x = 0
            
            # Y position is always pixels
            try:
                pos_y = int(pos_y_raw)
            except (TypeError, ValueError):
                pos_y = 0
            
            # Mobile coordinates with same logic
            pos_x_mobile_raw = str(settings.get('posXMobile', '0')).strip()
            pos_y_mobile_raw = str(settings.get('posYMobile', '0')).strip()
            
            pos_width_mobile = None
            pos_x_mobile = 0
            
            if '%' in pos_x_mobile_raw:
                # It's a width percentage
                try:
                    pos_width_mobile = float(pos_x_mobile_raw.replace('%', '').strip())
                    pos_width_mobile = max(1.0, min(pos_width_mobile, 100.0))
                except (TypeError, ValueError):
                    pos_width_mobile = 100
            else:
                # It's a pixel position
                try:
                    pos_x_mobile = int(pos_x_mobile_raw)
                except (TypeError, ValueError):
                    pos_x_mobile = 0
            
            try:
                pos_y_mobile = int(pos_y_mobile_raw)
            except (TypeError, ValueError):
                pos_y_mobile = 0
            
            # If width is set via %, use that; otherwise fall back to regular width setting
            width_for_positioning = pos_width if pos_width is not None else width_value
            width_for_positioning_mobile = pos_width_mobile if pos_width_mobile is not None else width_value
            
            # Desktop positioning style
            position_style_desktop = f"position: absolute; left: {pos_x}px; top: {pos_y}px; width: {width_for_positioning}%;"
            # Mobile positioning style (applied at breakpoint)
            position_style_mobile = f"position: absolute; left: {pos_x_mobile}px; top: {pos_y_mobile}px; width: {width_for_positioning_mobile}%;"
            
            outer_style = f"{position_style_desktop} box-sizing: border-box;"
            # Add a data attribute for mobile styles to be applied via CSS
            shell_style = f"width: 100%; max-width: 100%; data-mobile-style='{position_style_mobile}'"
            outer_div_tag = f'<div id="{block_id}" style="{outer_style}">'
        else:
            outer_style = "display: flex; justify-content: center; box-sizing: border-box;"
            shell_style = f"width: {width_value}%; max-width: 100%;"
            outer_div_tag = f'<div id="{block_id}" style="{outer_style}">'
        
        scale_style = f"transform: scale({scale_factor}); transform-origin: 50% 50%;"
        inner_style = f"padding: {padding}px; box-sizing: border-box;"
        
        if block_type == 'plain-text':
            text = preserve_html_tags(settings.get('text', ''))
            font_size = settings.get('fontSize', '16')
            font_size_mobile = settings.get('fontSizeMobile', font_size)  # Mobile variant
            padding_mobile = settings.get('paddingMobile', padding)
            width_mobile = settings.get('widthMobile', width)
            weight = settings.get('weight', 'normal')
            text_align = settings.get('textAlign', 'left')
            color = settings.get('color', '#333333')
            line_height = settings.get('lineHeight', '1.6')
            italic = 'italic' if settings.get('italic') else 'normal'
            underline = 'underline' if settings.get('underline') else 'none'
            
            # Collect mobile CSS for this block
            mobile_css_rules.append(f"""
                #{block_id} {{ padding: {padding_mobile}px; width: {width_mobile}%; }}
                #{block_id} p {{ font-size: {font_size_mobile}px; }}
            """)
            
            text_style = f"white-space: pre-wrap; font-size: {font_size}px; font-weight: {weight}; text-align: {text_align}; color: {color}; line-height: {line_height}; font-style: {italic}; text-decoration: {underline};"
            html = f'{outer_div_tag}<div style="{shell_style}"><div style="{scale_style}"><div style="{inner_style}"><p style="{text_style}">{text}</p></div></div></div></div>'
            html_parts.append(html)
            print(f"DEBUG RENDER: Added plain-text block")  # Debug
            
        elif block_type == 'hero':
            title = preserve_html_tags(settings.get('title', ''))
            subtitle = preserve_html_tags(settings.get('subtitle', ''))
            image_url = extract_google_drive_id(settings.get('image', ''))
            background_image_url = extract_google_drive_id(settings.get('backgroundImage', ''))
            title_font_size = settings.get('titleFontSize', '48')
            title_font_size_mobile = settings.get('titleFontSizeMobile', title_font_size)  # Mobile variant
            title_weight = settings.get('titleWeight', 'bold')
            subtitle_font_size = settings.get('subtitleFontSize', '24')
            subtitle_font_size_mobile = settings.get('subtitleFontSizeMobile', subtitle_font_size)  # Mobile variant
            subtitle_color = settings.get('subtitleColor', '#ffffff')
            padding_mobile = settings.get('paddingMobile', padding)
            width_mobile = settings.get('widthMobile', width)
            
            # Collect mobile CSS for this block
            mobile_css_rules.append(f"""
                #{block_id} {{ padding: {padding_mobile}px; width: {width_mobile}%; }}
                #{block_id} h1 {{ font-size: {title_font_size_mobile}px; }}
                #{block_id} p {{ font-size: {subtitle_font_size_mobile}px; }}
            """)
            
            # Create background image style if provided, properly encode URL
            background_style = ''
            if background_image_url:
                # Properly encode URL for CSS context while preserving URL structure
                safe_url = urllib.parse.quote(background_image_url, safe=':/?#[]@!$&\'()*+,;=.-_~')
                background_style = f"background-image: url('{safe_url}'); background-size: cover; background-position: center; background-repeat: no-repeat;"
            
            # Create image HTML with fixed width
            image_html = f'<img src="{image_url}" style="width: 100%; max-width: 400px; height: auto; border-radius: 8px;" />' if image_url else ''
            
            # Start with minimum height for hero section visibility
            hero_min_height = "min-height: 300px;" if background_image_url else ""
            
            html = f'''{outer_div_tag}<div style="{shell_style}"><div style="{scale_style}; {background_style} color: white; border-radius: 12px; {hero_min_height}">
                <div style="{inner_style}; display: flex; align-items: center; gap: 40px; flex-wrap: wrap;">
                    <div style="flex: 1; min-width: 250px;">
                        <h1 style="font-size: {title_font_size}px; font-weight: {title_weight}; margin: 0 0 20px 0; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">{title}</h1>
                        <p style="font-size: {subtitle_font_size}px; margin: 0; opacity: 0.95; color: {subtitle_color};">{subtitle}</p>
                    </div>
                    {f'<div style="flex: 1; min-width: 250px; display: flex; justify-content: center;">{image_html}</div>' if image_html else ''}
                </div>
            </div></div></div>'''
            html_parts.append(html)
            print(f"DEBUG RENDER: Added hero block")  # Debug
            
        elif block_type == 'text-image':
            text = preserve_html_tags(settings.get('text', ''))
            image_url = settings.get('image', '')
            padding_mobile = settings.get('paddingMobile', padding)
            width_mobile = settings.get('widthMobile', width)
            
            # Collect mobile CSS for this block
            mobile_css_rules.append(f"""
                #{block_id} {{ padding: {padding_mobile}px; width: {width_mobile}%; }}
            """)
            
            if not image_url:
                # Just show text if no image
                html = f'{outer_div_tag}<div style="{shell_style}"><div style="{scale_style}"><div style="{inner_style}"><p style="white-space: pre-wrap; line-height: 1.6;">{text}</p></div></div></div></div>'
            else:
                image_html = f'<img src="{image_url}" style="width: 100%; height: auto; border-radius: 8px; margin-bottom: 20px;" />'
                text_html = f'<p style="white-space: pre-wrap; line-height: 1.6;">{text}</p>'
                html = f'{outer_div_tag}<div style="{shell_style}"><div style="{scale_style}; display: flex; flex-direction: column; align-items: center;"><div style="{inner_style}">{image_html}{text_html}</div></div></div></div>'
            
            html_parts.append(html)
            
        elif block_type == 'buttons':
            buttons_data = settings.get('buttons', [])
            button_font_size = settings.get('buttonFontSize', '16')
            button_font_size_mobile = settings.get('buttonFontSizeMobile', button_font_size)  # Mobile variant
            button_font_weight = settings.get('buttonFontWeight', 'bold')
            padding_mobile = settings.get('paddingMobile', padding)
            width_mobile = settings.get('widthMobile', width)
            
            # Collect mobile CSS for this block
            mobile_css_rules.append(f"""
                #{block_id} {{ padding: {padding_mobile}px; width: {width_mobile}%; }}
                #{block_id} a {{ font-size: {button_font_size_mobile}px; }}
            """)
            
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
            html = f'{outer_div_tag}<div style="{shell_style}"><div style="{scale_style}"><div style="{inner_style}">{buttons_html}</div></div></div></div>'
            html_parts.append(html)
            
        elif block_type == 'youtube':
            video_id_input = settings.get('videoId', '')
            height = settings.get('height', '400')
            height_mobile = settings.get('heightMobile', height)  # Mobile variant
            padding_mobile = settings.get('paddingMobile', padding)
            width_mobile = settings.get('widthMobile', width)
            
            # Collect mobile CSS for this block
            mobile_css_rules.append(f"""
                #{block_id} {{ padding: {padding_mobile}px; width: {width_mobile}%; }}
                #{block_id} iframe {{ height: {height_mobile}px; }}
            """)
            
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
                    
                    html = f'''{outer_div_tag}<div style="{shell_style}"><div style="{scale_style}">
                        <div style="{inner_style}">
                            <iframe width="100%" height="{height}" src="{embed_url}" frameborder="0" 
                                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
                                allowfullscreen style="border-radius: 8px;"></iframe>
                            <!-- DEBUG: video_id={video_id}, embed_url={embed_url} -->
                        </div>
                    </div></div></div>'''
                    html_parts.append(html)
                    print(f"DEBUG YOUTUBE: Iframe HTML generated successfully")
                else:
                    # Invalid video ID format
                    print(f"DEBUG YOUTUBE: Invalid video ID - showing error message. video_id='{video_id}', len={len(video_id) if video_id else 0}")
                    html = f'''{outer_div_tag}<div style="{shell_style}"><div style="{scale_style}; background: #fff3cd; border-radius: 8px; text-align: center;">
                        <div style="{inner_style}">
                            <p style="color: #856404; margin: 0;">Invalid YouTube video ID format</p>
                            <small style="color: #856404;">Please use: dQw4w9WgXcQ or https://youtube.com/watch?v=dQw4w9WgXcQ</small>
                        </div>
                    </div></div></div>'''
                    html_parts.append(html)
                
        elif block_type == 'carousel':
            items = settings.get('items', [])
            carousel_layout = settings.get('alignment', 'centered')  # This is the carousel layout (centered vs dual)
            autoplay = settings.get('autoplay', False)
            interval = settings.get('interval', 3000)
            item_title_font_size = settings.get('itemTitleFontSize', '24')
            item_title_font_size_mobile = settings.get('itemTitleFontSizeMobile', item_title_font_size)  # Mobile variant
            item_title_weight = settings.get('itemTitleWeight', 'bold')
            item_description_font_size = settings.get('itemDescriptionFontSize', '16')
            item_description_font_size_mobile = settings.get('itemDescriptionFontSizeMobile', item_description_font_size)  # Mobile variant
            padding_mobile = settings.get('paddingMobile', padding)
            width_mobile = settings.get('widthMobile', width)
            carousel_id = f"carousel_{block.get('id', 'default')}"
            
            # Collect mobile CSS for this block
            mobile_css_rules.append(f"""
                #{block_id} {{ padding: {padding_mobile}px; width: {width_mobile}%; }}
                #{block_id} h3 {{ font-size: {item_title_font_size_mobile}px; }}
                #{block_id} p {{ font-size: {item_description_font_size_mobile}px; }}
            """)
            
            if items:
                # Determine layout based on carousel_layout
                if carousel_layout == 'centered':
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
                    
                    html = f'''{outer_div_tag}<div style="{shell_style}"><div style="{scale_style}; position: relative; margin-bottom: 20px;">
                        <div style="{inner_style}">
                            <div id="{carousel_id}" style="position: relative; min-height: 500px; overflow: hidden;">
                                {items_html}
                                {nav_html}
                            </div>
                            {dots_html}
                            {autoplay_script}
                        </div>
                    </div></div></div>'''
                    
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
                    
                    if carousel_layout == 'left':
                        html = f'''{outer_div_tag}<div style="{shell_style}"><div style="{scale_style}; display: flex; gap: 30px; align-items: flex-start; margin-bottom: 20px;">
                            <div style="{inner_style}">
                                {item1_html}
                                {item2_html}
                            </div>
                        </div></div></div>'''
                    else:  # right
                        html = f'''{outer_div_tag}<div style="{shell_style}"><div style="{scale_style}; display: flex; gap: 30px; align-items: flex-start; flex-direction: row-reverse; margin-bottom: 20px;">
                            <div style="{inner_style}">
                                {item1_html}
                                {item2_html}
                            </div>
                        </div></div></div>'''
                
                
                html_parts.append(html)
        
        # Increment block index for next block's unique ID
        block_index += 1
    
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
    
    # Generate mobile CSS media queries
    mobile_css = ""
    if mobile_css_rules:
        mobile_css_content = "\n".join(mobile_css_rules)
        mobile_css = f"""
        <style>
        @media (max-width: 768px) {{
            {mobile_css_content}
        }}
        </style>
        """
    
    # Wrap all blocks in a positioned container so absolutely positioned elements
    # are positioned relative to this container, not the window
    content_html = '\n'.join(html_parts) + carousel_script + mobile_css
    wrapped_html = f'<div style="position: relative; width: 100%; min-height: 600px;">{content_html}</div>'
    
    return wrapped_html
