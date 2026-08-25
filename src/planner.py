from dataclasses import dataclass


@dataclass(frozen=True)
class QueryPlan:
    params: dict
    strategy: str
    server_filter_count: int
    local_verifier_count: int


NON_RESTRICTIVE_PARAMS = {"fields", "startindex", "limit", "recursive", "parentid"}


def _contains_search_term(pattern):
    """Return text for a simple *text* pattern, otherwise None."""
    if not isinstance(pattern, str) or len(pattern) < 3:
        return None
    if not (pattern.startswith("*") and pattern.endswith("*")):
        return None
    term = pattern[1:-1]
    if not term or any(character in term for character in "*?["):
        return None
    return term


def plan_query(rules):
    """Combine all safe Emby filters and retain exact local verifiers."""
    params = dict(rules["params"])
    local_verifiers = set(rules["filters"])

    name_term = _contains_search_term(rules["filters"].get("name"))
    if name_term is not None and not any(key.casefold() == "searchterm" for key in params):
        params["SearchTerm"] = name_term

    server_filters = [
        key for key in params if key.casefold() not in NON_RESTRICTIVE_PARAMS
    ]
    strategy = (
        "server-side filtered query" if server_filters
        else "full paginated fallback scan"
    )
    return QueryPlan(params, strategy, len(server_filters), len(local_verifiers))
