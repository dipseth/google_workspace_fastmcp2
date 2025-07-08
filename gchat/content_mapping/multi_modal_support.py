"""
Multi-Modal Content Support for Google Chat Card Creation

This module provides the MultiModalSupport class, which handles various types of
media content for Google Chat cards, including image optimization, chart generation,
and video thumbnail extraction.
"""

import logging
import re
import uuid
import json
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse
import random

logger = logging.getLogger(__name__)


class MultiModalSupport:
    """Provides support for multi-modal content in cards."""
    
    def __init__(self):
        """Initialize the multi-modal support module."""
        # Define supported image formats and sizes
        self.supported_image_formats = ["jpg", "jpeg", "png", "gif", "webp"]
        self.supported_chart_types = ["bar", "line", "pie", "scatter", "area", "radar"]
        self.supported_video_platforms = ["youtube", "vimeo", "drive"]
        
        # Define optimization parameters
        self.default_image_size = (800, 600)  # Default target size for images
        self.max_image_size = (1200, 900)     # Maximum image size
        self.thumbnail_size = (320, 180)      # Standard 16:9 thumbnail size
        
        # Define CDN or proxy service URL (placeholder)
        self.image_proxy_url = "https://image-proxy.example.com"
    
    async def optimize_image(self, image_url: str, target_size: Tuple[int, int] = None) -> str:
        """
        Optimize an image for use in a card.
        
        This method:
        1. Validates the image URL
        2. Determines the optimal size based on target or defaults
        3. Generates a proxy URL that will handle resizing and optimization
        
        Args:
            image_url: URL of the image to optimize
            target_size: Optional target size as (width, height)
            
        Returns:
            URL of the optimized image
        """
        logger.info(f"Optimizing image: {image_url}")
        
        # Validate URL
        if not self._is_valid_url(image_url):
            logger.warning(f"Invalid image URL: {image_url}")
            return image_url
        
        # Extract file extension to check format
        parsed_url = urlparse(image_url)
        path = parsed_url.path
        extension = path.split('.')[-1].lower() if '.' in path else None
        
        # Check if format is supported
        if extension and extension not in self.supported_image_formats:
            logger.warning(f"Unsupported image format: {extension}")
            # Return original URL if format is not supported
            return image_url
        
        # Determine target size
        size = target_size or self.default_image_size
        width, height = size
        
        # Ensure size is within limits
        width = min(width, self.max_image_size[0])
        height = min(height, self.max_image_size[1])
        
        # In a real implementation, this would generate a URL for an image optimization service
        # For now, we'll simulate it with a placeholder URL
        optimized_url = f"{self.image_proxy_url}/resize?url={image_url}&width={width}&height={height}&format=webp"
        
        logger.info(f"Optimized image URL: {optimized_url}")
        return optimized_url
    
    async def generate_chart(self, data: Dict, chart_type: str = "bar") -> str:
        """
        Generate a chart image from data.
        
        Args:
            data: Dictionary containing chart data (labels, values, etc.)
            chart_type: Type of chart to generate (bar, line, pie, etc.)
            
        Returns:
            URL of the generated chart image
        """
        logger.info(f"Generating {chart_type} chart")
        
        # Validate chart type
        if chart_type not in self.supported_chart_types:
            logger.warning(f"Unsupported chart type: {chart_type}, defaulting to bar")
            chart_type = "bar"
        
        # Validate data structure
        if not self._validate_chart_data(data, chart_type):
            logger.error(f"Invalid data structure for {chart_type} chart")
            # Return a placeholder image for invalid data
            return f"https://via.placeholder.com/800x400?text=Invalid+Chart+Data"
        
        # In a real implementation, this would use a chart generation service
        # For now, we'll simulate it with a placeholder URL
        
        # Generate a unique ID for the chart
        chart_id = str(uuid.uuid4())[:8]
        
        # Serialize data for URL parameters
        data_param = json.dumps(data).replace(" ", "")
        
        # Generate chart URL (in a real implementation, this would be a chart service)
        chart_url = f"https://chart-service.example.com/generate?type={chart_type}&data={data_param}&id={chart_id}"
        
        logger.info(f"Generated chart URL: {chart_url}")
        return chart_url
    
    async def extract_video_thumbnail(self, video_url: str) -> str:
        """
        Extract a thumbnail from a video URL.
        
        Args:
            video_url: URL of the video
            
        Returns:
            URL of the extracted thumbnail
        """
        logger.info(f"Extracting thumbnail from video: {video_url}")
        
        # Validate URL
        if not self._is_valid_url(video_url):
            logger.warning(f"Invalid video URL: {video_url}")
            return f"https://via.placeholder.com/320x180?text=Invalid+Video+URL"
        
        # Determine video platform
        platform = self._detect_video_platform(video_url)
        
        if platform == "youtube":
            # Extract YouTube video ID
            video_id = self._extract_youtube_id(video_url)
            if video_id:
                # YouTube thumbnail URL format
                return f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
        
        elif platform == "vimeo":
            # For Vimeo, we would need to call their API to get the thumbnail
            # This is a simplified placeholder implementation
            return f"https://via.placeholder.com/320x180?text=Vimeo+Thumbnail"
        
        elif platform == "drive":
            # For Google Drive videos, we would need to use the Drive API
            # This is a simplified placeholder implementation
            return f"https://via.placeholder.com/320x180?text=Drive+Video+Thumbnail"
        
        # Default placeholder for unsupported platforms
        return f"https://via.placeholder.com/320x180?text=Video+Thumbnail"
    
    async def convert_data_to_table(self, data: List[Dict]) -> Dict:
        """
        Convert data to a table widget.
        
        Args:
            data: List of dictionaries containing row data
            
        Returns:
            Dictionary representing a table widget
        """
        logger.info(f"Converting data to table widget with {len(data)} rows")
        
        if not data or not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            logger.error("Invalid data format for table conversion")
            return {
                "textParagraph": {
                    "text": "Error: Invalid data format for table"
                }
            }
        
        # Extract column headers from the first item's keys
        columns = list(data[0].keys())
        
        # Create rows from data
        rows = []
        for item in data:
            row = []
            for col in columns:
                cell_value = item.get(col, "")
                row.append(str(cell_value))
            rows.append(row)
        
        # In a real implementation, we would create a proper table widget
        # Since Google Chat doesn't have a native table widget, we'll create a
        # formatted text representation
        
        # Format as a grid of decoratedText widgets
        widgets = []
        
        # Add header row
        header_widgets = []
        for col in columns:
            header_widgets.append({
                "decoratedText": {
                    "text": col,
                    "wrapText": True,
                    "bottomLabel": "header"
                }
            })
        
        widgets.append({
            "horizontalAlignment": "CENTER",
            "widgets": header_widgets
        })
        
        # Add data rows
        for row in rows:
            row_widgets = []
            for cell in row:
                row_widgets.append({
                    "decoratedText": {
                        "text": cell,
                        "wrapText": True
                    }
                })
            
            widgets.append({
                "horizontalAlignment": "CENTER",
                "widgets": row_widgets
            })
        
        # Return a section containing the table
        return {
            "section": {
                "widgets": widgets
            }
        }
    
    async def create_image_grid(self, image_urls: List[str]) -> Dict:
        """
        Create an image grid widget from multiple images.
        
        Args:
            image_urls: List of image URLs
            
        Returns:
            Dictionary representing an image grid widget
        """
        logger.info(f"Creating image grid with {len(image_urls)} images")
        
        if not image_urls:
            logger.warning("No images provided for grid")
            return {
                "textParagraph": {
                    "text": "No images to display"
                }
            }
        
        # Optimize all images to a consistent size
        optimized_urls = []
        for url in image_urls:
            # Use a smaller size for grid images
            optimized_url = await self.optimize_image(url, (400, 300))
            optimized_urls.append(optimized_url)
        
        # Create a grid layout
        # Since Google Chat doesn't have a native grid widget, we'll create a
        # layout of image widgets arranged in rows
        
        # Determine grid dimensions (max 3 images per row)
        images_per_row = min(3, len(optimized_urls))
        num_rows = (len(optimized_urls) + images_per_row - 1) // images_per_row
        
        # Create rows of images
        rows = []
        for i in range(num_rows):
            row_images = optimized_urls[i * images_per_row:(i + 1) * images_per_row]
            row_widgets = []
            
            for img_url in row_images:
                row_widgets.append({
                    "image": {
                        "imageUrl": img_url,
                        "altText": "Grid image"
                    }
                })
            
            rows.append({
                "horizontalAlignment": "CENTER",
                "widgets": row_widgets
            })
        
        # Return a section containing the image grid
        return {
            "section": {
                "widgets": rows
            }
        }
    
    def _is_valid_url(self, url: str) -> bool:
        """
        Check if a URL is valid.
        
        Args:
            url: URL to validate
            
        Returns:
            True if valid, False otherwise
        """
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
    
    def _validate_chart_data(self, data: Dict, chart_type: str) -> bool:
        """
        Validate data structure for a specific chart type.
        
        Args:
            data: Data to validate
            chart_type: Type of chart
            
        Returns:
            True if valid, False otherwise
        """
        # Basic validation for all chart types
        if not isinstance(data, dict):
            return False
        
        # Check for required fields based on chart type
        if chart_type in ["bar", "line", "area"]:
            # These charts require labels and values
            return "labels" in data and "values" in data and isinstance(data["labels"], list) and isinstance(data["values"], list)
        
        elif chart_type == "pie":
            # Pie charts require labels and values of the same length
            return ("labels" in data and "values" in data and 
                    isinstance(data["labels"], list) and isinstance(data["values"], list) and 
                    len(data["labels"]) == len(data["values"]))
        
        elif chart_type == "scatter":
            # Scatter charts require x and y values
            return "x" in data and "y" in data and isinstance(data["x"], list) and isinstance(data["y"], list)
        
        elif chart_type == "radar":
            # Radar charts require categories and series
            return ("categories" in data and "series" in data and 
                    isinstance(data["categories"], list) and isinstance(data["series"], list))
        
        # Unknown chart type
        return False
    
    def _detect_video_platform(self, video_url: str) -> str:
        """
        Detect the platform of a video URL.
        
        Args:
            video_url: URL of the video
            
        Returns:
            Platform name or "unknown"
        """
        if "youtube.com" in video_url or "youtu.be" in video_url:
            return "youtube"
        elif "vimeo.com" in video_url:
            return "vimeo"
        elif "drive.google.com" in video_url:
            return "drive"
        else:
            return "unknown"
    
    def _extract_youtube_id(self, youtube_url: str) -> Optional[str]:
        """
        Extract the video ID from a YouTube URL.
        
        Args:
            youtube_url: YouTube video URL
            
        Returns:
            YouTube video ID or None if not found
        """
        # Handle youtu.be format
        if "youtu.be" in youtube_url:
            parts = youtube_url.split("/")
            return parts[-1].split("?")[0]
        
        # Handle youtube.com format
        if "v=" in youtube_url:
            query = urlparse(youtube_url).query
            params = dict(param.split("=") for param in query.split("&"))
            return params.get("v")
        
        return None