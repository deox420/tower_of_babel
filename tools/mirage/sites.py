"""Static, version-pinned site catalogs for each MIRAGE profile.

The catalog is a Python module rather than a JSON blob on purpose:

  * PyInstaller picks the module up automatically; no
    ``package_data`` row is needed.
  * The literal lives in one place so reviewers can see the entire
    public catalog without diffing a separate data file.
  * The values are bare tuples to minimise import overhead.

Each entry is ``(host, path_template, zipf_rank)``.  Lower
``zipf_rank`` -> more frequent.  The path template currently has
no substitutions; ``{tok}`` is reserved for a future variant that
draws Wikipedia article slugs from a per-locale list (out of scope
for Phase 5).

All hosts are public, well-known, plausibly common destinations.
The catalogs are intentionally small (30-60 entries each); the
goal is "looks ordinary", not "covers the entire web".
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Profile catalogs.
# ---------------------------------------------------------------------------

PROFILE_SITES: dict[str, tuple[tuple[str, str, int], ...]] = {
    "office_worker": (
        ("en.wikipedia.org",     "/wiki/Main_Page",       1),
        ("duckduckgo.com",       "/",                     2),
        ("www.bbc.com",          "/news",                 3),
        ("www.reuters.com",      "/",                     4),
        ("weather.com",          "/",                     5),
        ("www.google.com",       "/",                     6),
        ("outlook.live.com",     "/",                     7),
        ("www.bing.com",         "/",                     8),
        ("www.openstreetmap.org", "/",                    9),
        ("calendar.google.com",  "/",                    10),
        ("translate.google.com", "/",                    11),
        ("www.linkedin.com",     "/",                    12),
        ("www.indeed.com",       "/",                    13),
        ("www.wsj.com",          "/",                    14),
        ("www.ft.com",           "/",                    15),
        ("apnews.com",           "/",                    16),
        ("www.npr.org",          "/",                    17),
        ("docs.google.com",      "/",                    18),
        ("zoom.us",              "/",                    19),
        ("www.dropbox.com",      "/",                    20),
    ),
    "developer": (
        ("github.com",                 "/",              1),
        ("stackoverflow.com",          "/",              2),
        ("developer.mozilla.org",      "/en-US/",        3),
        ("pypi.org",                   "/",              4),
        ("docs.python.org",            "/3/",            5),
        ("news.ycombinator.com",       "/",              6),
        ("www.npmjs.com",              "/",              7),
        ("crates.io",                  "/",              8),
        ("docs.rs",                    "/",              9),
        ("go.dev",                     "/",             10),
        ("kubernetes.io",              "/docs/home/",   11),
        ("docs.docker.com",            "/",             12),
        ("docs.aws.amazon.com",        "/",             13),
        ("cloud.google.com",           "/docs",         14),
        ("learn.microsoft.com",        "/en-us/",       15),
        ("readthedocs.org",            "/",             16),
        ("manpages.debian.org",        "/",             17),
        ("man7.org",                   "/linux/man-pages/", 18),
        ("www.rust-lang.org",          "/",             19),
        ("www.postgresql.org",         "/docs/",        20),
        ("redis.io",                   "/docs/",        21),
        ("nginx.org",                  "/en/docs/",     22),
        ("www.gnu.org",                "/software/bash/manual/", 23),
        ("git-scm.com",                "/docs",         24),
        ("docs.github.com",            "/",             25),
    ),
    "casual_browser": (
        ("www.reddit.com",       "/",                    1),
        ("www.youtube.com",      "/",                    2),
        ("en.wikipedia.org",     "/wiki/Main_Page",      3),
        ("www.bbc.com",          "/news",                4),
        ("www.imdb.com",         "/",                    5),
        ("twitter.com",          "/",                    6),
        ("medium.com",           "/",                    7),
        ("www.theguardian.com",  "/",                    8),
        ("www.cnn.com",          "/",                    9),
        ("www.aljazeera.com",    "/",                   10),
        ("www.spotify.com",      "/",                   11),
        ("www.netflix.com",      "/",                   12),
        ("www.tiktok.com",       "/",                   13),
        ("www.instagram.com",    "/",                   14),
        ("www.pinterest.com",    "/",                   15),
        ("www.tumblr.com",       "/",                   16),
        ("substack.com",         "/",                   17),
        ("www.vox.com",          "/",                   18),
        ("www.theverge.com",     "/",                   19),
        ("arstechnica.com",      "/",                   20),
    ),
    "researcher": (
        ("en.wikipedia.org",        "/wiki/Main_Page",                1),
        ("scholar.google.com",      "/",                              2),
        ("arxiv.org",               "/",                              3),
        ("www.semanticscholar.org", "/",                              4),
        ("www.jstor.org",           "/",                              5),
        ("www.ncbi.nlm.nih.gov",    "/pubmed/",                       6),
        ("doaj.org",                "/",                              7),
        ("plato.stanford.edu",      "/",                              8),
        ("www.britannica.com",      "/",                              9),
        ("www.gutenberg.org",       "/",                             10),
        ("archive.org",             "/",                             11),
        ("www.nature.com",          "/",                             12),
        ("www.sciencemag.org",      "/",                             13),
        ("www.cell.com",            "/",                             14),
        ("openlibrary.org",         "/",                             15),
        ("www.zotero.org",          "/",                             16),
        ("www.researchgate.net",    "/",                             17),
        ("dl.acm.org",              "/",                             18),
        ("ieeexplore.ieee.org",     "/",                             19),
        ("www.loc.gov",             "/",                             20),
    ),
}


def get_catalog(sites_key: str) -> tuple[tuple[str, str, int], ...]:
    try:
        return PROFILE_SITES[sites_key]
    except KeyError as e:
        raise ValueError(
            f"unknown MIRAGE site catalog {sites_key!r}; "
            f"known: {sorted(PROFILE_SITES)}"
        ) from e


__all__ = ["PROFILE_SITES", "get_catalog"]
