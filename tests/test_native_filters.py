import configparser

from api import CollectionUpdateResult
import app
from functions import determine_rule_type
from planner import plan_query


def make_plan(entries):
    return plan_query(determine_rule_type(entries))


def test_genre_tags_exclusions_and_years_are_native_filters():
    plan = make_plan([
        ("Genres", "Documentary"), ("Tags", "Family"),
        ("ExcludeTags", "Archive"), ("Years", "2024"),
    ])
    assert plan.strategy == "server-side filtered query"
    assert plan.params == {
        "Genres": "Documentary", "Tags": "Family",
        "ExcludeTags": "Archive", "Years": "2024",
    }
    assert plan.server_filter_count == 4
    assert plan.local_verifier_count == 0


def test_rating_filters_are_native():
    plan = make_plan([
        ("OfficialRatings", "PG-13"), ("MinCommunityRating", "7"),
        ("MinCriticRating", "70"),
    ])
    assert plan.params["OfficialRatings"] == "PG-13"
    assert plan.params["MinCommunityRating"] == "7"
    assert plan.params["MinCriticRating"] == "70"


def test_codec_container_and_video_type_filters_are_native():
    plan = make_plan([
        ("Containers", "mkv"), ("VideoCodecs", "hevc"),
        ("AudioCodecs", "aac"), ("SubtitleCodecs", "srt"),
        ("VideoTypes", "VideoFile"),
    ])
    assert plan.params == {
        "Containers": "mkv", "VideoCodecs": "hevc", "AudioCodecs": "aac",
        "SubtitleCodecs": "srt", "VideoTypes": "VideoFile",
    }


def test_boolean_filters_are_native():
    entries = [
        ("IsHD", "true"), ("Is3D", "false"), ("IsFavorite", "true"),
        ("IsPlayed", "false"), ("IsLocked", "false"),
        ("HasSubtitles", "true"), ("HasTrailer", "false"),
        ("HasOverview", "true"), ("HasImdbId", "true"),
        ("HasTmdbId", "true"), ("HasTvdbId", "true"),
    ]
    plan = make_plan(entries)
    assert plan.server_filter_count == len(entries)
    assert all(plan.params[key] == value for key, value in entries)


def test_date_range_filters_are_native_and_combined_with_and_semantics():
    plan = make_plan([
        ("MinPremiereDate", "2024-01-01"),
        ("MaxPremiereDate", "2024-12-31"),
        ("MinDateLastSaved", "2026-01-01"),
    ])
    assert plan.params == {
        "MinPremiereDate": "2024-01-01",
        "MaxPremiereDate": "2024-12-31",
        "MinDateLastSaved": "2026-01-01",
    }


def test_hybrid_plan_pushes_native_filters_and_keeps_path_wildcard_local():
    rules = determine_rule_type([
        ("Genres", "Documentary"), ("Path", "*Vacation*"),
        ("Name", "harbor*"),
    ])
    plan = plan_query(rules)
    assert plan.strategy == "server-side filtered query"
    assert plan.params == {"Genres": "Documentary"}
    assert rules["filters"] == {"path": "*Vacation*", "name": "harbor*"}
    assert plan.local_verifier_count == 2


def test_path_only_and_unsupported_name_wildcard_fall_back_safely():
    plan = make_plan([("Path", "*Vacation*"), ("Name", "harbor*")])
    assert plan.strategy == "full paginated fallback scan"
    assert plan.params == {}
    assert plan.local_verifier_count == 2


class ScopedAPI:
    def __init__(self):
        self.calls = []
        self.updated_ids = None

    def Libraries(self):
        return [
            {"Id": "movies", "Name": "Movies"},
            {"Id": "home", "Name": "Home Videos & Photos"},
        ]

    def iter_library_content(self, library_id, params=None, fields=None):
        self.calls.append((library_id, dict(params or {}), set(fields or {})))
        yield [
            {"Id": "yes", "Name": "Harbor Vacation", "Path": "/media/Vacation/clip.mkv", "MediaType": "Video"},
            {"Id": "no", "Name": "Harbor Work", "Path": "/media/work/clip.mkv", "MediaType": "Video"},
        ], 2, 2

    def update_collection(self, name, ids):
        self.updated_ids = set(ids)
        return CollectionUpdateResult(name, "collection", False, len(ids), len(ids), 0)


def test_library_scoped_hybrid_query_and_final_local_verification(monkeypatch):
    fake = ScopedAPI()
    monkeypatch.setattr(app, "emby_api", fake)
    config = configparser.ConfigParser()
    config.read_dict({"Vacation": {
        "Library": "Home Videos & Photos", "Name": "*harbor*",
        "Genres": "Documentary", "Path": "*Vacation*",
    }})
    app.main(config)
    assert len(fake.calls) == 1
    library_id, params, fields = fake.calls[0]
    assert library_id == "home"
    assert params == {"Genres": "Documentary", "SearchTerm": "harbor"}
    assert fields == {"Path"}
    assert fake.updated_ids == {"yes"}
