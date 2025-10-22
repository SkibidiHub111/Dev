from flask import Flask, request, jsonify, abort
import psycopg2, threading, time, datetime, os

DATABASE_URL = "postgresql://keysdb_94t2_user:blxPheWDksBZ2wt7lXuqlMTtgehOt3YQ@dpg-d3sbfsh5pdvs73fe8en0-a.oregon-postgres.render.com/keysdb_94t2"
app = Flask(__name__)

def get_conn():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS keys (
        id SERIAL PRIMARY KEY,
        key TEXT NOT NULL,
        hwid TEXT,
        months INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        discord_id TEXT
    )
    ''')
    conn.commit()
    conn.close()

def add_key_to_db(key, hwid, months, discord_id):
    created = datetime.datetime.utcnow()
    expires = created + datetime.timedelta(days=30 * months)
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        INSERT INTO keys (key, hwid, months, created_at, expires_at, discord_id)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
    ''', (key, hwid, months, created.isoformat(), expires.isoformat(), discord_id))
    key_id = c.fetchone()[0]
    conn.commit()
    conn.close()
    return {
        "id": key_id,
        "key": key,
        "hwid": hwid,
        "months": months,
        "created_at": created.isoformat(),
        "expires_at": expires.isoformat(),
        "discord_id": discord_id
    }

def get_all_keys():
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT id, key, hwid, months, created_at, expires_at, discord_id FROM keys')
    rows = c.fetchall()
    conn.close()
    keys = []
    for r in rows:
        keys.append({
            "id": r[0],
            "key": r[1],
            "hwid": r[2],
            "months": r[3],
            "created_at": r[4],
            "expires_at": r[5],
            "discord_id": r[6]
        })
    return keys

def delete_key(key_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute('DELETE FROM keys WHERE id = %s', (key_id,))
    conn.commit()
    conn.close()

@app.route('/')
def index():
    return jsonify({"status": "ok", "message": "API online"}), 200

@app.route('/keys', methods=['POST'])
def post_key():
    j = request.get_json()
    if not j:
        abort(400)
    key = j.get('key')
    months = int(j.get('months', 1))
    hwid_bypass = bool(j.get('hwid_bypass', False))
    discord_id = j.get('discord_id')
    if not key:
        return jsonify({"error": "key required"}), 400
    hwid = "BYPASS" if hwid_bypass else None
    data = add_key_to_db(key, hwid, months, discord_id)
    return jsonify({"status": "ok", "data": data}), 201

@app.route('/keys', methods=['GET'])
def list_keys():
    return jsonify(get_all_keys()), 200

@app.route('/keys/<int:key_id>', methods=['PATCH'])
def patch_key(key_id):
    j = request.get_json()
    if not j:
        abort(400)
    if 'hwid' in j:
        hw = j['hwid']
        conn = get_conn()
        c = conn.cursor()
        c.execute('UPDATE keys SET hwid = %s WHERE id = %s', (hw, key_id))
        conn.commit()
        conn.close()
        return jsonify({"status": "ok"}), 200
    return jsonify({"error": "no valid field"}), 400

@app.route('/keys/<int:key_id>', methods=['DELETE'])
def del_key(key_id):
    delete_key(key_id)
    return jsonify({"status": "deleted"}), 200

@app.route('/verify', methods=['GET'])
def verify_key():
    key = request.args.get('key')
    hwid = request.args.get('hwid')
    if not key:
        return jsonify({"status": "error", "message": "missing key"}), 400
    conn = get_conn()
    c = conn.cursor()
    c.execute('SELECT id, hwid, expires_at FROM keys WHERE key = %s', (key,))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({"status": "invalid", "message": "key not found"}), 404
    key_id, saved_hwid, exp = row
    if datetime.datetime.fromisoformat(exp) < datetime.datetime.utcnow():
        return jsonify({"status": "expired", "message": "key expired"}), 403
    if saved_hwid == "BYPASS":
        return jsonify({"status": "ok", "message": "key valid (bypass)", "id": key_id}), 200
    if saved_hwid and hwid and saved_hwid != hwid:
        return jsonify({"status": "invalid", "message": "hwid mismatch"}), 403
    if not saved_hwid and hwid:
        conn = get_conn()
        c = conn.cursor()
        c.execute('UPDATE keys SET hwid = %s WHERE id = %s', (hwid, key_id))
        conn.commit()
        conn.close()
    return jsonify({"status": "ok", "message": "key valid", "id": key_id}), 200

def cleanup_loop():
    while True:
        try:
            now = datetime.datetime.utcnow().isoformat()
            conn = get_conn()
            c = conn.cursor()
            c.execute('DELETE FROM keys WHERE expires_at <= %s', (now,))
            conn.commit()
            conn.close()
        except Exception:
            pass
        time.sleep(3600)

if __name__ == '__main__':
    init_db()
    threading.Thread(target=cleanup_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
