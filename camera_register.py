"""
camera_register.py
Script kamera registrasi wajah yang dijalankan sebagai subprocess terpisah.
Hasil dikirim ke parent process via file JSON sementara.
"""
import base64
import cv2
import json
import os
import pickle
import sys
import time
import zlib


if len(sys.argv) < 4:
    print(json.dumps({'success': False, 'message': 'Argumen tidak lengkap'}))
    sys.exit(1)

PESERTA_ID = int(sys.argv[1])
NAMA = sys.argv[2]
OUTPUT_JSON = sys.argv[3]
FOTO_DIR = sys.argv[4] if len(sys.argv) > 4 else 'foto_absensi'
CAMERA_INDEX = int(sys.argv[5]) if len(sys.argv) > 5 else 0
JUMLAH_SAMPEL = 16
JPEG_QUALITY = 80

MIN_FACE_SIZE = 100
MIN_FACE_RATIO = 0.08
MAX_CENTER_OFFSET = 0.25
MIN_BLUR_SCORE = 55.0
STABLE_FRAMES_REQUIRED = 3

os.makedirs(f"{FOTO_DIR}/registrasi", exist_ok=True)

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
        return False, "Posisikan wajah di tengah kotak"

    blur_score = cv2.Laplacian(face_roi, cv2.CV_64F).var()
    if blur_score < MIN_BLUR_SCORE:
        return False, "Tahan kepala sebentar agar tidak blur"

    return True, "Wajah stabil, mengambil sampel"


cap = open_camera(CAMERA_INDEX)
if not cap.isOpened():
    result = {'success': False, 'message': f'Kamera index {CAMERA_INDEX} tidak dapat dibuka'}
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(result, f)
    sys.exit(1)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

faces_collected = []
foto_referensi = None
frame_count = 0
good_frame_streak = 0
phase = 'scanning'
confirm_start = None
window_name = f'Registrasi Wajah - {NAMA}'

cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
cv2.resizeWindow(window_name, 640, 480)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    display = frame.copy()
    face_roi, coords, detect_message = detect_face(frame)

    if phase == 'scanning':
        progress = len(faces_collected)

        cv2.rectangle(display, (0, 0), (640, 68), (15, 15, 20), -1)
        cv2.putText(
            display, f'REGISTRASI: {NAMA}',
            (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (255, 255, 255), 2
        )

        bar_fill = int((progress / JUMLAH_SAMPEL) * 600)
        cv2.rectangle(display, (20, 40), (620, 56), (40, 40, 50), -1)
        cv2.rectangle(display, (20, 40), (20 + bar_fill, 56), (0, 210, 100), -1)
        cv2.putText(
            display, f'{progress}/{JUMLAH_SAMPEL} sampel terkumpul',
            (12, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (180, 180, 180), 1
        )

        if face_roi is not None and coords is not None:
            x, y, w, h = coords
            is_good_face, quality_message = evaluate_face_quality(face_roi, coords, frame.shape)
            box_color = (0, 230, 90) if is_good_face else (0, 180, 255)
            cv2.rectangle(display, (x, y), (x + w, y + h), box_color, 2)
            cv2.putText(
                display, quality_message,
                (x, max(24, y - 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, box_color, 2
            )

            if is_good_face:
                good_frame_streak += 1
                frame_count += 1
                if good_frame_streak >= STABLE_FRAMES_REQUIRED and frame_count % 2 == 0:
                    faces_collected.append(face_roi.copy())
                    if len(faces_collected) == JUMLAH_SAMPEL // 2:
                        foto_path = f"{FOTO_DIR}/registrasi/peserta_{PESERTA_ID}_{int(time.time())}.jpg"
                        cv2.imwrite(foto_path, frame)
                        foto_referensi = foto_path
            else:
                good_frame_streak = 0
        else:
            good_frame_streak = 0
            cv2.rectangle(display, (195, 115), (445, 385), (0, 180, 255), 2)
            cv2.putText(
                display, detect_message,
                (120, 108), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 180, 255), 2
            )

        if len(faces_collected) >= JUMLAH_SAMPEL:
            phase = 'confirmed'
            confirm_start = time.time()

        cv2.rectangle(display, (0, 448), (640, 480), (15, 15, 20), -1)
        cv2.putText(
            display,
            "Tekan Q untuk batal  |  Hadap kamera dengan pencahayaan cukup",
            (8, 469), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (140, 140, 140), 1
        )

    elif phase == 'confirmed':
        elapsed_confirm = time.time() - confirm_start

        overlay = display.copy()
        cv2.rectangle(overlay, (0, 0), (640, 480), (0, 180, 60), -1)
        cv2.addWeighted(overlay, 0.35, display, 0.65, 0, display)

        cv2.putText(
            display, 'WAJAH BERHASIL DIREKAM',
            (92, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 255, 255), 2
        )
        cv2.putText(
            display, NAMA,
            (int(320 - len(NAMA) * 11), 250),
            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (80, 255, 140), 2
        )
        cv2.putText(
            display, f'{len(faces_collected)} sampel wajah tersimpan',
            (170, 295), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 255, 200), 1
        )

        sisa = max(0, 3 - int(elapsed_confirm))
        cv2.putText(
            display, f'Menyimpan ke database... ({sisa})',
            (175, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 255, 180), 1
        )

        if elapsed_confirm >= 3:
            phase = 'done'

    elif phase == 'done':
        break

    cv2.imshow(window_name, display)

    key = cv2.waitKey(1) & 0xFF
    if key in (ord('q'), 27):
        cap.release()
        cv2.destroyAllWindows()
        result = {'success': False, 'message': 'Registrasi dibatalkan oleh user'}
        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(result, f)
        sys.exit(0)

cap.release()
cv2.destroyAllWindows()

if not faces_collected:
    result = {'success': False, 'message': 'Tidak ada wajah yang berhasil direkam'}
else:
    encoded_faces = []
    for face in faces_collected:
        ok, buffer = cv2.imencode(
            '.jpg',
            face,
            [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
        )
        if ok:
            encoded_faces.append(buffer.tobytes())

    payload = {
        'version': 2,
        'format': 'jpeg_list',
        'size': [200, 200],
        'faces': encoded_faces,
    }
    if not encoded_faces:
        result = {'success': False, 'message': 'Sampel wajah gagal diproses'}
    else:
        encoding_bytes = zlib.compress(pickle.dumps(payload), level=9)
        encoding_b64 = base64.b64encode(encoding_bytes).decode('utf-8')
        result = {
            'success': True,
            'encoding_b64': encoding_b64,
            'jumlah_sampel': len(encoded_faces),
            'foto_referensi': foto_referensi or '',
        }

with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
    json.dump(result, f)

sys.exit(0)
