# Emby Dynamic Collections Manager

EDCM synchronizes Emby collections from INI rules. This fork targets Emby Server **4.10.0.27 beta**, uses the current `/emby` REST endpoints, recursively scans nested library content, and adds and removes collection members on every successful scan.

This repository is a fork and modernization of the original EDCM project created by [steveharsant](https://github.com/steveharsant).

A failed library/API request leaves the affected collection unchanged. Logs report startup, authentication, library names, aggregate item/match counts, collection creation and add/remove counts; they do not log matching item names.

## Docker / Unraid

Create a persistent host directory for `/config`, then run:

```bash
docker build -t edcm:local .
docker run -d \
  --name edcm \
  --restart unless-stopped \
  -e EMBY_ADDRESS=<<emby-ip-address-here>> \
  -e EMBY_PORT=8096 \
  -e EMBY_TOKEN=<<your-emby-api-token-here>> \
  -e EDCM_USE_SSL=false \
  -e EDCM_SCAN_INTERVAL=600 \
  -v <</path/to/config/dir>>:/config \
  edcm:local
```

In Unraid, add a Docker container using the built/published image, map `/mnt/user/appdata/edcm` to `/config`, and add the environment variables above. With a reverse proxy or native HTTPS, set `EDCM_USE_SSL=true` and the corresponding port.

| Variable | Default | Required |
|---|---:|---|
| `EMBY_ADDRESS` | — | yes |
| `EMBY_TOKEN` | — | yes |
| `EMBY_PORT` | `8096` | no |
| `EDCM_USE_SSL` | `false` | no |
| `EDCM_CONFIG_PATH` | `/config/config.ini` | no |
| `EDCM_SCAN_INTERVAL` | `600` | no |
| `EDCM_DEBUG` | `false` | no |

Boolean variables accept true values `true`, `1`, `yes`, and `on` (case-insensitive). Other values, including `false`, use HTTP/disable debug.

On first start EDCM creates `/config/config.ini`. Existing section/rule syntax remains compatible.

## Rules

A section name is the collection name. API query parameters such as `IncludeItemTypes` and `MinCommunityRating` are sent to Emby. Other keys filter returned item fields with case-insensitive shell wildcards. `Library` is an EDCM behavior key that restricts the rule to one exact Emby library name. `DryRun=true` scans and counts without changing Emby.

```ini
[Highly Rated HBO Series]
Library = TV Shows
IncludeItemTypes = Series
Studios = HBO*
MinCommunityRating = 8

[Family Vacation Videos]
Library = Home Videos & Photos
Type = Video
Name = *vacation*
IncludeVideo = true
IncludeFolders = false
IncludePhotos = false

[Comedies]
Genres = comedy
```

Home Videos & Photos is supported. `Name` matches the Emby `Name` field, which Emby derives from the media filename where applicable.

`IncludeVideo`, `IncludeFolders`, and `IncludePhotos` are independent EDCM behavior options. Their defaults are `true`, `false`, and `false`, respectively, producing normal video-only collections. Matching folders require `IncludeFolders=true`. Photos are detected from Emby's `MediaType` (preferred) or `Type`, never from filenames or extensions, and require `IncludePhotos=true`. Playable Home Videos are classified as video. These options are applied locally and are not sent to Emby. A rule that disables all three is invalid and will not scan or synchronize.

```ini
[Test Home Videos]
Name = *harbor*
IncludeVideo = true
IncludeFolders = false
IncludePhotos = false
DryRun = false
```

Photo-only, folder-only, and mixed examples:

```ini
[Harbor Photos]
Name = *harbor*
IncludeVideo = false
IncludeFolders = false
IncludePhotos = true

[Harbor Folders]
Name = *harbor*
IncludeVideo = false
IncludeFolders = true
IncludePhotos = false

[Harbor Everything]
Name = *harbor*
IncludeVideo = true
IncludeFolders = true
IncludePhotos = true
```

A successful non-dry-run scan fully synchronizes membership: new matches are added and items that no longer match are removed. Do not manually manage members of an EDCM-owned collection unless you expect the next scan to reconcile them.

## Development and mocked tests

```bash
python -m pip install -r src/requirements.txt -r requirements-dev.txt
PYTHONPATH=src pytest -q
```

Tests mock the Emby 4.10 response shapes and do not require or inspect an Emby database. The implementation uses the documented operations:

- `GET /Library/MediaFolders`
- `GET /Items` with `ParentId` and `Recursive=true`
- `POST /Collections`
- `POST /Collections/{Id}/Items`
- `POST /Collections/{Id}/Items/Delete`

See the [Emby REST API documentation](https://dev.emby.media/reference/RestAPI.html) and [CollectionService](https://dev.emby.media/reference/RestAPI/CollectionService.html).

### Large libraries and pagination

Recursive scans use Emby's paginated Items API and stream rule matching one page at a time. Only matching item IDs are retained across pages. If any page or selected library fails, that rule's collection is left unchanged.

EDCM prefers server-side candidate filtering. A simple contains rule such as `Name = *harbor*` is sent to Emby as `SearchTerm=harbor`, including when all libraries are selected. EDCM then applies the original wildcard locally to every candidate, preserving exact `fnmatch` behavior. Rules without a safe server-side representation use the full paginated fallback scan.

### Rule execution

Multiple configured rules are combined with AND semantics. EDCM pushes every safe condition into the Emby query, paginates the reduced result, and then runs any required local wildcard verifiers. A local-only rule does not prevent other native filters in the same rule set from narrowing the query.

| Rule field | Execution | INI example | Notes |
|---|---|---|---|
| `Name = *text*` | Server-side + local verification | `Name = *vacation*` | Uses `SearchTerm=vacation`; simple contains patterns only |
| Other `Name` wildcard forms | Local fallback | `Name = Vacation 2024*` | Uses a hybrid plan when another server filter is present |
| `NameAny` | Server-side + local verification | `NameAny = *vacation* \| *boat* \| *beach*` | Matches when at least one pattern matches; unions deduplicated `SearchTerm` queries |
| `NameAll` | Server-side + local verification | `NameAll = *vacation* \| *beach*` | Every pattern must match in any order; one mandatory term narrows candidates |
| `ExcludeName` | Local verification | `ExcludeName = *surf* \| *trailer*` | Rejects an item when any pattern matches |
| `Genres` | Server-side | `Genres = Documentary` | Native genre filter |
| `GenresAny` | Server-side + local verification | `GenresAny = Documentary \| Family` | At least one genre must match; exact values use native `Genres` narrowing |
| `GenresAll` | Server-side + local verification | `GenresAll = Documentary \| Family` | Every genre must match; one exact genre narrows candidates |
| `ExcludeGenres` | Local verification | `ExcludeGenres = Archive \| Horror` | Rejects an item when any genre matches |
| `Tags` | Server-side | `Tags = Family` | Native tag filter |
| `ExcludeTags` | Server-side | `ExcludeTags = Archive` | Excludes matching tags |
| `Years` | Server-side | `Years = 2024` | Multiple years: `Years = 2023,2024` |
| `OfficialRatings` | Server-side | `OfficialRatings = PG-13` | Native official-rating filter |
| `MinCommunityRating` | Server-side | `MinCommunityRating = 7` | Minimum community rating |
| `MinCriticRating` | Server-side | `MinCriticRating = 70` | Minimum critic rating |
| `Containers` | Server-side | `Containers = mkv` | Multiple values: `Containers = mkv,mp4` |
| `VideoCodecs` | Server-side | `VideoCodecs = hevc` | Native video-codec filter |
| `AudioCodecs` | Server-side | `AudioCodecs = aac` | Native audio-codec filter |
| `SubtitleCodecs` | Server-side | `SubtitleCodecs = srt` | Native subtitle-codec filter |
| `VideoTypes` | Server-side | `VideoTypes = VideoFile` | Examples include `VideoFile`, `Dvd`, `Bluray`, and `Iso` |
| `IsHD` | Server-side | `IsHD = true` | HD status |
| `Is3D` | Server-side | `Is3D = false` | 3D status |
| `IsFavorite` | Server-side | `IsFavorite = true` | Favorite status |
| `IsPlayed` | Server-side | `IsPlayed = false` | Played status |
| `IsLocked` | Server-side | `IsLocked = false` | Metadata lock status |
| `HasSubtitles` | Server-side | `HasSubtitles = true` | Requires subtitles |
| `HasTrailer` | Server-side | `HasTrailer = false` | Trailer presence |
| `HasOverview` | Server-side | `HasOverview = true` | Overview presence |
| `HasImdbId` | Server-side | `HasImdbId = true` | IMDb provider ID presence |
| `HasTmdbId` | Server-side | `HasTmdbId = true` | TMDb provider ID presence |
| `HasTvdbId` | Server-side | `HasTvdbId = true` | TVDB provider ID presence |
| `MinPremiereDate` | Server-side | `MinPremiereDate = 2024-01-01` | ISO date lower bound |
| `MaxPremiereDate` | Server-side | `MaxPremiereDate = 2024-12-31` | ISO date upper bound |
| `MinDateLastSaved` | Server-side | `MinDateLastSaved = 2026-01-01` | ISO date lower bound |
| `Path` | Local fallback | `Path = *Vacation*` | Preserves local wildcard semantics |

Combined example:

```ini
[2024 Family Vacation Videos]
Library = Home Videos & Photos
Name = *vacation*
Genres = Documentary
Tags = Family
ExcludeTags = Archive
Years = 2024
MinCommunityRating = 7
Containers = mkv,mp4
VideoCodecs = hevc
HasSubtitles = true
MinPremiereDate = 2024-01-01
MaxPremiereDate = 2024-12-31
IncludeVideo = true
IncludeFolders = false
IncludePhotos = false
DryRun = false
```

Compound name and genre example:

```ini
[Family Water Trips]
NameAny = *vacation* | *boat* | *beach*
NameAll = *family*
ExcludeName = *surf* | *trailer*
GenresAny = Documentary | Travel
GenresAll = Family
ExcludeGenres = Archive | Horror
IncludeVideo = true
IncludeFolders = false
IncludePhotos = false
DryRun = false
```

`NameAny` and `GenresAny` require at least one listed pattern. `NameAll` and `GenresAll` require every listed pattern. `ExcludeName` and `ExcludeGenres` reject matches containing any listed pattern. Different rule groups combine with AND semantics. The `|` character separates patterns; matching remains case-insensitive and uses EDCM wildcard semantics.

Planner logs disclose counts but never filter values or media details:

```text
Rule set '2024 Family Vacation Videos' execution strategy: server-side filtered query
Planner: 4 server-side filters, 1 local verifier
```

| Variable | Default | Purpose |
|---|---:|---|
| `EDCM_PAGE_SIZE` | `2000` | Items requested per recursive page |
| `EDCM_HTTP_TIMEOUT` | `30` | Per-request safety timeout in seconds |

For very constrained servers, reduce `EDCM_PAGE_SIZE`. Increasing the timeout is not normally necessary because pagination bounds each response. Progress logs contain library names and aggregate counts only, such as `Scanning Storage_2: 40000 / 174343`.

## Development Notes

Portions of this fork were developed with assistance from AI coding tools, including OpenAI Codex, for code generation, refactoring, testing, and documentation. Changes were reviewed and tested against the project's intended Emby integration and Docker environment.
