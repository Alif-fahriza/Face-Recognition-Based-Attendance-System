<?php
/**
 * face_api_helper.php
 * Helper untuk memanggil Python Face ID Service dari PHP
 * Include file ini di halaman PHP absensi yang sudah ada
 * 
 * Contoh penggunaan:
 *   require_once 'face_api_helper.php';
 *   $hasil = FaceAPI::absensiMasuk();
 */

class FaceAPI {
    private static $BASE_URL = 'http://localhost:5000/api';
    private static $TIMEOUT  = 60; // detik (perlu waktu untuk scan wajah)

    /**
     * Kirim HTTP request ke Python service
     */
    private static function request($endpoint, $method = 'GET', $data = null) {
        $url = self::$BASE_URL . $endpoint;
        $ch  = curl_init($url);

        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => self::$TIMEOUT,
            CURLOPT_CUSTOMREQUEST  => $method,
        ]);

        if ($data !== null) {
            curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
            curl_setopt($ch, CURLOPT_HTTPHEADER, ['Content-Type: application/json']);
        }

        $response = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $error    = curl_error($ch);
        curl_close($ch);

        if ($error) {
            return ['success' => false, 'message' => 'Tidak dapat terhubung ke Face ID service: ' . $error];
        }

        $decoded = json_decode($response, true);
        return $decoded ?: ['success' => false, 'message' => 'Response tidak valid dari service'];
    }

    /**
     * Cek apakah Python service aktif
     */
    public static function cekStatus() {
        return self::request('/status');
    }

    /**
     * Absensi masuk — buka kamera & verifikasi wajah
     * Return: array dengan key: success, nama, confidence, status, waktu, message
     */
    public static function absensiMasuk() {
        return self::request('/absensi/masuk', 'POST');
    }

    /**
     * Absensi keluar — buka kamera & verifikasi wajah
     */
    public static function absensiKeluar() {
        return self::request('/absensi/keluar', 'POST');
    }

    /**
     * Daftarkan wajah peserta (buka kamera untuk registrasi)
     * @param int $pesertaId — ID peserta di database
     */
    public static function registrasiWajah($pesertaId) {
        return self::request("/registrasi-wajah/{$pesertaId}", 'POST');
    }

    /**
     * Ambil rekap absensi hari ini
     */
    public static function rekapHariIni() {
        return self::request('/rekap/hari-ini');
    }

    /**
     * Ambil semua peserta
     */
    public static function getAllPeserta() {
        return self::request('/peserta');
    }

    /**
     * Tambah peserta baru
     */
    public static function tambahPeserta($data) {
        return self::request('/peserta', 'POST', $data);
    }
}


/* ================================================================
 * CONTOH INTEGRASI: Ganti halaman absensi lama dengan kode ini
 * ================================================================

// File: absensi.php (modifikasi halaman absensi PHP yang lama)

session_start();
require_once 'face_api_helper.php';

$pesan   = '';
$berhasil = false;

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $tipe = $_POST['tipe'] ?? 'masuk'; // 'masuk' atau 'keluar'

    if ($tipe === 'masuk') {
        $hasil = FaceAPI::absensiMasuk();
    } else {
        $hasil = FaceAPI::absensiKeluar();
    }

    if ($hasil['success']) {
        $berhasil = true;
        $pesan = "Absensi {$tipe} berhasil! Selamat datang, {$hasil['nama']}. "
               . "Waktu: {$hasil['waktu']}";
    } else {
        $pesan = "Gagal: " . ($hasil['message'] ?? 'Wajah tidak dikenali');
    }
}
*/
?>
