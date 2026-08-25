import configparser, fnmatch, os, sys
from loguru import logger
from variables import CONFIG_PATH, config_behaviour_rules, items_param_rules


def config_bool(value, default=False):
    if value is None:
        return default
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off", ""}:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def is_photo(item):
    """Use Emby's basic MediaType first, with Type as the documented fallback."""
    media_type = str(item.get("MediaType") or "").strip().casefold()
    item_type = str(item.get("Type") or "").strip().casefold()
    return media_type == "photo" or item_type == "photo"


def is_video(item):
    """Classify playable video from Emby's MediaType or documented video Type."""
    media_type = str(item.get("MediaType") or "").strip().casefold()
    item_type = str(item.get("Type") or "").strip().casefold()
    video_types = {"video", "movie", "episode", "trailer", "adultvideo", "musicvideo"}
    return media_type == "video" or item_type in video_types


def content_kind(item):
    """Return the mutually exclusive EDCM inclusion category for an Emby item."""
    if item.get("IsFolder") is True:
        return "folder"
    if is_photo(item):
        return "photo"
    if is_video(item):
        return "video"
    return "other"

def split_patterns(value):
    return [pattern.strip() for pattern in str(value).split("|") if pattern.strip()]


def _matches_any(values, patterns):
    return any(
        fnmatch.fnmatch(str(value).casefold(), pattern.casefold())
        for pattern in patterns
        for value in values
        if value not in (None, "")
    )


def determine_match(item, rule_set, rules):
    compound_rules = {
        "nameany": ("name", "any"),
        "nameall": ("name", "all"),
        "excludename": ("name", "exclude"),
        "genresany": ("genres", "any"),
        "genresall": ("genres", "all"),
        "excludegenres": ("genres", "exclude"),
    }
    for key, pattern in rules.items():
        compound = compound_rules.get(key)
        if compound:
            field, mode = compound
            values = item.get(field, [])
            if not isinstance(values, list):
                values = [values]
            patterns = split_patterns(pattern)
            if not patterns:
                return False
            if mode == "any" and not _matches_any(values, patterns):
                return False
            if mode == "all" and not all(_matches_any(values, [value]) for value in patterns):
                return False
            if mode == "exclude" and _matches_any(values, patterns):
                return False
            continue
        values = item.get(key, [])
        if not isinstance(values, list):
            values = [values]
        flat = []
        for value in values:
            flat.extend(value if isinstance(value, list) else [value])
        if not any(fnmatch.fnmatch(str(value).casefold(), pattern.casefold()) for value in flat if value not in (None, "")):
            return False
    return True

def determine_rule_type(rule_set):
    result = {"params": {}, "filters": {}, "behaviour": {}}
    params = {item.lower(): item for item in items_param_rules}
    behaviour = {item.lower() for item in config_behaviour_rules}
    for key, value in rule_set:
        normalized = key.lower()
        if normalized in params: result["params"][params[normalized]] = value
        elif normalized in behaviour: result["behaviour"][normalized] = value
        else: result["filters"][normalized] = value
    return result

def load_config():
    if not os.path.exists(CONFIG_PATH):
        logger.warning("Config file not found at {}; generating it", CONFIG_PATH)
        os.makedirs(os.path.dirname(CONFIG_PATH) or ".", exist_ok=True)
        try:
            with open(os.path.join(os.path.dirname(__file__), "config.ini.tmpl"), encoding="utf-8") as source, open(CONFIG_PATH, "w", encoding="utf-8") as target:
                target.write(source.read())
        except OSError as exc:
            logger.error("Failed to create config file: {}", exc); sys.exit(1)
    config = configparser.ConfigParser()
    try:
        with open(CONFIG_PATH, encoding="utf-8") as stream: config.read_file(stream)
    except (OSError, configparser.Error) as exc:
        logger.error("Failed to read config file: {}", exc); sys.exit(1)
    logger.success("Found collection rule sets: {}", ", ".join(config.sections()) or "none")
    return config

def map_content_data(item):
    return {"name":[item.get("Name","")], "id":item.get("Id",""), "datecreated":[item.get("DateCreated","")],
        "overview":[item.get("Overview","")], "runtimeticks":[item.get("RunTimeTicks","")], "isfolder":[item.get("IsFolder","")],
        "parentid":[item.get("ParentId","")], "type":[item.get("Type","")], "enddate":[item.get("EndDate","")],
        "genres":item.get("Genres",[]) or [], "people":[x.get("Name","") for x in item.get("People",[])],
        "studios":[x.get("Name","") for x in item.get("Studios",[])], "path":[item.get("Path","")]}
