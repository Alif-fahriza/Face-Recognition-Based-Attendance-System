# 🎓 Sistem Absensi Face ID
### Upgrade dari Barcode → Face Recognition
**Platform:** Desktop Lokal (Windows) | **Stack:** Python + PHP + MySQL

---

## 📁 Struktur File

```
absensi-faceid/
├── app.py                  ← Flask API utama (JALANKAN INI)
├── face_utils.py           ← Core face recognition
├── db_connect.py           ← Koneksi MySQL
├── face_api_helper.php     ← Integrasi ke sistem PHP lama
├── database.sql            ← Schema database (import ke phpMyAdmin)
├── requirements.txt        ← Daftar library Python
├── .env                    ← Konfigurasi (edit sesuai kondisi)
├── templates/
│   └── index.html          ← Dashboard admin
└── foto_absensi/           ← Foto snapshot absensi (auto-created)
    ├── registrasi/
    ├── absensi/
    └── gagal/
```

---

## ⚙️ LANGKAH INSTALASI

### 1. Install Python (jika belum ada)
- Download Python 3.9+ dari https://python.org
- ✅ Centang **"Add Python to PATH"** saat instalasi

### 2. Install CMake (diperlukan oleh OpenCV)
```
pip install cmake
```

### 3. Install semua library Python
Buka CMD/Terminal di folder project, lalu:
```bash
pip install -r requirements.txt
```

> ⚠️ Jika ada error di opencv-contrib, coba:
> `pip install opencv-contrib-python`

### 4. Import Database
- Buka **phpMyAdmin** di browser
- Buat database baru: `absensi_db`
- Klik tab **Import** → pilih file `database.sql`
- Klik **Go**

### 5. Konfigurasi `.env`
Edit file `.env` sesuai kondisi PC:
```
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=         ← isi password MySQL jika ada
DB_NAME=absensi_db
CAMERA_INDEX=0       ← 0 = webcam pertama
```

### 6. Jalankan Service
```bash
python app.py
```

Jika berhasil, akan muncul:
```
✅ Koneksi database berhasil!
🚀 Server berjalan di: http://localhost:5000
```

### 7. Buka Dashboard
Buka browser → http://localhost:5000

---

## 🔄 ALUR PENGGUNAAN

### Pertama kali (Registrasi Wajah):
1. Buka halaman **Peserta**
2. Tambah peserta baru (isi nama, institusi, dll)
3. Klik tombol **"Daftar Wajah"** di samping nama
4. Jendela kamera terbuka → arahkan wajah
5. Sistem otomatis ambil 30 sampel
6. Selesai → wajah terdaftar

### Absensi Harian:
1. Buka halaman **Absensi**
2. Klik **Absen Masuk** (pagi) atau **Absen Keluar** (sore)
3. Jendela kamera terbuka
4. Arahkan wajah → sistem mengenali otomatis
5. Konfirmasi muncul → absensi tercatat

---

## 🔌 INTEGRASI KE SISTEM PHP LAMA

Copy file `face_api_helper.php` ke folder project PHP lama, lalu:

```php
require_once 'face_api_helper.php';

// Absensi masuk
$hasil = FaceAPI::absensiMasuk();
if ($hasil['success']) {
    echo "Selamat datang, " . $hasil['nama'];
}
```

---

## 🛠️ TROUBLESHOOTING

| Masalah | Solusi |
|---|---|
| `ModuleNotFoundError: cv2` | `pip install opencv-contrib-python` |
| Kamera tidak terbuka | Coba ganti `CAMERA_INDEX=1` di `.env` |
| Koneksi DB gagal | Cek password MySQL di `.env` |
| Wajah tidak dikenali | Lakukan ulang registrasi dengan pencahayaan lebih baik |
| Port 5000 sudah dipakai | Ganti `FLASK_PORT=5001` di `.env` |

---

## 📞 Catatan untuk Pengembangan Lanjutan

- [ ] Tambah liveness detection (anti foto)
- [ ] Export laporan ke Excel/PDF
- [ ] Notifikasi WhatsApp/email otomatis
- [ ] Multi-kamera support
- [ ] Integrasi dengan sistem HR yang ada
