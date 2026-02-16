"""Tests for video scraper."""

from src.video_scraper import get_video_data, MOCK_VIDEOS


def test_get_video_data_returns_mock_videos():
    """Returns mock video data structure."""
    result = get_video_data("Dr Jodie Rummer")
    assert "videos" in result
    assert isinstance(result["videos"], list)
    assert len(result["videos"]) == len(MOCK_VIDEOS)


def test_video_items_have_required_fields():
    """Each video has title, author, vimeoUrl."""
    result = get_video_data("Dr Jodie Rummer")
    for video in result["videos"]:
        assert "title" in video
        assert "author" in video
        assert "vimeoUrl" in video
        assert video["vimeoUrl"].startswith("https://vimeo.com/")
