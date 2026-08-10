"""
camera_verify.py
Script kamera verifikasi wajah untuk absensi.
"""
import cv2
import json
import os
import sys
import time


if len(sys.argv) < 5:
    print(json.dumps({'success': False, 'message': 'Argumen tidak lengkap'}))
    sys.exit(1)

TIPE = sys.argv[1]
MODEL_PATH = sys.argv[2]
LABELS_PATH = sys.argv[3]
OUTPUT_JSON = sys.argv[4]
FOTO_DIR = sys.argv[5] if len(sys.argv) > 5 else 'foto_absensi'
CAMERA_INDEX = int(sys.argv[6]) if len(sys.argv) > 6 else 0
THRESHOLD = float(sys.argv[7]) if len(sys.argv) > 7 else 55.0

MIN_FACE_SIZE = 100
MIN_FACE_RATIO = 0.08
MAX_CENTER_OFFSET = 0.28
MIN_BLUR_SCORE = 45.0
STABLE_NEEDED = 8
TIMEOUT = 20

os.makedirs(f"{FOTO_DIR}/absensi", exist_ok=True)
os.makedirs(f"{FOTO_DIR}/gagal", exist_ok=True)

try:
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(MODEL_PATH)
    with open(LABELS_PATH, 'r', encoding='utf-8') as f:
        label_map = {int(k): v for k, v in json.load(f).items()}
except Exception as e:
    result = {'success': False, 'message': f'Gagal load model: {e}'}
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f)
    sys.exit(1)

CASCADE_PATH = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
ALT_CASCADE_PATH = cv2.data.haarcascades + 'haarcascade_frontalface_alt2.xml'
face_cascade = cv2.CascadeClassifier(CASCADE_PATH)
alt_face_cascade = cv2.CascadeClassifier(ALT_CASCADE_PATH)


def open_camera(camera_index):
    if os.name == 'nt':
        cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        if cap.isOpened():
            return cap
    return cv2.VideoCapture(camera_index)


def detect_face(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.08,
        minNeighbors=6,
        minSize=(MIN_FACE_SIZE, MIN_FACE_SIZE)
    )
    if len(faces) == 0 and not alt_face_cascade.empty():
        faces = alt_face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.05,
            minNeighbors=5,
            minSize=(MIN_FACE_SIZE, MIN_FACE_SIZE)
        )

    if len(faces) == 0:
        return None, None, "Wajah belum terdeteksi"
    if len(faces) > 1:
        return None, None, "Pastikan hanya satu wajah di depan kamera"

    x, y, w, h = max(faces, key=lambda item: item[2] * item[3])
    roi = gray[y:y + h, x:x + w]
    roi = cv2.resize(roi, (200, 200))
    return roi, (x, y, w, h), "Wajah terdeteksi"


def evaluate_face_quality(face_roi, coords, frame_shape):
    x, y, w, h = coords
    frame_h, frame_w = frame_shape[:2]
    face_ratio = (w * h) / float(frame_w * frame_h)
    if face_ratio < MIN_FACE_RATIO:
        return False, "Dekatkan wajah ke kamera"

    face_center_x = x + (w / 2.0)
    face_center_y = y + (h / 2.0)
    frame_center_x = frame_w / 2.0
    frame_center_y = frame_h / 2.0
    offset_x = abs(face_center_x - frame_center_x) / frame_w
    offset_y = abs(face_center_y - frame_center_y) / frame_h
    if offset_x > MAX_CENTER_OFFSET or offset_y > MAX_CENTER_OFFSET:
        return False, "Posisikan wajah di tengah kamera"

    blur_score = cv2.Laplacian(face_roi, cv2.CV_64F).var()
    if blur_score < MIN_BLUR_SCORE:
        return False, "Tahan kepala sebentar agar tidak blur"

    return True, "Wajah stabil"


cap = open_camera(CAMERA_INDEX)
if not cap.isOpened():
    result = {'success': False, 'message': 'Kamera tidak dapat dibuka'}
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f)
    sys.exit(1)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

label_tipe = 'ABSEN MASUK' if TIPE == 'masuk' else 'ABSEN KELUAR'
window_name = f'Sistem Absensi - {label_tipe}'

phase = 'scanning'
confirm_start = None
confirmed_id = None
confirmed_nama = ''
confirmed_conf = 0.0
foto_path = None
stable_buffer = []

cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
cv2.resizeWindow(window_name, 640, 480)
start_time = time.time()

while True:
    ret, frame = cap.read()
    if not ret:
        break

    display = frame.copy()
    elapsed = time.time() - start_time
    face_roi, coords, detect_message = detect_face(frame)

    if phase == 'scanning':
        cv2.rectangle(display, (0, 0), (640, 68), (15, 15, 20), -1)
        cv2.putText(
            display, f'SISTEM ABSENSI - {label_tipe}',
            (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2
        )
        cv2.putText(
            display, time.strftime('%A, %d %B %Y  |  %H:%M:%S'),
            (12, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.43, (160, 160, 160), 1
        )

        if face_roi is not None and coords is not None:
            x, y, w, h = coords
            is_good_face, quality_message = evaluate_face_quality(face_roi, coords, frame.shape)

            if is_good_face:
                label_int, distance = recognizer.predict(face_roi)
                confidence = max(0.0, 1.0 - distance / 100.0)
                is_match = distance < THRESHOLD and label_int in label_map

                if is_match:
                    person_data = label_map[label_int]
                    if isinstance(person_data, dict):
                        nama = person_data.get('nama', str(label_int))
                        pid = person_data.get('id', label_int)
                    else:
                        nama = str(person_data)
                        pid = person_data

                    stable_buffer.append((pid, nama, confidence))
                    if len(stable_buffer) > STABLE_NEEDED:
                        stable_buffer.pop(0)

                    cv2.rectangle(display, (x, y), (x + w, y + h), (0, 230, 90), 3)
                    cv2.putText(
                        display, nama,
                        (x, max(24, y - 36)), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 230, 90), 2
                    )
                    cv2.putText(
                        display, f'Confidence: {confidence:.0%}',
                        (x, max(44, y - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 230, 90), 1
                    )

                    bw = int(confidence * w)
                    cv2.rectangle(display, (x, y + h + 5), (x + w, y + h + 16), (40, 40, 50), -1)
                    cv2.rectangle(
                        display,
                        (x, y + h + 5),
                        (x + bw, y + h + 16),
                        (0, 230, 90) if confidence > 0.8 else (0, 200, 200),
                        -1
                    )

                    if len(stable_buffer) >= STABLE_NEEDED:
                        ids = [item[0] for item in stable_buffer]
                        if len(set(ids)) == 1:
                            confirmed_id = stable_buffer[-1][0]
                            confirmed_nama = stable_buffer[-1][1]
                            confirmed_conf = sum(item[2] for item in stable_buffer) / len(stable_buffer)
                            foto_path = f"{FOTO_DIR}/absensi/{TIPE}_{confirmed_id}_{int(time.time())}.jpg"
                            cv2.imwrite(foto_path, frame)
                            phase = 'confirmed'
                            confirm_start = time.time()
                else:
                    stable_buffer.clear()
                    cv2.rectangle(display, (x, y), (x + w, y + h), (0, 60, 240), 2)
                    cv2.putText(
                        display, 'Wajah tidak dikenali',
                        (x, max(24, y - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 60, 240), 1
                    )
            else:
                stable_buffer.clear()
                cv2.rectangle(display, (x, y), (x + w, y + h), (0, 180, 255), 2)
                cv2.putText(
                    display, quality_message,
                    (x, max(24, y - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 180, 255), 1
                )
        else:
            stable_buffer.clear()
            cv2.rectangle(display, (195, 115), (445, 385), (0, 180, 255), 2)
            cv2.putText(
                display, detect_message,
                (120, 108), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 180, 255), 2
            )

        cv2.rectangle(display, (0, 448), (640, 480), (15, 15, 20), -1)
        timeout_fill = int((elapsed / TIMEOUT) * 620)
        cv2.rectangle(
            display, (10, 460), (10 + min(timeout_fill, 620), 468),
            (200, 120, 0) if elapsed < TIMEOUT * 0.75 else (0, 60, 220), -1
        )
        cv2.putText(
            display,
            f"Timeout: {max(0, int(TIMEOUT - elapsed))}s  |  Tekan Q untuk batal",
            (10, 478), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (120, 120, 120), 1
        )

        if elapsed >= TIMEOUT:
            foto_gagal = f"{FOTO_DIR}/gagal/timeout_{int(time.time())}.jpg"
            cv2.imwrite(foto_gagal, frame)
            cap.release()
            cv2.destroyAllWindows()
            result = {
                'success': False,
                'status': 'timeout',
                'message': 'Waktu habis. Wajah tidak terdeteksi atau tidak dikenali.',
                'foto': foto_gagal
            }
            with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
                json.dump(result, f)
            sys.exit(0)

    elif phase == 'confirmed':
        elapsed_c = time.time() - confirm_start

        overlay = display.copy()
        cv2.rectangle(overlay, (0, 0), (640, 480), (0, 150, 50), -1)
        cv2.addWeighted(overlay, 0.40, display, 0.60, 0, display)

        cv2.putText(
            display, 'SELAMAT DATANG',
            (195, 175), cv2.FONT_HERSHEY_SIMPLEX, 0.90, (255, 255, 255), 2
        )
        cv2.putText(
            display, confirmed_nama,
            (int(320 - len(confirmed_nama) * 11), 235),
            cv2.FONT_HERSHEY_SIMPLEX, 0.95, (80, 255, 140), 2
        )
        cv2.putText(
            display, f'Absensi {TIPE}: {time.strftime("%H:%M:%S")}',
            (165, 285), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (200, 255, 200), 1
        )
        cv2.putText(
            display, f'Confidence: {confirmed_conf:.0%}',
            (240, 320), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (180, 255, 180), 1
        )

        sisa = max(0, 3 - int(elapsed_c))
        cv2.putText(
            display, f'Mencatat kehadiran... ({sisa})',
            (195, 390), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (160, 255, 160), 1
        )

        if elapsed_c >= 3:
            phase = 'done'

    elif phase == 'done':
        break

    cv2.imshow(window_name, display)
    key = cv2.waitKey(1) & 0xFF
    if key in (ord('q'), 27):
        foto_gagal = f"{FOTO_DIR}/gagal/batal_{int(time.time())}.jpg"
        cv2.imwrite(foto_gagal, frame)
        cap.release()
        cv2.destroyAllWindows()
        result = {
            'success': False,
            'status': 'dibatalkan',
            'message': 'Verifikasi dibatalkan.',
            'foto': foto_gagal
        }
        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(result, f)
        sys.exit(0)

cap.release()
cv2.destroyAllWindows()

if confirmed_id is not None:
    result = {
        'success': True,
        'status': 'dikenali',
        'peserta_id': confirmed_id,
        'nama': confirmed_nama,
        'confidence': round(confirmed_conf, 3),
        'foto': foto_path or '',
        'tipe': TIPE,
    }
else:
    result = {
        'success': False,
        'status': 'tidak_dikenali',
        'message': 'Wajah tidak dapat dikenali.'
    }

with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
    json.dump(result, f)

sys.exit(0)
