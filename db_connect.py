"""
db_connect.py
Modul koneksi ke MySQL dengan auto-reconnect
"""
import mysql.connector
from mysql.connector import Error, errorcode
import os
import time
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """Buat koneksi baru ke MySQL (fresh connection setiap kali)"""
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            database=os.getenv('DB_NAME', 'absensi_db'),
            charset='utf8mb4',
            connection_timeout=30,
            autocommit=False,
        )
        return conn
    except Error as e:
        print(f"[DB ERROR] Gagal koneksi ke database: {e}")
        return None


def execute_query(query, params=None, fetch=False, retry=3):
    """
    Helper untuk eksekusi query dengan auto-retry.
    fetch=True  → return hasil SELECT
    fetch=False → eksekusi INSERT/UPDATE/DELETE, return lastrowid
    retry       → jumlah percobaan ulang jika koneksi putus
    """
    last_error = None

    for attempt in range(1, retry + 1):
        conn = None
        try:
            conn = get_connection()
            if not conn:
                raise Error("Tidak dapat membuat koneksi ke database")

            cursor = conn.cursor(dictionary=True)
            cursor.execute(query, params or ())

            if fetch:
                result = cursor.fetchall()
                cursor.close()
                conn.close()
                return result
            else:
                conn.commit()
                last_id = cursor.lastrowid
                cursor.close()
                conn.close()
                return last_id

        except Error as e:
            last_error = e
            # Tutup koneksi yang bermasalah
            try:
                if conn and conn.is_connected():
                    conn.rollback()
                    conn.close()
            except Exception:
                pass

            # Cek apakah error karena koneksi putus (bisa di-retry)
            recoverable = e.errno in (
                2006,  # MySQL server has gone away
                2013,  # Lost connection to MySQL server
                2055,  # Lost connection during query
                1040,  # Too many connections
            )

            if recoverable and attempt < retry:
                print(
                    f"[DB] Koneksi terputus (attempt {attempt}/{retry}), mencoba ulang...")
                time.sleep(1 * attempt)  # tunggu 1s, 2s, 3s
                continue
            else:
                print(
                    f"[DB ERROR] Query gagal setelah {attempt} percobaan: {e}")
                return None

    print(f"[DB ERROR] Semua {retry} percobaan gagal: {last_error}")
    return None


def test_connection():
    """Test apakah koneksi database berhasil"""
    conn = get_connection()
    if conn and conn.is_connected():
        print("[DB] ✅ Koneksi database berhasil!")
        conn.close()
        return True
    else:
        print("[DB] ❌ Koneksi database gagal!")
        return False
