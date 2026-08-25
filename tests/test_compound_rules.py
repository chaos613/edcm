import configparser
from api import CollectionUpdateResult, EmbyAPIError
import app
from functions import determine_match, determine_rule_type, map_content_data
from planner import plan_query


def mapped(name, genres=None):
    return map_content_data({"Id": name, "Name": name, "Genres": genres or [], "MediaType": "Video"})


def test_name_any_matches_one_pattern():
    rules = {"nameany": "*vacation* | *boat* | *beach*"}
    assert determine_match(mapped("My Boat Trip"), "Test", rules)
    assert not determine_match(mapped("Mountain Trip"), "Test", rules)


def test_name_all_requires_every_pattern_in_any_order():
    rules = {"nameall": "*vacation* | *beach*"}
    assert determine_match(mapped("Beach Family Vacation"), "Test", rules)
    assert determine_match(mapped("Vacation at the Beach"), "Test", rules)
    assert not determine_match(mapped("Vacation in the Mountains"), "Test", rules)


def test_exclude_name_rejects_any_excluded_pattern():
    rules = {"nameany": "*vacation* | *boat* | *beach*", "excludename": "*surf* | *trailer*"}
    assert determine_match(mapped("Family Beach Day"), "Test", rules)
    assert not determine_match(mapped("Surf Beach Day"), "Test", rules)


def test_genre_any_all_and_exclusion():
    item = mapped("Film", ["Documentary", "Family", "Travel"])
    assert determine_match(item, "Test", {"genresany": "Comedy | Travel"})
    assert determine_match(item, "Test", {"genresall": "Documentary | Family"})
    assert not determine_match(item, "Test", {"genresall": "Documentary | Comedy"})
    assert not determine_match(item, "Test", {"excludegenres": "Horror | Travel"})


def test_name_any_creates_paginated_search_union():
    rules = determine_rule_type([("NameAny", "*vacation* | *boat* | *beach*")])
    plan = plan_query(rules)
    assert [query["SearchTerm"] for query in plan.queries] == ["vacation", "boat", "beach"]
    assert plan.strategy == "server-side filtered query"


def test_name_all_uses_one_mandatory_prefilter_and_keeps_local_check():
    rules = determine_rule_type([("NameAll", "*trip* | *family vacation* | *beach*")])
    plan = plan_query(rules)
    assert len(plan.queries) == 1
    assert plan.params["SearchTerm"] == "family vacation"
    assert "nameall" in rules["filters"]


def test_unsupported_name_any_pattern_falls_back_without_false_negatives():
    plan = plan_query(determine_rule_type([("NameAny", "*vacation* | boat*")]))
    assert plan.queries == ({},)
    assert plan.strategy == "full paginated fallback scan"


def test_genres_any_uses_native_or_prefilter():
    plan = plan_query(determine_rule_type([("GenresAny", "Documentary | Family | Travel")]))
    assert plan.params["Genres"] == "Documentary|Family|Travel"


def test_genres_all_uses_one_safe_native_prefilter_and_local_verification():
    rules = determine_rule_type([("GenresAll", "Documentary | Family"), ("ExcludeGenres", "Archive")])
    plan = plan_query(rules)
    assert plan.params["Genres"] == "Documentary"
    assert set(rules["filters"]) == {"genresall", "excludegenres"}


class UnionAPI:
    def __init__(self, fail_term=None):
        self.fail_term, self.calls, self.updated_ids = fail_term, [], None
    def Libraries(self):
        return [{"Id": "home", "Name": "Home Videos & Photos"}]
    def iter_library_content(self, library_id, params=None, fields=None):
        term = params["SearchTerm"]
        self.calls.append(term)
        if term == self.fail_term:
            raise EmbyAPIError("GET", "Items", "timed out")
        candidates = {
            "vacation": [{"Id": "one", "Name": "Family Vacation", "MediaType": "Video"}, {"Id": "shared", "Name": "Beach Vacation", "MediaType": "Video"}],
            "boat": [{"Id": "two", "Name": "New Boat", "MediaType": "Video"}, {"Id": "shared", "Name": "Beach Vacation", "MediaType": "Video"}],
            "beach": [{"Id": "shared", "Name": "Beach Vacation", "MediaType": "Video"}, {"Id": "excluded", "Name": "Surf Beach", "MediaType": "Video"}],
        }
        yield candidates[term], len(candidates[term]), len(candidates[term])
    def update_collection(self, name, ids):
        self.updated_ids = set(ids)
        return CollectionUpdateResult(name, "collection", False, len(ids), len(ids), 0)


def union_config():
    config = configparser.ConfigParser()
    config.read_dict({"Trips": {"NameAny": "*vacation* | *boat* | *beach*", "ExcludeName": "*surf*"}})
    return config


def test_name_any_unions_deduplicates_and_synchronizes_final_ids(monkeypatch):
    fake = UnionAPI()
    monkeypatch.setattr(app, "emby_api", fake)
    app.main(union_config())
    assert fake.calls == ["vacation", "boat", "beach"]
    assert fake.updated_ids == {"one", "two", "shared"}


def test_failed_or_branch_leaves_collection_unchanged(monkeypatch):
    fake = UnionAPI(fail_term="boat")
    monkeypatch.setattr(app, "emby_api", fake)
    app.main(union_config())
    assert fake.updated_ids is None
