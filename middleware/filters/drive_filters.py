"""
Google Drive URL formatting filters for Jinja2 templates.

Provides filters for converting various Google Drive URL formats into
embeddable image URLs and other Drive-specific transformations.
"""

import re


def format_drive_image_url_filter(url: str) -> str:
    """
    Format Google Drive URLs for image embedding.

    Converts various Drive URL formats to the proper uc?export=view format
    that can be embedded in HTML img tags.

    Supported input formats:
    - https://drive.google.com/file/d/FILE_ID/view
    - https://drive.google.com/file/d/FILE_ID/view?usp=sharing
    - https://drive.google.com/uc?id=FILE_ID
    - FILE_ID (just the ID)

    Args:
        url: Drive URL or file ID to format

    Returns:
        Formatted URL: https://drive.google.com/uc?export=view&id=FILE_ID

    Usage in templates:
        {{ drive_url | format_drive_image_url }}
        {{ image_id | format_drive_image_url }}
        <img src="{{ photo_link | format_drive_image_url }}" alt="Photo">
    """
    if not url or not isinstance(url, str):
        return url

    # Pattern 1: https://drive.google.com/file/d/FILE_ID/view
    match = re.search(r"/file/d/([a-zA-Z0-9-_]+)", url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=view&id={file_id}"

    # Pattern 2: https://drive.google.com/uc?id=FILE_ID
    match = re.search(r"[?&]id=([a-zA-Z0-9-_]+)", url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=view&id={file_id}"

    # Pattern 3: Just the ID itself (25+ characters, alphanumeric + hyphens/underscores)
    if re.match(r"^[a-zA-Z0-9-_]{25,}$", url):
        return f"https://drive.google.com/uc?export=view&id={url}"

    # Pattern 4: Already in correct format
    if "drive.google.com/uc?export=view" in url:
        return url

    # Return original if no pattern matches
    return url
