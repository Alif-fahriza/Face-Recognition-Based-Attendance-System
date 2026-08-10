"""
face_utils.py
Modul Face Recognition — menggunakan subprocess agar jendela kamera
terbuka dengan benar di Windows (cv2.imshow harus di main thread).
"""
import cv2
import numpy as np
import os
import pickle
import json
import base64
import time
import subprocess
import sys
import tempfile
import zlib
from db_connect import get_connection, execute_query
from dotenv import load_dotenv

load_dotenv()

FOTO_DIR = os.getenv('FOTO_DIR', 'foto_absensi')
CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD', '0.55'))
CAMERA_INDEX = int(os.getenv('CAMERA_INDEX', '0'))
CAMERA_PROCESS_TIMEOUT = int(os.getenv('CAMERA_PROCESS_TIMEOUT', '180'))
DISTANCE_THRESHOLD = (1.0 - CONFIDENCE_THRESHOLD) * 100.0

for d in ['registrasi', 'absensi', 'gagal']:
    os.makedirs(f"{FOTO_DIR}/{d}", exist_ok=True)

recognizer = cv2.face.LBPHFaceRecognizer_create()
recognizer_trained = False
label_map = {}
MODEL_FILE = os.path.join(tempfile.gettempdir(), 'absensi_model.xml')
LABELS_FILE = os.path.join(tempfile.gettempdir(), 'absensi_labels.json')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_REGISTER = os.path.join(BASE_DIR, 'camera_register.py')
SCRIPT_VERIFY = os.path.join(BASE_DIR, 'camera_verify.py')
PYTHON_EXE = sys.executable


def _blob_to_bytes(value):
    """Normalisasi hasil BLOB dari MySQL connector ke bytes murni."""
    if value is None:
        return b''
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, memoryview):
        return value.tobytes()
    return bytes(value)


def _decode_face_payload(blob_value):
    """
    Baca payload wajah lama maupun baru.
    Format lama: pickle(list[np.ndarray]).
    Format baru: zlib(pickle({version: 2, format: 'jpeg_list', faces: [...]})).
    """
    raw_bytes = _blob_to_bytes(blob_value)
    if not raw_bytes:
        return []

    payload = None
    try:
        payload = pickle.loads(raw_bytes)
    except Exception:
        try:
            payload = pickle.loads(zlib.decompress(raw_bytes))
        except Exception as e:
            raise RuntimeError(f'Payload wajah tidak valid: {e}')

    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict) and payload.get('format') == 'jpeg_list':
        faces = []
        for encoded_face in payload.get('faces', []):
            arr = np.frombuffer(encoded_face, dtype=np.uint8)
            face = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
            if face is None:
                continue
            if face.shape != (200, 200):
                face = cv2.resize(face, (200, 200))
            faces.append(face)
        return faces

    raise RuntimeError('Format payload wajah tidak dikenali')


def _save_encoding_to_db(peserta_id, encoding_bytes, jumlah, foto_ref):
    """
    Simpan encoding wajah dengan cursor biasa agar BLOB besar lebih aman ditulis.
    Return (success, action, error_message).
    """
    last_error = None

    for attempt in range(1, 4):
        conn = None
        cursor = None
        try:
            conn = get_connection()
            if not conn:
                raise RuntimeError("Tidak dapat membuat koneksi ke database")

            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM face_encodings WHERE peserta_id=%s",
                (peserta_id,)
            )
            existing = cursor.fetchone()

            if existing:
                cursor.execute(
                    "UPDATE face_encodings "
                    "SET encoding_data=%s, jumlah_sampel=%s, foto_referensi=%s, updated_at=NOW() "
                    "WHERE peserta_id=%s",
                    (encoding_bytes, jumlah, foto_ref, peserta_id)
                )
                action = 'updated'
            else:
                cursor.execute(
                    "INSERT INTO face_encodings (peserta_id, encoding_data, jumlah_sampel, foto_referensi) "
                    "VALUES (%s, %s, %s, %s)",
                    (peserta_id, encoding_bytes, jumlah, foto_ref)
                )
                action = 'inserted'

            conn.commit()

            cursor.execute(
                "SELECT LENGTH(encoding_data) FROM face_encodings WHERE peserta_id=%s",
                (peserta_id,)
            )
            saved_row = cursor.fetchone()
            blob_len = saved_row[0] if saved_row else 0
            if not blob_len:
                raise RuntimeError("Data wajah tidak ditemukan setelah proses simpan")

            return True, action, None
        except Exception as e:
            last_error = str(e)
            print(f"[FACE][DB] Gagal simpan encoding attempt {attempt}/3: {e}")
            try:
                if conn and conn.is_connected():
                    conn.rollback()
            except Exception:
                pass
            time.sleep(attempt * 0.5)
        finally:
            try:
                if cursor is not None:
                    cursor.close()
            except Exception:
                pass
            try:
                if conn and conn.is_connected():
                    conn.close()
            except Exception:
                pass

    return False, None, last_error


def load_model_from_db():
    global recognizer, recognizer_trained, label_map

    rows = execute_query(
        "SELECT fe.peserta_id, fe.encoding_data, p.nama "
        "FROM face_encodings fe JOIN peserta p ON fe.peserta_id = p.id",
        fetch=True
    )

    if not rows:
        print("[FACE] Belum ada data wajah di database.")
        recognizer_trained = False
        return False

    faces, labels = [], []
    label_map = {}

    valid_rows = 0
    for idx, row in enumerate(rows):
        try:
            face_list = _decode_face_payload(row['encoding_data'])
        except Exception as e:
            print(f"[FACE] Gagal membaca encoding peserta {row['peserta_id']}: {e}")
            continue

        if not isinstance(face_list, list) or not face_list:
            print(f"[FACE] Encoding peserta {row['peserta_id']} kosong atau format tidak valid.")
            continue

        label_int = idx + 1
        label_map[label_int] = {'id': row['peserta_id'], 'nama': row['nama']}
        for fa in face_list:
            faces.append(fa)
            labels.append(label_int)
        valid_rows += 1

    if not faces:
        recognizer_trained = False
        return False

    recognizer.train(faces, np.array(labels))
    recognizer_trained = True

    recognizer.save(MODEL_FILE)
    with open(LABELS_FILE, 'w') as f:
        json.dump({str(k): v for k, v in label_map.items()},
                  f, ensure_ascii=False)

    print(f"[FACE] Model siap: {valid_rows} peserta valid, {len(faces)} sampel.")
    return True


def register_face(peserta_id):
    rows = execute_query(
        "SELECT nama FROM peserta WHERE id=%s", (peserta_id,), fetch=True)
    if not rows:
        return False, "Peserta tidak ditemukan"
    nama = rows[0]['nama']

    out_file = os.path.join(tempfile.gettempdir(),
                            f'reg_result_{peserta_id}.json')
    if os.path.exists(out_file):
        os.remove(out_file)

    print(f"[FACE] Membuka kamera untuk registrasi: {nama}")

    try:
        completed = subprocess.run(
            [PYTHON_EXE, SCRIPT_REGISTER,
             str(peserta_id), nama, out_file, FOTO_DIR, str(CAMERA_INDEX)],
            timeout=CAMERA_PROCESS_TIMEOUT,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
    except subprocess.TimeoutExpired:
        return False, f"Proses kamera timeout (>{CAMERA_PROCESS_TIMEOUT} detik)"
    except Exception as e:
        return False, f"Error subprocess: {e}"

    if not os.path.exists(out_file):
        error_output = (completed.stderr or completed.stdout or '').strip()
        if error_output:
            error_output = error_output.splitlines()[-1]
            return False, f"Kamera gagal memproses registrasi: {error_output}"
        return False, "Tidak ada hasil dari kamera"

    with open(out_file, 'r') as f:
        result = json.load(f)
    os.remove(out_file)

    if not result.get('success'):
        return False, result.get('message', 'Registrasi gagal')

    encoding_bytes = base64.b64decode(result['encoding_b64'])
    foto_ref = result.get('foto_referensi', '')
    jumlah = result.get('jumlah_sampel', 0)
    print(f"[FACE] Ukuran payload registrasi: {len(encoding_bytes)} bytes")

    time.sleep(0.5)

    ok, action, error_message = _save_encoding_to_db(
        peserta_id, encoding_bytes, jumlah, foto_ref
    )
    if not ok:
        return False, f"Gagal menyimpan ke database: {error_message or 'error tidak diketahui'}"

    if not load_model_from_db():
        return False, "Data wajah tersimpan, tetapi model gagal diperbarui. Coba restart service."

    if action == 'updated':
        msg = f"Data wajah {nama} berhasil diperbarui ({jumlah} sampel)"
    else:
        msg = f"Wajah {nama} berhasil didaftarkan ({jumlah} sampel)"

    print(f"[FACE] {msg}")
    return True, msg


def verify_face(tipe='masuk'):
    if not recognizer_trained:
        if not load_model_from_db():
            return {
                'success': False, 'status': 'error',
                'message': 'Belum ada data wajah terdaftar. Lakukan registrasi terlebih dahulu.'
            }

    if not os.path.exists(MODEL_FILE) or not os.path.exists(LABELS_FILE):
        return {'success': False, 'status': 'error',
                'message': 'File model tidak ditemukan. Restart service.'}

    out_file = os.path.join(tempfile.gettempdir(),
                            f'verify_{tipe}_{int(time.time())}.json')
    if os.path.exists(out_file):
        os.remove(out_file)

    print(f"[FACE] Membuka kamera untuk absensi {tipe}...")

    try:
        subprocess.run(
            [PYTHON_EXE, SCRIPT_VERIFY,
             tipe, MODEL_FILE, LABELS_FILE, out_file,
             FOTO_DIR, str(CAMERA_INDEX), str(DISTANCE_THRESHOLD)],
            timeout=180
        )
    except subprocess.TimeoutExpired:
        return {'success': False, 'status': 'timeout', 'message': 'Proses kamera timeout'}
    except Exception as e:
        return {'success': False, 'status': 'error', 'message': f'Error subprocess: {e}'}

    if not os.path.exists(out_file):
        return {'success': False, 'status': 'error', 'message': 'Tidak ada hasil dari kamera'}

    with open(out_file, 'r') as f:
        result = json.load(f)
    os.remove(out_file)

    return result
