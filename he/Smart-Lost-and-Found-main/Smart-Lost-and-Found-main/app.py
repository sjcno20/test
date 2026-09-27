from flask import Flask, request, send_from_directory, jsonify
import sqlite3
import os
import re

try:
    from flask_cors import CORS
except ImportError:
    def CORS(app, *args, **kwargs):
        return None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "lost_found.db")

app = Flask(__name__, static_folder=BASE_DIR, static_url_path='')
CORS(app, resources={r"/api/*": {"origins": "*"}})


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL,
            category TEXT,
            item TEXT NOT NULL,
            brand TEXT,
            size TEXT,
            marks TEXT,
            location TEXT,
            date TEXT,
            high_priority INTEGER DEFAULT 0,
            drop_off_status TEXT,
            secret_question TEXT,
            match_score INTEGER DEFAULT 0,
            matched_with TEXT DEFAULT '',
            claim_status TEXT DEFAULT 'PENDING'
        )
    """)

    existing_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(reports)").fetchall()
    }

    new_columns = {
        "category": "TEXT",
        "size": "TEXT",
        "marks": "TEXT",
        "high_priority": "INTEGER DEFAULT 0",
        "drop_off_status": "TEXT",
        "secret_question": "TEXT",
        "match_score": "INTEGER DEFAULT 0",
        "matched_with": "TEXT DEFAULT ''",
        "claim_status": "TEXT DEFAULT 'PENDING'"
    }

    for column, definition in new_columns.items():
        if column not in existing_columns:
            conn.execute(
                f"ALTER TABLE reports ADD COLUMN {column} {definition}"
            )

    # Seed initial demo items if table is empty
    count = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    if count == 0:
        demo_reports = [
            (
                "lost",
                "Wearables & Watches",
                "Blue Casio Watch with scratched strap",
                "Casio",
                "Standard Dial (42mm)",
                "Distinct scratch across bottom plastic bezel; navy blue polyurethane strap with faint silver buckle wear.",
                "Central Library - 1st Floor",
                "2026-09-25",
                1,
                "N/A",
                "",
                80,
                "#ITM-2 (Casio Digital Watch)",
                "MATCH CANDIDATE"
            ),
            (
                "found",
                "Wearables & Watches",
                "Casio Digital Watch with blue strap",
                "Casio",
                "Standard Dial",
                "Found under 2nd row study desk, blue resin strap with scratch on bezel.",
                "Central Library - 1st Floor",
                "2026-09-25",
                0,
                "Central Library - Main Desk",
                "What number or code is etched on the rear case?",
                80,
                "#ITM-1 (Blue Casio Watch)",
                "PENDING"
            ),
            (
                "found",
                "Wallets & Cards",
                "Black Leather Bifold Wallet",
                "Fossil",
                "Medium",
                "Embossed leather edges, contains student campus card and transport pass.",
                "RK Hall - Cafeteria",
                "2026-09-26",
                0,
                "RK Hall Security",
                "What initials are engraved inside the coin pocket?",
                0,
                "",
                "PENDING"
            ),
            (
                "lost",
                "Keys",
                "Key Ring with Space Shuttle Pendant",
                "NASA Souvenir",
                "3 brass keys + fob",
                "Miniature metal Apollo rocket keychain; 1 small padlock brass key.",
                "Unknown / Misplaced",
                "2026-09-24",
                0,
                "N/A",
                "",
                0,
                "",
                "PENDING"
            )
        ]

        conn.executemany("""
            INSERT INTO reports
            (status, category, item, brand, size, marks, location, date,
             high_priority, drop_off_status, secret_question, match_score,
             matched_with, claim_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, demo_reports)

    conn.commit()
    conn.close()


# Initialize database automatically on startup
init_db()


def extract_keywords(text):
    if not text:
        return set()
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', ' ', text.lower())
    stop_words = {'the', 'and', 'with', 'for', 'from', 'this', 'that', 'has', 'item', 'lost', 'found'}
    return {w for w in cleaned.split() if len(w) > 2 and w not in stop_words}


def calculate_similarity(item1, item2):
    """
    Multi-factor similarity scoring algorithm:
    - Same Category: +40%
    - Keyword Overlap in Title/Marks: +30%
    - Same Brand: +20%
    - Same Specific Location: +10%
    """
    score = 0

    # 1. Category comparison
    c1 = (item1.get("category") or "").strip().lower()
    c2 = (item2.get("category") or "").strip().lower()
    if c1 and c2 and c1 == c2:
        score += 40

    # 2. Keyword overlap in item name & description
    text1 = f"{item1.get('item', '')} {item1.get('marks', '')}"
    text2 = f"{item2.get('item', '')} {item2.get('marks', '')}"
    k1 = extract_keywords(text1)
    k2 = extract_keywords(text2)
    common_keywords = k1 & k2
    if common_keywords:
        score += 30

    # 3. Brand comparison
    b1 = (item1.get("brand") or "").strip().lower()
    b2 = (item2.get("brand") or "").strip().lower()
    ignored_brands = {"unspecified", "none", "unknown", "n/a", "standard", ""}
    if b1 not in ignored_brands and b2 not in ignored_brands and b1 == b2:
        score += 20

    # 4. Location comparison (skip unknown)
    l1 = (item1.get("location") or "").strip().lower()
    l2 = (item2.get("location") or "").strip().lower()
    if l1 and l2 and "unknown" not in l1 and "unknown" not in l2 and l1 == l2:
        score += 10

    return min(score, 100), common_keywords


@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/api/test')
def test():
    return jsonify({"message": "Backend is working!", "status": "online"})


@app.route('/api/stats', methods=["GET"])
def get_stats():
    conn = get_db()
    total_lost = conn.execute("SELECT COUNT(*) FROM reports WHERE LOWER(status) = 'lost'").fetchone()[0]
    total_found = conn.execute("SELECT COUNT(*) FROM reports WHERE LOWER(status) = 'found'").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM reports WHERE UPPER(claim_status) != 'RESOLVED'").fetchone()[0]
    resolved = conn.execute("SELECT COUNT(*) FROM reports WHERE UPPER(claim_status) = 'RESOLVED'").fetchone()[0]
    conn.close()

    return jsonify({
        "total_lost": total_lost,
        "total_found": total_found,
        "pending_claims": pending,
        "successful_returns": resolved
    })


@app.route("/api/reports", methods=["GET", "POST"])
def handle_reports():
    conn = get_db()

    if request.method == "GET":
        cursor = conn.execute("SELECT * FROM reports ORDER BY id DESC")
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return jsonify({"reports": rows})

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        
        status = (data.get("status") or "lost").lower().strip()
        item_name = (data.get("item") or "").strip()
        category = (data.get("category") or "").strip()
        brand = (data.get("brand") or "Unspecified").strip()
        size = (data.get("size") or "Standard").strip()
        marks = (data.get("marks") or "No specific marks listed.").strip()
        location = (data.get("location") or "").strip()
        date_val = (data.get("date") or "").strip()
        high_priority = 1 if data.get("high_priority") else 0
        drop_off_status = (data.get("drop_off_status") or "N/A").strip()
        secret_question = (data.get("secret_question") or "").strip()

        if not item_name:
            conn.close()
            return jsonify({"error": "Item name is required"}), 400

        # Dynamic Similarity Match against opposite incident types
        opposite_status = "found" if status == "lost" else "lost"
        cursor = conn.execute("SELECT * FROM reports WHERE LOWER(status) = ?", (opposite_status,))
        potential_matches = cursor.fetchall()

        incoming_item_dict = {
            "category": category,
            "item": item_name,
            "brand": brand,
            "marks": marks,
            "location": location
        }

        best_match_score = 0
        best_match_row = None
        for row in potential_matches:
            row_dict = dict(row)
            score, _ = calculate_similarity(incoming_item_dict, row_dict)
            if score > best_match_score:
                best_match_score = score
                best_match_row = row_dict

        matched_with = ""
        claim_status = "PENDING"
        if best_match_score >= 50 and best_match_row:
            matched_with = f"#ITM-{best_match_row['id']} ({best_match_row['item']})"
            claim_status = "MATCH CANDIDATE"

        # Insert new report into Database
        cursor = conn.execute("""
            INSERT INTO reports
            (status, category, item, brand, size, marks, location, date,
             high_priority, drop_off_status, secret_question, match_score,
             matched_with, claim_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            status,
            category,
            item_name,
            brand,
            size,
            marks,
            location,
            date_val,
            high_priority,
            drop_off_status,
            secret_question,
            best_match_score,
            matched_with,
            claim_status
        ))

        conn.commit()
        report_id = cursor.lastrowid

        # Update the opposing match record in database if cross-matched
        if best_match_score >= 50 and best_match_row:
            partner_matched_with = f"#ITM-{report_id} ({item_name})"
            conn.execute("""
                UPDATE reports
                SET match_score = MAX(match_score, ?),
                    matched_with = CASE WHEN matched_with IS NULL OR matched_with = '' THEN ? ELSE matched_with END,
                    claim_status = CASE WHEN claim_status = 'PENDING' THEN 'MATCH CANDIDATE' ELSE claim_status END
                WHERE id = ?
            """, (best_match_score, partner_matched_with, best_match_row["id"]))
            conn.commit()

        conn.close()

        return jsonify({
            "message": "Report saved successfully!",
            "report_id": report_id,
            "match_score": best_match_score,
            "matched_item": best_match_row,
            "report": {
                "id": report_id,
                "status": status,
                "category": category,
                "item": item_name,
                "brand": brand,
                "size": size,
                "marks": marks,
                "location": location,
                "date": date_val,
                "high_priority": high_priority,
                "drop_off_status": drop_off_status,
                "secret_question": secret_question,
                "match_score": best_match_score,
                "matched_with": matched_with,
                "claim_status": claim_status
            }
        }), 201

    conn.close()
    return jsonify({"message": "Invalid request method"}), 405


@app.route("/api/reports/<int:report_id>/resolve", methods=["POST", "PATCH"])
def resolve_report(report_id):
    conn = get_db()
    cursor = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Report not found"}), 404

    conn.execute("UPDATE reports SET claim_status = 'RESOLVED' WHERE id = ?", (report_id,))
    conn.commit()
    conn.close()

    return jsonify({
        "message": f"Report #{report_id} marked as RESOLVED.",
        "report_id": report_id,
        "claim_status": "RESOLVED"
    })


@app.route('/<path:path>')
def static_proxy(path):
    target = os.path.join(BASE_DIR, path)
    if os.path.exists(target) and not os.path.isdir(target):
        return send_from_directory(BASE_DIR, path)
    return send_from_directory(BASE_DIR, 'index.html')


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Smart Lost & Found server on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)