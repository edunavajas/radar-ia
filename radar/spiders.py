"""Definiciones de spiders de Thordata.

Todo lo específico de la API vive aquí, para que cambiar un scraper sea tocar
un solo módulo. Los `spider_id` y parámetros marcados como CONFIRMADO salen de
la petición literal que genera el panel; los marcados como SIN CONFIRMAR siguen
el mismo patrón pero no se han validado contra el panel todavía.
"""

from __future__ import annotations

SPIDER_NAME = "youtube.com"

# CONFIRMADO EN PANEL
SPIDER_TRANSCRIPT = "youtube_transcript_by-id"
# CONFIRMADO EN PANEL (producto = información básica por id)
SPIDER_VIDEO = "youtube_product_by-id"

# Descubrimiento — SIN CONFIRMAR EN PANEL
SPIDER_POST_BY_URL = "youtube_video-post_by-url"
SPIDER_POST_BY_KEYWORD = "youtube_video-post_by-keyword"
SPIDER_POST_BY_SEARCH = "youtube_video-post_by-search-filters"
SPIDER_POST_BY_HASHTAG = "youtube_video-post_by-hashtag"
SPIDER_POST_BY_EXPLORE = "youtube_video-post_by-explore"


def transcript_request(
    video_id: str, lang: str | None = None, subtitle_type: str = "auto_generated"
) -> dict:
    """CONFIRMADO EN PANEL: subtítulos por id."""
    universal: dict[str, str] = {"selected_only": "false"}
    if lang:
        universal = {"subtitles_language": lang, "subtitles_type": subtitle_type}
    return {
        "spider_id": SPIDER_TRANSCRIPT,
        "spider_parameters": [{"video_id": video_id}],
        "spider_universal": universal,
        "file_name": "{{VideoID}}",
    }


def video_request(video_id: str) -> dict:
    """CONFIRMADO EN PANEL: metadatos del vídeo por id."""
    return {
        "spider_id": SPIDER_VIDEO,
        "spider_parameters": [{"video_id": video_id}],
        "file_name": "{{VideoID}}",
    }


# --------------------------------------------------------------------------- #
# Descubrimiento — SIN CONFIRMAR EN PANEL
# --------------------------------------------------------------------------- #


def channel_videos_request(url: str, num_of_posts: int = 15) -> dict:
    # SIN CONFIRMAR EN PANEL
    return {
        "spider_id": SPIDER_POST_BY_URL,
        "spider_parameters": [
            {"url": url, "order_by": "Latest", "num_of_posts": str(num_of_posts)}
        ],
        "file_name": "{{VideoID}}",
    }


def keyword_request(keyword: str, num_of_posts: int = 15) -> dict:
    # SIN CONFIRMAR EN PANEL
    return {
        "spider_id": SPIDER_POST_BY_KEYWORD,
        "spider_parameters": [{"keyword": keyword, "num_of_posts": str(num_of_posts)}],
        "file_name": "{{VideoID}}",
    }


def search_request(
    keyword_search: str,
    features: str = "",
    type_: str = "Video",
    duration: str = "",
    upload_date: str = "",
) -> dict:
    # SIN CONFIRMAR EN PANEL
    return {
        "spider_id": SPIDER_POST_BY_SEARCH,
        "spider_parameters": [
            {
                "keyword_search": keyword_search,
                "features": features,
                "type": type_,
                "duration": duration,
                "upload_date": upload_date,
            }
        ],
        "file_name": "{{VideoID}}",
    }


def hashtag_request(hashtag: str, num_of_posts: int = 15) -> dict:
    # SIN CONFIRMAR EN PANEL
    return {
        "spider_id": SPIDER_POST_BY_HASHTAG,
        "spider_parameters": [{"hashtag": hashtag, "num_of_posts": str(num_of_posts)}],
        "file_name": "{{VideoID}}",
    }


def explore_request(url: str, all_tabs: str = "true") -> dict:
    # SIN CONFIRMAR EN PANEL
    return {
        "spider_id": SPIDER_POST_BY_EXPLORE,
        "spider_parameters": [{"url": url, "all_tabs": all_tabs}],
        "file_name": "{{VideoID}}",
    }
