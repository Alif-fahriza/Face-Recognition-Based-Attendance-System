-- ============================================
-- SCHEMA DATABASE SISTEM ABSENSI FACE ID
-- Jalankan file ini di phpMyAdmin
-- ============================================

CREATE DATABASE IF NOT EXISTS absensi_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE absensi_db;

-- ============================================
-- TABEL DIVISI / DEPARTEMEN
-- ============================================
CREATE TABLE IF NOT EXISTS divisi (
    id INT PRIMARY KEY AUTO_INCREMENT,
    nama VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO divisi (nama) VALUES 
    ('IT / Teknologi'),
    ('Administrasi'),
    ('Keuangan'),
    ('Marketing'),
    ('Operasional');

-- ============================================
-- TABEL PESERTA MAGANG
-- ============================================
CREATE TABLE IF NOT EXISTS peserta (
    id INT PRIMARY KEY AUTO_INCREMENT,
    nama VARCHAR(150) NOT NULL,
    email VARCHAR(150) UNIQUE,
    no_hp VARCHAR(20),
    divisi_id INT,
    institusi VARCHAR(150),              -- asal kampus/sekolah
    tanggal_mulai DATE NOT NULL,
    tanggal_selesai DATE NOT NULL,
    status ENUM('aktif', 'selesai', 'nonaktif') DEFAULT 'aktif',
    foto_profil VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (divisi_id) REFERENCES divisi(id) ON DELETE SET NULL
);

-- ============================================
-- TABEL FACE ENCODING (DATA WAJAH)
-- ============================================
CREATE TABLE IF NOT EXISTS face_encodings (
    id INT PRIMARY KEY AUTO_INCREMENT,
    peserta_id INT NOT NULL UNIQUE,
    encoding_data LONGBLOB NOT NULL,     -- numpy array sebagai bytes
    jumlah_sampel INT DEFAULT 0,         -- berapa foto dipakai untuk training
    foto_referensi VARCHAR(255),         -- path foto terbaik sebagai referensi
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (peserta_id) REFERENCES peserta(id) ON DELETE CASCADE
);

-- ============================================
-- TABEL ABSENSI
-- ============================================
CREATE TABLE IF NOT EXISTS absensi (
    id INT PRIMARY KEY AUTO_INCREMENT,
    peserta_id INT NOT NULL,
    tanggal DATE NOT NULL,
    jam_masuk TIME,
    jam_keluar TIME,
    foto_masuk VARCHAR(255),             -- snapshot saat absen masuk
    foto_keluar VARCHAR(255),            -- snapshot saat absen keluar
    confidence_masuk FLOAT,             -- tingkat keyakinan saat masuk (0-1)
    confidence_keluar FLOAT,            -- tingkat keyakinan saat keluar (0-1)
    status ENUM('hadir', 'terlambat', 'izin', 'alpha') DEFAULT 'hadir',
    keterangan TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (peserta_id) REFERENCES peserta(id) ON DELETE CASCADE,
    UNIQUE KEY unique_absensi (peserta_id, tanggal)
);

-- ============================================
-- TABEL LOG PERCOBAAN ABSENSI
-- (termasuk yang gagal / tidak dikenali)
-- ============================================
CREATE TABLE IF NOT EXISTS absensi_log (
    id INT PRIMARY KEY AUTO_INCREMENT,
    peserta_id INT,                      -- NULL jika tidak dikenali
    tipe ENUM('masuk', 'keluar') DEFAULT 'masuk',
    status ENUM('berhasil', 'gagal', 'tidak_dikenali') NOT NULL,
    confidence FLOAT,
    foto_percobaan VARCHAR(255),
    keterangan VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (peserta_id) REFERENCES peserta(id) ON DELETE SET NULL
);

-- ============================================
-- TABEL SETTING SISTEM
-- ============================================
CREATE TABLE IF NOT EXISTS setting (
    id INT PRIMARY KEY AUTO_INCREMENT,
    kunci VARCHAR(100) UNIQUE NOT NULL,
    nilai VARCHAR(255),
    keterangan TEXT
);

INSERT INTO setting (kunci, nilai, keterangan) VALUES
    ('jam_masuk_normal', '08:00', 'Jam masuk normal'),
    ('jam_masuk_toleransi', '08:15', 'Batas toleransi keterlambatan'),
    ('jam_keluar_normal', '17:00', 'Jam keluar normal'),
    ('confidence_threshold', '0.55', 'Minimum confidence untuk verifikasi wajah');

-- ============================================
-- VIEW: REKAP ABSENSI HARIAN (mudah diquery)
-- ============================================
CREATE OR REPLACE VIEW v_absensi_hari_ini AS
SELECT 
    p.id as peserta_id,
    p.nama,
    p.institusi,
    d.nama as divisi,
    a.tanggal,
    a.jam_masuk,
    a.jam_keluar,
    a.status,
    a.confidence_masuk,
    a.confidence_keluar
FROM peserta p
LEFT JOIN absensi a ON p.id = a.peserta_id AND a.tanggal = CURDATE()
LEFT JOIN divisi d ON p.divisi_id = d.id
WHERE p.status = 'aktif';

-- ============================================
-- DATA DUMMY UNTUK TESTING
-- ============================================
INSERT INTO peserta (nama, email, no_hp, divisi_id, institusi, tanggal_mulai, tanggal_selesai)
VALUES
    ('Budi Santoso', 'budi@test.com', '081234567890', 1, 'Universitas Andalas', CURDATE(), DATE_ADD(CURDATE(), INTERVAL 3 MONTH)),
    ('Siti Rahayu', 'siti@test.com', '081234567891', 2, 'Politeknik Negeri Padang', CURDATE(), DATE_ADD(CURDATE(), INTERVAL 3 MONTH)),
    ('Ahmad Fauzi', 'ahmad@test.com', '081234567892', 1, 'Universitas Bung Hatta', CURDATE(), DATE_ADD(CURDATE(), INTERVAL 3 MONTH));
