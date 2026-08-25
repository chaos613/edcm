from dataclasses import dataclass


@dataclass(frozen=True)
class QueryPlan:
    params: dict
    queries: tuple
    strategy: str
    server_filter_count: int
    local_verifier_count: int


NON_RESTRICTIVE_PARAMS = {"fields", "startindex", "limit", "recursive", "parentid"}
GLOB_CHARACTERS = "*?["


def _split_patterns(value):
    if value is None:
        return []
    return [pattern.strip() for pattern in str(value).split("|") if pattern.strip()]


def _contains_search_term(pattern):
    """Return text for a simple *text* pattern, otherwise None."""
    if not isinstance(pattern, str) or len(pattern) < 3:
        return None
    if not (pattern.startswith("*") and pattern.endswith("*")):
        return None
    term = pattern[1:-1]
    if not term or any(character in term for character in GLOB_CHARACTERS):
        return None
    return term


def _exact_values(value):
    patterns = _split_patterns(value)
    if not patterns or any(any(character in pattern for character in GLOB_CHARACTERS) for pattern in patterns):
        return None
    return patterns


def _add_genre_prefilter(params, filters):
    if any(key.casefold() == "genres" for key in params):
        return
    all_values = _exact_values(filters.get("genresall"))
    any_values = _exact_values(filters.get("genresany"))
    if all_values:
        params["Genres"] = max(all_values, key=len)
    elif any_values:
        params["Genres"] = "|".join(any_values)


def _name_queries(base_params, filters):
    if any(key.casefold() == "searchterm" for key in base_params):
        return (dict(base_params),)

    mandatory_terms = []
    name_term = _contains_search_term(filters.get("name"))
    if name_term:
        mandatory_terms.append(name_term)
    for pattern in _split_patterns(filters.get("nameall")):
        term = _contains_search_term(pattern)
        if term:
            mandatory_terms.append(term)

    if mandatory_terms:
        query = dict(base_params)
        query["SearchTerm"] = max(mandatory_terms, key=len)
        return (query,)

    any_patterns = _split_patterns(filters.get("nameany"))
    any_terms = [_contains_search_term(pattern) for pattern in any_patterns]
    if any_patterns and all(any_terms):
        queries = []
        for term in dict.fromkeys(any_terms):
            query = dict(base_params)
            query["SearchTerm"] = term
            queries.append(query)
        return tuple(queries)

    return (dict(base_params),)


def plan_query(rules):
    """Build safe native queries while retaining exact compound local checks."""
    params = dict(rules["params"])
    filters = rules["filters"]
    _add_genre_prefilter(params, filters)
    queries = _name_queries(params, filters)

    server_keys = {
        key.casefold()
        for query in queries
        for key in query
        if key.casefold() not in NON_RESTRICTIVE_PARAMS
    }
    strategy = (
        "server-side filtered query" if server_keys
        else "full paginated fallback scan"
    )
    return QueryPlan(
        params=queries[0],
        queries=queries,
        strategy=strategy,
        server_filter_count=len(server_keys),
        local_verifier_count=len(filters),
    )
