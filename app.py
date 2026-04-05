import os
import csv
import io
import sqlite3
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    g,
)

# ---------------------------------------------------------------------------
# Safe ORDER BY helpers – prevents SQL injection via f-string interpolation
# ---------------------------------------------------------------------------

_SORT_COLUMNS = {
    "name": "name",
    "rate": "rate",
    "date_added": "date_added",
}
_ORDER_DIRS = {"asc": "ASC", "desc": "DESC"}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")

DATABASE = os.path.join(os.path.dirname(__file__), "songs.db")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_sort_params(sort_arg, order_arg):
    """Return validated (sort_col, order_dir) from request args."""
    sort = _SORT_COLUMNS.get(sort_arg, "date_added")
    order = _ORDER_DIRS.get(order_arg, "DESC")
    return sort, order


def _make_toggle(sort, order_dir):
    """Return a callable that gives the next sort direction for a column."""
    def toggle(col):
        col_key = _SORT_COLUMNS.get(col, col)
        if col_key == sort:
            return "asc" if order_dir == "DESC" else "desc"
        return "desc"
    return toggle


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS songs (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT    NOT NULL,
            rate      REAL    NOT NULL DEFAULT 0,
            url       TEXT,
            date_added DATETIME DEFAULT (datetime('now'))
        )
        """
    )
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Public view
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    sort, order_dir = _safe_sort_params(
        request.args.get("sort", "date_added"),
        request.args.get("order", "desc"),
    )

    db = get_db()
    songs = db.execute(
        "SELECT * FROM songs ORDER BY " + sort + " " + order_dir
    ).fetchall()

    return render_template(
        "public.html",
        songs=songs,
        sort=sort,
        order=order_dir.lower(),
        toggle=_make_toggle(sort, order_dir),
    )


# ---------------------------------------------------------------------------
# Admin views
# ---------------------------------------------------------------------------

@app.route("/admin/")
def admin():
    sort, order_dir = _safe_sort_params(
        request.args.get("sort", "date_added"),
        request.args.get("order", "desc"),
    )

    db = get_db()
    songs = db.execute(
        "SELECT * FROM songs ORDER BY " + sort + " " + order_dir
    ).fetchall()

    return render_template(
        "admin.html",
        songs=songs,
        sort=sort,
        order=order_dir.lower(),
        toggle=_make_toggle(sort, order_dir),
    )


@app.route("/admin/add", methods=["GET", "POST"])
def add_song():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        rate = request.form.get("rate", "0").strip()
        url = request.form.get("url", "").strip()

        errors = []
        if not name:
            errors.append("Song name is required.")
        try:
            rate_val = int(rate)
            if not (0 <= rate_val <= 9):
                errors.append("Rate must be between 0 and 9.")
        except ValueError:
            errors.append("Rate must be a number.")
            rate_val = 0

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("add_song.html", name=name, rate=rate, url=url)

        db = get_db()
        db.execute(
            "INSERT INTO songs (name, rate, url) VALUES (?, ?, ?)",
            (name, rate_val, url or None),
        )
        db.commit()
        flash(f'Song "{name}" added successfully.', "success")
        return redirect(url_for("admin"))

    return render_template("add_song.html", name="", rate="", url="")


@app.route("/admin/edit/<int:song_id>", methods=["GET", "POST"])
def edit_song(song_id):
    db = get_db()
    song = db.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()
    if song is None:
        flash("Song not found.", "danger")
        return redirect(url_for("admin"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        rate = request.form.get("rate", "0").strip()
        url = request.form.get("url", "").strip()

        errors = []
        if not name:
            errors.append("Song name is required.")
        try:
            rate_val = int(rate)
            if not (0 <= rate_val <= 9):
                errors.append("Rate must be between 0 and 9.")
        except ValueError:
            errors.append("Rate must be a number.")
            rate_val = 0

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("edit_song.html", song=song, name=name, rate=rate, url=url)

        db.execute(
            "UPDATE songs SET name = ?, rate = ?, url = ? WHERE id = ?",
            (name, rate_val, url or None, song_id),
        )
        db.commit()
        flash(f'Song "{name}" updated successfully.', "success")
        return redirect(url_for("admin"))

    return render_template(
        "edit_song.html",
        song=song,
        name=song["name"],
        rate=song["rate"],
        url=song["url"] or "",
    )


@app.route("/admin/delete/<int:song_id>", methods=["POST"])
def delete_song(song_id):
    db = get_db()
    song = db.execute("SELECT name FROM songs WHERE id = ?", (song_id,)).fetchone()
    if song:
        db.execute("DELETE FROM songs WHERE id = ?", (song_id,))
        db.commit()
        flash(f'Song "{song["name"]}" deleted.', "success")
    else:
        flash("Song not found.", "danger")
    return redirect(url_for("admin"))


@app.route("/admin/upload", methods=["GET", "POST"])
def upload_csv():
    if request.method == "POST":
        file = request.files.get("csv_file")
        if not file or file.filename == "":
            flash("No file selected.", "danger")
            return redirect(url_for("upload_csv"))

        if not file.filename.lower().endswith(".csv"):
            flash("Please upload a CSV file.", "danger")
            return redirect(url_for("upload_csv"))

        stream = io.StringIO(file.stream.read().decode("utf-8-sig"), newline=None)
        reader = csv.DictReader(stream)

        required_fields = {"name", "rate"}
        if not required_fields.issubset({f.lower().strip() for f in (reader.fieldnames or [])}):
            flash(
                "CSV must contain at least 'name' and 'rate' columns.",
                "danger",
            )
            return redirect(url_for("upload_csv"))

        db = get_db()
        added = 0
        skipped = 0
        for row in reader:
            # Normalise keys to lowercase; guard against None values
            row = {k.lower().strip(): (v.strip() if v else "") for k, v in row.items() if k}
            name = row.get("name", "").strip()
            rate_raw = row.get("rate", "0").strip()
            url = row.get("url", "").strip()

            if not name:
                skipped += 1
                continue
            try:
                rate_val = int(float(rate_raw))
                if not (0 <= rate_val <= 9):
                    skipped += 1
                    continue
            except ValueError:
                skipped += 1
                continue

            db.execute(
                "INSERT INTO songs (name, rate, url) VALUES (?, ?, ?)",
                (name, rate_val, url or None),
            )
            added += 1

        db.commit()
        flash(f"Import complete: {added} added, {skipped} skipped.", "success")
        return redirect(url_for("admin"))

    return render_template("upload_csv.html")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug)
