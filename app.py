"""
app.py
Flask API utama - Sistem Absensi Face ID
Jalankan: python app.py
"""
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from datetime import datetime, date, time as dtime
import os
import threading
from dotenv import load_dotenv

from db_connect import execute_query, test_connection
from face_utils import register_face, verify_face, load_model_from_db

load_dotenv()

app = Flask(__name__)
CORS(app)  # Izinkan akses dari PHP

FOTO_DIR = os.getenv('FOTO_DIR', 'foto_absensi')
CAMERA_API_TIMEOUT = int(os.getenv('CAMERA_API_TIMEOUT', '190'))

# ============================================================
# INISIALISASI
# ============================================================
@app.before_request
def startup():
    pass

# Load model saat startup
with app.app_context():
    print("\n" + "="*50)
    print("  SISTEM ABSENSI FACE ID")
    print("  Starting up...")
    print("="*50)
    test_connection()
    load_model_from_db()
    print("="*50 + "\n")

# ============================================================
# ROUTE: HALAMAN UTAMA (Dashboard Admin)
# ============================================================
@app.route('/')
def index():
    return render_template('index.html')

# ============================================================
# API: STATUS SERVICE
# ============================================================
@app.route('/api/status', methods=['GET'])
def status():
    from face_utils import recognizer_trained, label_map
    return jsonify({
        'status': 'running',
        'model_loaded': recognizer_trained,
        'jumlah_peserta_terdaftar': len(label_map),
        'timestamp': datetime.now().isoformat()
    })

# ============================================================
# API: DATA PESERTA
# ============================================================
@app.route('/api/peserta', methods=['GET'])
def get_semua_peserta():
    """Ambil semua peserta aktif"""
    rows = execute_query("""
        SELECT p.id, p.nama, p.email, p.institusi, d.nama as divisi,
               p.tanggal_mulai, p.tanggal_selesai, p.status,
               CASE WHEN fe.id IS NOT NULL THEN 1 ELSE 0 END as sudah_daftar_wajah
        FROM peserta p
        LEFT JOIN divisi d ON p.divisi_id = d.id
        LEFT JOIN face_encodings fe ON p.id = fe.peserta_id
        ORDER BY p.nama
    """, fetch=True)

    # Serialize date objects
    for row in rows:
        for key in ['tanggal_mulai', 'tanggal_selesai']:
            if row[key] and hasattr(row[key], 'isoformat'):
                row[key] = row[key].isoformat()

    return jsonify({'success': True, 'data': rows})

@app.route('/api/peserta', methods=['POST'])
def tambah_peserta():
    """Tambah peserta magang baru"""
    data = request.json
    required = ['nama', 'tanggal_mulai', 'tanggal_selesai']
    for field in required:
        if not data.get(field):
            return jsonify({'success': False, 'message': f'Field {field} wajib diisi'}), 400

    new_id = execute_query("""
        INSERT INTO peserta (nama, email, no_hp, divisi_id, institusi, tanggal_mulai, tanggal_selesai)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        data['nama'],
        data.get('email', ''),
        data.get('no_hp', ''),
        data.get('divisi_id'),
        data.get('institusi', ''),
        data['tanggal_mulai'],
        data['tanggal_selesai']
    ))

    if new_id:
        return jsonify({'success': True, 'message': 'Peserta berhasil ditambahkan', 'id': new_id})
    return jsonify({'success': False, 'message': 'Gagal menambah peserta'}), 500

@app.route('/api/peserta/<int:peserta_id>', methods=['DELETE'])
def hapus_peserta(peserta_id):
    peserta = execute_query(
        "SELECT id, nama FROM peserta WHERE id = %s",
        (peserta_id,),
        fetch=True
    )
    if not peserta:
        return jsonify({'success': False, 'message': 'Peserta tidak ditemukan'}), 404

    execute_query("DELETE FROM face_encodings WHERE peserta_id = %s", (peserta_id,))
    execute_query("DELETE FROM peserta WHERE id = %s", (peserta_id,))
    load_model_from_db()

    return jsonify({
        'success': True,
        'message': f"Peserta {peserta[0]['nama']} beserta data wajah dihapus"
    })

# ── State untuk komunikasi antar thread ──
_task_results = {}   # {task_id: result_dict}
_task_lock    = threading.Lock()

def _run_in_thread(task_id, fn, *args, timeout=CAMERA_API_TIMEOUT):
    """Jalankan fn(*args) di thread terpisah, simpan hasilnya ke _task_results."""
    def worker():
        try:
            result = fn(*args)
            with _task_lock:
                _task_results[task_id] = result or {'success': False, 'message': 'Tidak ada hasil'}
        except Exception as e:
            with _task_lock:
                _task_results[task_id] = {'success': False, 'message': str(e)}
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout=timeout)
    with _task_lock:
        return _task_results.pop(
            task_id,
            {'success': False, 'message': f'Timeout - kamera tidak merespons dalam {timeout} detik'}
        )

# ============================================================
# API: REGISTRASI WAJAH
# ============================================================
@app.route('/api/registrasi-wajah/<int:peserta_id>', methods=['POST'])
def registrasi_wajah(peserta_id):
    """Buka kamera untuk registrasi wajah peserta."""
    import uuid
    task_id = str(uuid.uuid4())
    print(f"\n[API] Registrasi wajah untuk peserta ID: {peserta_id}")
    result = _run_in_thread(task_id, register_face, peserta_id)
    if isinstance(result, tuple):
        success, message = result
        return jsonify({'success': success, 'message': message})
    return jsonify(result)

# ============================================================
# API: ABSENSI (VERIFIKASI WAJAH)
# ============================================================
@app.route('/api/absensi/masuk', methods=['POST'])
def absensi_masuk():
    """Proses absensi masuk via face recognition"""
    import uuid
    print("\n[API] Memulai proses absensi masuk...")
    task_id = str(uuid.uuid4())
    hasil = _run_in_thread(task_id, verify_face, 'masuk')

    if not hasil or not hasil.get('success'):
        # Log percobaan gagal
        execute_query("""
            INSERT INTO absensi_log (tipe, status, confidence, foto_percobaan, keterangan)
            VALUES ('masuk', 'tidak_dikenali', NULL, %s, %s)
        """, (hasil.get('foto'), hasil.get('message', '')))

        return jsonify(hasil), 400

    peserta_id = hasil['peserta_id']
    confidence = hasil['confidence']
    foto = hasil['foto']
    tanggal_hari_ini = date.today()

    # Cek apakah sudah absen masuk hari ini
    existing = execute_query("""
        SELECT id, jam_masuk FROM absensi
        WHERE peserta_id = %s AND tanggal = %s
    """, (peserta_id, tanggal_hari_ini), fetch=True)

    if existing and existing[0]['jam_masuk']:
        jam = existing[0]['jam_masuk']
        return jsonify({
            'success': False,
            'status': 'sudah_absen',
            'message': f"Anda sudah absen masuk hari ini pukul {jam}",
            'nama': hasil['nama']
        }), 400

    # Tentukan status (tepat waktu / terlambat)
    jam_sekarang = datetime.now().time()
    jam_toleransi_str = execute_query(
        "SELECT nilai FROM setting WHERE kunci='jam_masuk_toleransi'", fetch=True
    )
    jam_toleransi = dtime(8, 15)  # default
    if jam_toleransi_str:
        h, m = map(int, jam_toleransi_str[0]['nilai'].split(':'))
        jam_toleransi = dtime(h, m)

    status_absensi = 'terlambat' if jam_sekarang > jam_toleransi else 'hadir'

    # Insert atau update absensi
    if existing:
        execute_query("""
            UPDATE absensi SET jam_masuk=NOW(), foto_masuk=%s,
            confidence_masuk=%s, status=%s
            WHERE peserta_id=%s AND tanggal=%s
        """, (foto, confidence, status_absensi, peserta_id, tanggal_hari_ini))
    else:
        execute_query("""
            INSERT INTO absensi (peserta_id, tanggal, jam_masuk, foto_masuk, confidence_masuk, status)
            VALUES (%s, %s, NOW(), %s, %s, %s)
        """, (peserta_id, tanggal_hari_ini, foto, confidence, status_absensi))

    # Log berhasil
    execute_query("""
        INSERT INTO absensi_log (peserta_id, tipe, status, confidence, foto_percobaan)
        VALUES (%s, 'masuk', 'berhasil', %s, %s)
    """, (peserta_id, confidence, foto))

    return jsonify({
        'success': True,
        'message': f"Absensi masuk berhasil!",
        'nama': hasil['nama'],
        'confidence': confidence,
        'status': status_absensi,
        'waktu': datetime.now().strftime('%H:%M:%S')
    })

@app.route('/api/absensi/keluar', methods=['POST'])
def absensi_keluar():
    """Proses absensi keluar via face recognition"""
    import uuid
    print("\n[API] Memulai proses absensi keluar...")
    task_id = str(uuid.uuid4())
    hasil = _run_in_thread(task_id, verify_face, 'keluar')

    if not hasil or not hasil.get('success'):
        execute_query("""
            INSERT INTO absensi_log (tipe, status, confidence, foto_percobaan, keterangan)
            VALUES ('keluar', 'tidak_dikenali', NULL, %s, %s)
        """, (hasil.get('foto'), hasil.get('message', '')))
        return jsonify(hasil), 400

    peserta_id = hasil['peserta_id']
    confidence = hasil['confidence']
    foto = hasil['foto']
    tanggal_hari_ini = date.today()

    # Cek apakah sudah absen masuk
    existing = execute_query("""
        SELECT id, jam_keluar FROM absensi
        WHERE peserta_id = %s AND tanggal = %s
    """, (peserta_id, tanggal_hari_ini), fetch=True)

    if not existing:
        return jsonify({
            'success': False,
            'message': 'Anda belum melakukan absensi masuk hari ini.',
            'nama': hasil['nama']
        }), 400

    if existing[0]['jam_keluar']:
        return jsonify({
            'success': False,
            'status': 'sudah_absen',
            'message': f"Anda sudah absen keluar hari ini.",
            'nama': hasil['nama']
        }), 400

    execute_query("""
        UPDATE absensi SET jam_keluar=NOW(), foto_keluar=%s, confidence_keluar=%s
        WHERE peserta_id=%s AND tanggal=%s
    """, (foto, confidence, peserta_id, tanggal_hari_ini))

    execute_query("""
        INSERT INTO absensi_log (peserta_id, tipe, status, confidence, foto_percobaan)
        VALUES (%s, 'keluar', 'berhasil', %s, %s)
    """, (peserta_id, confidence, foto))

    return jsonify({
        'success': True,
        'message': 'Absensi keluar berhasil!',
        'nama': hasil['nama'],
        'confidence': confidence,
        'waktu': datetime.now().strftime('%H:%M:%S')
    })

# ============================================================
# API: LAPORAN & REKAP
# ============================================================
@app.route('/api/rekap/hari-ini', methods=['GET'])
def rekap_hari_ini():
    """Rekap absensi hari ini"""
    rows = execute_query("""
        SELECT p.nama, p.institusi, d.nama as divisi,
               a.jam_masuk, a.jam_keluar, a.status,
               a.confidence_masuk,
               CASE WHEN fe.id IS NOT NULL THEN 1 ELSE 0 END as terdaftar_wajah
        FROM peserta p
        LEFT JOIN absensi a ON p.id = a.peserta_id AND a.tanggal = CURDATE()
        LEFT JOIN divisi d ON p.divisi_id = d.id
        LEFT JOIN face_encodings fe ON p.id = fe.peserta_id
        WHERE p.status = 'aktif'
        ORDER BY a.jam_masuk IS NULL, a.jam_masuk
    """, fetch=True)

    for row in rows:
        for key in ['jam_masuk', 'jam_keluar']:
            if row[key] is not None:
                if hasattr(row[key], 'seconds'):
                    total = row[key].seconds
                    h, rem = divmod(total, 3600)
                    m, s = divmod(rem, 60)
                    row[key] = f"{h:02d}:{m:02d}:{s:02d}"

    total = len(rows)
    hadir = sum(1 for r in rows if r['jam_masuk'])
    belum = total - hadir

    return jsonify({
        'success': True,
        'data': rows,
        'summary': {
            'total_peserta': total,
            'sudah_hadir': hadir,
            'belum_hadir': belum,
            'tanggal': date.today().isoformat()
        }
    })

@app.route('/api/rekap/bulanan', methods=['GET'])
def rekap_bulanan():
    """Rekap absensi bulan ini"""
    rows = execute_query("""
        SELECT p.nama, p.institusi,
               COUNT(CASE WHEN a.status = 'hadir' THEN 1 END) as hadir,
               COUNT(CASE WHEN a.status = 'terlambat' THEN 1 END) as terlambat,
               COUNT(CASE WHEN a.status = 'izin' THEN 1 END) as izin,
               COUNT(CASE WHEN a.status = 'alpha' THEN 1 END) as alpha,
               COUNT(a.id) as total_hari
        FROM peserta p
        LEFT JOIN absensi a ON p.id = a.peserta_id
            AND MONTH(a.tanggal) = MONTH(CURDATE())
            AND YEAR(a.tanggal) = YEAR(CURDATE())
        WHERE p.status = 'aktif'
        GROUP BY p.id, p.nama, p.institusi
        ORDER BY p.nama
    """, fetch=True)

    return jsonify({'success': True, 'data': rows})

@app.route('/api/divisi', methods=['GET'])
def get_divisi():
    rows = execute_query("SELECT * FROM divisi ORDER BY nama", fetch=True)
    return jsonify({'success': True, 'data': rows})

# ============================================================
# SERVE FOTO
# ============================================================
@app.route('/foto/<path:filename>')
def serve_foto(filename):
    return send_from_directory(FOTO_DIR, filename)

# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    port = int(os.getenv('FLASK_PORT', 5000))
    debug_mode = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    host = os.getenv('FLASK_HOST', '127.0.0.1')

    app.run(host=host, port=port, debug=debug_mode,
            use_reloader=False, threaded=True)
