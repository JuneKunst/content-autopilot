"""Text processing utilities."""

import re
from html.parser import HTMLParser
from typing import List


class HTMLStripper(HTMLParser):
    """HTML parser that strips tags and returns plain text."""
    
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = []
    
    def handle_data(self, data: str) -> None:
        """Collect text data."""
        self.text.append(data)
    
    def get_data(self) -> str:
        """Return collected text."""
        return "".join(self.text)


def strip_html(html: str) -> str:
    """Remove HTML tags from string.
    
    Args:
        html: HTML string to process
        
    Returns:
        Plain text with HTML tags removed
    """
    stripper = HTMLStripper()
    try:
        stripper.feed(html)
        return stripper.get_data()
    except Exception:
        # Fallback to regex if parsing fails
        return re.sub(r"<[^>]+>", "", html)


def truncate(
    text: str,
    max_length: int = 4000,
    suffix: str = "..."
) -> str:
    """Truncate text to maximum length.
    
    Args:
        text: Text to truncate
        max_length: Maximum length in characters
        suffix: Suffix to append if truncated
        
    Returns:
        Truncated text with suffix if needed
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def extract_urls(text: str) -> List[str]:
    """Extract all URLs from text.
    
    Args:
        text: Text to search for URLs
        
    Returns:
        List of URLs found in text
    """
    pattern = r"https?://[^\s<>\"{}|\\^\[\]]+"
    return re.findall(pattern, text)


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text.
    
    Collapses multiple spaces/newlines into single spaces and strips
    leading/trailing whitespace.
    
    Args:
        text: Text to normalize
        
    Returns:
        Text with normalized whitespace
    """
    return re.sub(r"\s+", " ", text).strip()
