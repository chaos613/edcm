import os
from api import *

CONFIG_PATH = os.getenv("EDCM_CONFIG_PATH", "/config/config.ini")
EDCM_DEBUG = os.getenv("EDCM_DEBUG", "false")
DEBUG = EDCM_DEBUG.strip().lower() in {"1", "true", "yes", "on"}
EMBY_ADDRESS = os.getenv("EMBY_ADDRESS")
EMBY_PORT = int(os.getenv("EMBY_PORT", 8096))
EMBY_TOKEN = os.getenv("EMBY_TOKEN")
SCAN_INTERVAL = int(os.getenv("EDCM_SCAN_INTERVAL", 600))  # seconds
PAGE_SIZE = int(os.getenv("EDCM_PAGE_SIZE", 2000))
HTTP_TIMEOUT = float(os.getenv("EDCM_HTTP_TIMEOUT", 30))
USE_SSL = os.getenv("EDCM_USE_SSL", "false").strip().lower() in {"1", "true", "yes", "on"}
HTTPS = "https" if USE_SSL else "http"

emby_api = api(base_url=f"{HTTPS}://{EMBY_ADDRESS}:{EMBY_PORT}", api_token=EMBY_TOKEN, timeout=HTTP_TIMEOUT, page_size=PAGE_SIZE)

config_behaviour_rules = [
    "DryRun", "Description", "Library", "IncludeVideo", "IncludeFolders",
    "IncludePhotos",
]

items_param_rules = [
    "AdjacentTo",
    "AiredDuringSeason",
    "Albums",
    "Artists",
    "ArtistType",
    "AudioCodecs",
    "Containers",
    "ExcludeLocationTypes",
    "ExcludeTags",
    "Genres",
    "HasImdbId",
    "HasOfficialRating",
    "HasOverview",
    "HasParentalRating",
    "HasSpecialFeature",
    "HasSubtitles",
    "HasThemeSong",
    "HasThemeVideo",
    "HasTmdbId",
    "HasTrailer",
    "HasTvdbId",
    "Is3D",
    "IsFavorite",
    "IsHD",
    "IsLocked",
    "IsMissing",
    "IsPlaceHolder",
    "IsPlayed",
    "IsUnaired",
    "LocationTypes",
    "MaxOfficialRating",
    "MaxPlayers",
    "MaxPremiereDate",
    "MinCommunityRating",
    "MinCriticRating",
    "MinDateLastSaved",
    "MinDateLastSavedForUser",
    "MinIndexNumber",
    "MinOfficialRating",
    "MinPlayers",
    "MinPremiereDate",
    "OfficialRatings",
    "ParentIndexNumber",
    "SeriesStatus",
    "SearchTerm",
    "SubtitleCodecs",
    "Tags",
    "VideoCodecs",
    "VideoTypes",
    "Years",
]
