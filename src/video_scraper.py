"""
Video scraper for content related to Dr Jodie Rummer and RummerLab.

Currently returns mock data. Intended for future integration with
Vimeo/YouTube APIs or scraping.
"""

from typing import TypedDict


class VideoItem(TypedDict):
    """Video metadata."""

    title: str
    author: str
    vimeoUrl: str


# Mock data: videos related to Dr Jodie Rummer / RummerLab research
MOCK_VIDEOS: list[VideoItem] = [
    {"title": "Fish Gills", "author": "Leteisha Prescott", "vimeoUrl": "https://vimeo.com/167221742"},
    {
        "title": "Mudskipper Movie Trailer",
        "author": "Tiffany Nay",
        "vimeoUrl": "https://vimeo.com/167221741",
    },
    {"title": "Baby Fish Swim", "author": "Adam Downie", "vimeoUrl": "https://vimeo.com/167221739"},
    {"title": "Hot Fish", "author": "Monica Morin", "vimeoUrl": "https://vimeo.com/167221740"},
]


def get_video_data(scholar_name: str) -> dict[str, list[VideoItem]]:
    """
    Fetch video data for a scholar.

    Returns mock data for now. Future implementation will query
    Vimeo, YouTube, or other sources for content related to the scholar.
    """
    # Placeholder for future scholar-based filtering
    _ = scholar_name
    return {"videos": MOCK_VIDEOS.copy()}
