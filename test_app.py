"""
Tests for the Song Rating application.
"""
import io
import os
import sqlite3
import tempfile

import pytest

# Point the app at a temporary database before importing
os.environ.setdefault("SECRET_KEY", "test-secret")

import app as app_module
from app import app


@pytest.fixture()
def db_path(tmp_path):
    """Return the path to a fresh temporary database."""
    path = str(tmp_path / "test_songs.db")
    original = app_module.DATABASE
    app_module.DATABASE = path
    app_module.init_db()
    yield path
    app_module.DATABASE = original


@pytest.fixture()
def client(db_path):
    """Flask test client with a fresh database."""
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret"
    with app.test_client() as c:
        with app.app_context():
            yield c


# ---------------------------------------------------------------------------
# Public view
# ---------------------------------------------------------------------------

class TestPublicView:
    def test_empty_list(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert b"No songs yet" in r.data

    def test_song_appears(self, client):
        client.post(
            "/admin/add",
            data={"name": "Test Song", "rate": "7", "url": ""},
        )
        r = client.get("/")
        assert b"Test Song" in r.data

    def test_sorting_by_name(self, client):
        client.post("/admin/add", data={"name": "Zebra", "rate": "5", "url": ""})
        client.post("/admin/add", data={"name": "Alpha", "rate": "8", "url": ""})
        r = client.get("/?sort=name&order=asc")
        assert r.status_code == 200
        assert b"Alpha" in r.data
        assert b"Zebra" in r.data

    def test_sorting_by_rate(self, client):
        r = client.get("/?sort=rate&order=desc")
        assert r.status_code == 200

    def test_sorting_by_date(self, client):
        r = client.get("/?sort=date_added&order=asc")
        assert r.status_code == 200

    def test_invalid_sort_falls_back(self, client):
        r = client.get("/?sort=invalid_col&order=desc")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Admin view
# ---------------------------------------------------------------------------

class TestAdminView:
    def test_admin_empty(self, client):
        r = client.get("/admin")
        assert r.status_code == 200
        assert b"No songs yet" in r.data

    def test_admin_shows_songs(self, client):
        client.post("/admin/add", data={"name": "My Song", "rate": "6", "url": ""})
        r = client.get("/admin")
        assert b"My Song" in r.data

    def test_admin_sorting(self, client):
        r = client.get("/admin?sort=rate&order=asc")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Add song
# ---------------------------------------------------------------------------

class TestAddSong:
    def test_get_form(self, client):
        r = client.get("/admin/add")
        assert r.status_code == 200
        assert b"Add Song" in r.data

    def test_add_valid(self, client):
        r = client.post(
            "/admin/add",
            data={"name": "Bohemian Rhapsody", "rate": "9", "url": "https://example.com"},
            follow_redirects=True,
        )
        assert r.status_code == 200
        assert b"Bohemian Rhapsody" in r.data

    def test_add_no_url(self, client):
        r = client.post(
            "/admin/add",
            data={"name": "No URL Song", "rate": "5", "url": ""},
            follow_redirects=True,
        )
        assert r.status_code == 200
        assert b"No URL Song" in r.data

    def test_add_missing_name(self, client):
        r = client.post(
            "/admin/add",
            data={"name": "", "rate": "5", "url": ""},
            follow_redirects=True,
        )
        assert b"Song name is required" in r.data

    def test_add_invalid_rate_too_high(self, client):
        r = client.post(
            "/admin/add",
            data={"name": "Bad Song", "rate": "10", "url": ""},
            follow_redirects=True,
        )
        assert b"Rate must be between 0 and 9" in r.data

    def test_add_invalid_rate_negative(self, client):
        r = client.post(
            "/admin/add",
            data={"name": "Bad Song", "rate": "-1", "url": ""},
            follow_redirects=True,
        )
        assert b"Rate must be between 0 and 9" in r.data

    def test_add_non_numeric_rate(self, client):
        r = client.post(
            "/admin/add",
            data={"name": "Bad Song", "rate": "abc", "url": ""},
            follow_redirects=True,
        )
        assert b"Rate must be a number" in r.data


# ---------------------------------------------------------------------------
# Edit song
# ---------------------------------------------------------------------------

class TestEditSong:
    def _add_song(self, client):
        client.post(
            "/admin/add",
            data={"name": "Original", "rate": "5", "url": ""},
        )

    def test_edit_get(self, client):
        self._add_song(client)
        r = client.get("/admin/edit/1")
        assert r.status_code == 200
        assert b"Original" in r.data

    def test_edit_not_found(self, client):
        r = client.get("/admin/edit/999", follow_redirects=True)
        assert b"Song not found" in r.data

    def test_edit_post_valid(self, client):
        self._add_song(client)
        r = client.post(
            "/admin/edit/1",
            data={"name": "Updated", "rate": "8", "url": "https://example.com"},
            follow_redirects=True,
        )
        assert b"Updated" in r.data

    def test_edit_post_validation(self, client):
        self._add_song(client)
        r = client.post(
            "/admin/edit/1",
            data={"name": "", "rate": "5", "url": ""},
            follow_redirects=True,
        )
        assert b"Song name is required" in r.data


# ---------------------------------------------------------------------------
# Delete song
# ---------------------------------------------------------------------------

class TestDeleteSong:
    def test_delete_existing(self, client):
        client.post("/admin/add", data={"name": "To Delete", "rate": "3", "url": ""})
        r = client.post("/admin/delete/1", follow_redirects=True)
        assert r.status_code == 200
        # After deletion, the table should be empty (flash msg may still show the name)
        assert b"No songs yet" in r.data

    def test_delete_nonexistent(self, client):
        r = client.post("/admin/delete/999", follow_redirects=True)
        assert b"Song not found" in r.data


# ---------------------------------------------------------------------------
# CSV upload
# ---------------------------------------------------------------------------

class TestCsvUpload:
    def test_get_upload_page(self, client):
        r = client.get("/admin/upload")
        assert r.status_code == 200
        assert b"CSV" in r.data

    def test_upload_valid_csv(self, client):
        csv_data = b"name,rate,url\nBohemian Rhapsody,9,https://example.com\nHotel California,8,\n"
        r = client.post(
            "/admin/upload",
            data={"csv_file": (io.BytesIO(csv_data), "songs.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert r.status_code == 200
        assert b"2 added" in r.data

    def test_upload_csv_with_bom(self, client):
        csv_data = b"\xef\xbb\xbfname,rate,url\nTest Song,7,\n"
        r = client.post(
            "/admin/upload",
            data={"csv_file": (io.BytesIO(csv_data), "songs.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert b"1 added" in r.data

    def test_upload_no_file(self, client):
        r = client.post(
            "/admin/upload",
            data={},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert b"No file selected" in r.data

    def test_upload_wrong_extension(self, client):
        r = client.post(
            "/admin/upload",
            data={"csv_file": (io.BytesIO(b"data"), "songs.txt")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert b"CSV file" in r.data

    def test_upload_missing_columns(self, client):
        csv_data = b"title,score\nBad Song,5\n"
        r = client.post(
            "/admin/upload",
            data={"csv_file": (io.BytesIO(csv_data), "bad.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert b"name" in r.data.lower()

    def test_upload_skips_invalid_rows(self, client):
        csv_data = b"name,rate,url\nGood Song,8,\n,5,\nBad Rate,15,\nNot A Number,abc,\n"
        r = client.post(
            "/admin/upload",
            data={"csv_file": (io.BytesIO(csv_data), "songs.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert b"1 added" in r.data
        assert b"3 skipped" in r.data
