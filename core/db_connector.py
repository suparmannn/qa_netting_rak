import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError, OperationalError


class DatabaseManager:
    """
    Connector read-only KHUSUS buat validasi QA Netting Bunga RAK.
    - SELECT-only (gak ada mode "force"/override kayak tools lain - QA tool ini
      emang gak pernah butuh nulis apa pun ke DB, jadi proteksinya permanen).
    - Dukung PostgreSQL & MySQL/MariaDB (parameter terpisah, aman utk password
      yang ada karakter @/:).
    """

    def __init__(self):
        self.engine = None
        self.connection_status = False
        self.db_type = None

    def connect(self, db_config: dict) -> tuple[bool, str]:
        try:
            db_type = db_config.get("type", "").lower()
            self.db_type = db_type

            connection_params = {
                "host": db_config["host"],
                "port": db_config["port"],
                "database": db_config["database"],
                "user": db_config["user"],
                "password": db_config["password"],
                "connect_timeout": 10,
            }

            if db_type == "postgresql":
                self.engine = create_engine(
                    "postgresql+psycopg2://",
                    connect_args={**connection_params, "options": "-c default_transaction_read_only=on"},
                    echo=False,
                )
            elif db_type in ("mysql", "mariadb"):
                self.engine = create_engine(
                    "mysql+pymysql://",
                    connect_args=connection_params,
                    echo=False,
                )
            else:
                raise ValueError(f"Tipe database belum didukung: {db_type}")

            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            self.connection_status = True
            return True, "Berhasil terhubung ke database (read-only)."

        except OperationalError as e:
            self.connection_status = False
            msg = str(e)
            if "timeout" in msg.lower():
                return False, f"KONEKSI TIMEOUT - server tidak merespon.\n\nDetail: {msg}\n\nTips: cek apakah IP kamu perlu di-whitelist."
            if "password authentication failed" in msg.lower() or "access denied" in msg.lower():
                return False, f"AKSES DITOLAK - username/password salah.\n\nDetail: {msg}"
            if "does not exist" in msg.lower() or "unknown database" in msg.lower():
                return False, f"DATABASE TIDAK DITEMUKAN.\n\nDetail: {msg}"
            return False, f"GAGAL KONEKSI.\n\nDetail: {msg}\n\nTips: cek host, port, dan pastikan server database menyala."
        except SQLAlchemyError as e:
            self.connection_status = False
            return False, f"DATABASE ERROR: {e}"
        except Exception as e:
            self.connection_status = False
            return False, f"ERROR TIDAK DIKENAL: {e}"

    def disconnect(self):
        if self.engine:
            self.engine.dispose()
        self.connection_status = False
        self.engine = None

    def query_df(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        """Jalankan SELECT dan kembalikan DataFrame. Non-SELECT ditolak keras."""
        if not self.connection_status:
            raise Exception("Belum konek ke database.")
        stripped = sql.strip().upper()
        if not (stripped.startswith("SELECT") or stripped.startswith("WITH")):
            raise Exception("Tool ini read-only - cuma boleh SELECT/WITH.")
        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params or {})
