import configparser

from api import CollectionUpdateResult
import app
from functions import determine_rule_type
from planner import plan_query


def test_name_contains_plan_uses_search_term_and_keeps_matcher_filter():
    rules = determine_rule_type([("Name", "*harbor*")])
    plan = plan_query(rules)

    assert plan.strategy == "server-side filtered query"
    assert plan.params["SearchTerm"] == "harbor"
    assert rules["filters"] == {"name": "*harbor*"}


def test_unsupported_name_wildcard_uses_full_scan():
    rules = determine_rule_type([("Name", "harbor*")])
    plan = plan_query(rules)

    assert plan.strategy == "full paginated fallback scan"
    assert "SearchTerm" not in plan.params


class CandidateAPI:
    def __init__(self):
        self.queries = []
        self.updated_ids = None

    def Libraries(self):
        return [
            {"Id": "one", "Name": "Storage_1"},
            {"Id": "two", "Name": "Storage_2"},
        ]

    def iter_library_content(self, library_id, params=None, fields=None):
        self.queries.append((library_id, dict(params or {})))
        yield [
            {"Id": f"match-{library_id}", "Name": "The Harbor", "MediaType": "Video"},
            {"Id": f"false-{library_id}", "Name": "Ed Ge", "MediaType": "Video"},
        ], 2, 2

    def update_collection(self, name, ids):
        self.updated_ids = set(ids)
        return CollectionUpdateResult(name, "collection", False, len(ids), len(ids), 0)


def test_name_search_uses_candidates_across_all_libraries_and_verifies_wildcard(monkeypatch):
    fake = CandidateAPI()
    monkeypatch.setattr(app, "emby_api", fake)
    config = configparser.ConfigParser()
    config.read_dict({"Harbors": {"Name": "*harbor*"}})

    app.main(config)

    assert [library_id for library_id, _ in fake.queries] == ["one", "two"]
    assert all(query["SearchTerm"] == "harbor" for _, query in fake.queries)
    assert fake.updated_ids == {"match-one", "match-two"}
