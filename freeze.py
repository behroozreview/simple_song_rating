#!/usr/bin/env python3
"""Freeze the Song Rating public view into a static site for GitHub Pages."""
import os
import sqlite3
import tempfile
import warnings

from flask_frozen import Freezer, MissingURLGeneratorWarning

import app as app_module
from app import app, init_db

# ---------------------------------------------------------------------------
# Use a temporary database so the build doesn't touch production data
# ---------------------------------------------------------------------------

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
DB_PATH = _tmp_db.name
app_module.DATABASE = DB_PATH

# ---------------------------------------------------------------------------
# Frozen-Flask configuration
# ---------------------------------------------------------------------------

app.config["FREEZER_DESTINATION"] = os.path.join(os.path.dirname(__file__), "_site")
app.config["FREEZER_RELATIVE_URLS"] = True
app.config["FREEZER_REMOVE_EXTRA_FILES"] = True
app.config["STATIC_MODE"] = True
app.config["GITHUB_REPO"] = os.environ.get("GITHUB_REPOSITORY", "behroozreview/simple_song_rating")

freezer = Freezer(app, with_no_argument_rules=False, log_url_for=False)


@freezer.register_generator
def admin():
    """Generate the default admin view (read-only, auth-gated on GitHub Pages)."""
    yield {}


@freezer.register_generator
def index():
    """Generate the public view for common sort combinations."""
    yield {}
    yield {"sort": "name", "order": "asc"}
    yield {"sort": "name", "order": "desc"}
    yield {"sort": "rate", "order": "asc"}
    yield {"sort": "rate", "order": "desc"}
    yield {"sort": "date_added", "order": "asc"}
    yield {"sort": "date_added", "order": "desc"}


def seed_sample_data():
    """Populate the temporary database with sample songs."""
    conn = sqlite3.connect(DB_PATH)
    sample_songs = [
        ("Bohemian Rhapsody", 9, "https://www.youtube.com/watch?v=fJ9rUzIMcZQ"),
        ("Hotel California", 8, "https://www.youtube.com/watch?v=EqPtz5qN7HM"),
        ("Stairway to Heaven", 9, None),
        ("Smells Like Teen Spirit", 8, "https://www.youtube.com/watch?v=hTWKbfoikeg"),
        ("Imagine", 7, None),
        ("Purple Haze", 6, None),
        ("Billie Jean", 7, "https://www.youtube.com/watch?v=Zi_XLOBDo_Y"),
        ("Sweet Child O Mine", 8, None),
    ]
    conn.executemany(
        "INSERT INTO songs (name, rate, url) VALUES (?, ?, ?)",
        sample_songs,
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    # Suppress expected warnings for admin endpoints not included in the static build
    warnings.filterwarnings("ignore", category=MissingURLGeneratorWarning)

    init_db()
    seed_sample_data()

    print("Freezing public view to _site/ ...")
    try:
        freezer.freeze()
    finally:
        os.unlink(DB_PATH)
    print("Done. Static site is in _site/")
