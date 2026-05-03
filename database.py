"""
BASE DE DATOS SQLite PARA MIA BOT
Clientes, tickets, pagos parciales, historial de credenciales, encuestas, renovaciones.
"""

import sqlite3
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
DB_PATH = "bot_mia.db"


class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._crear_tablas()

    def _crear_tablas(self):
        c = self.conn.cursor()

        c.execute("""CREATE TABLE IF NOT EXISTS clientes (
            telegram_id INTEGER PRIMARY KEY,
            nombre TEXT,
            username TEXT,
            primera_interaccion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            referencia TEXT UNIQUE NOT NULL,
            estado TEXT DEFAULT 'entregado',
            credencial_usuario TEXT,
            credencial_contrasena TEXT,
            monto_total REAL DEFAULT 45.0,
            monto_pagado REAL DEFAULT 0.0,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fecha_pago TIMESTAMP,
            fecha_revocacion TIMESTAMP,
            fecha_expiracion TIMESTAMP,
            recordatorios_enviados INTEGER DEFAULT 0,
            intervalo_horas INTEGER DEFAULT 1,
            ultimo_recordatorio TIMESTAMP,
            FOREIGN KEY (telegram_id) REFERENCES clientes(telegram_id)
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS credenciales_entregadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            ticket_id INTEGER NOT NULL,
            credencial_usuario TEXT NOT NULL,
            credencial_contrasena TEXT NOT NULL,
            fecha_entrega TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            es_reemplazo INTEGER DEFAULT 0,
            activa INTEGER DEFAULT 1,
            estado_cuenta TEXT DEFAULT 'entregada',
            FOREIGN KEY (telegram_id) REFERENCES clientes(telegram_id),
            FOREIGN KEY (ticket_id) REFERENCES tickets(id)
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS pagos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            monto REAL NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ticket_id) REFERENCES tickets(id)
        )""")

        # Encuestas de salida
        c.execute("""CREATE TABLE IF NOT EXISTS encuestas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            pregunta TEXT NOT NULL,
            respuesta TEXT NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (telegram_id) REFERENCES clientes(telegram_id)
        )""")

        self.conn.commit()
        logger.info("BD MIA inicializada")

    # ---- CLIENTES ----
    def registrar_cliente(self, tid, nombre, username):
        self.conn.execute("""
            INSERT INTO clientes (telegram_id, nombre, username) VALUES (?,?,?)
            ON CONFLICT(telegram_id) DO UPDATE SET nombre=excluded.nombre, username=excluded.username
        """, (tid, nombre, username))
        self.conn.commit()

    def es_cliente_existente(self, tid) -> bool:
        return self.conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE telegram_id=? AND estado='pagado'", (tid,)
        ).fetchone()[0] > 0

    def obtener_historial_cliente(self, tid) -> dict:
        tickets = self.conn.execute("""
            SELECT id, referencia, estado, credencial_usuario, monto_total, monto_pagado,
                   fecha_creacion, fecha_pago
            FROM tickets WHERE telegram_id=? ORDER BY fecha_creacion DESC
        """, (tid,)).fetchall()
        creds = self.conn.execute("""
            SELECT credencial_usuario, estado_cuenta, es_reemplazo, fecha_entrega
            FROM credenciales_entregadas WHERE telegram_id=? ORDER BY fecha_entrega DESC
        """, (tid,)).fetchall()
        return {
            "tickets": [dict(t) for t in tickets],
            "credenciales": [dict(c) for c in creds],
            "total_compras": sum(1 for t in tickets if t["estado"] == "pagado"),
            "total_reemplazos": sum(1 for c in creds if c["es_reemplazo"]),
        }

    # ---- TICKETS ----
    def crear_ticket(self, tid, ref, cred_user, cred_pass, monto_total: float) -> int:
        c = self.conn.execute("""
            INSERT INTO tickets (telegram_id, referencia, estado, credencial_usuario,
                                 credencial_contrasena, monto_total, ultimo_recordatorio)
            VALUES (?,?, 'entregado', ?,?,?,?)
        """, (tid, ref, cred_user, cred_pass, monto_total, datetime.now().isoformat()))
        self.conn.commit()
        return c.lastrowid

    def obtener_ticket_pendiente(self, tid) -> dict | None:
        r = self.conn.execute("""
            SELECT * FROM tickets WHERE telegram_id=? AND estado='entregado'
            ORDER BY fecha_creacion DESC LIMIT 1
        """, (tid,)).fetchone()
        return dict(r) if r else None

    def registrar_pago_parcial(self, ticket_id, monto):
        self.conn.execute("INSERT INTO pagos (ticket_id, monto) VALUES (?,?)", (ticket_id, monto))
        self.conn.execute("UPDATE tickets SET monto_pagado=monto_pagado+? WHERE id=?", (monto, ticket_id))
        self.conn.commit()

    def cerrar_ticket(self, ref, dias_soporte=25):
        ahora = datetime.now()
        exp = (ahora + timedelta(days=dias_soporte)).isoformat()
        self.conn.execute("""
            UPDATE tickets SET estado='pagado', fecha_pago=?, fecha_expiracion=? WHERE referencia=?
        """, (ahora.isoformat(), exp, ref))
        self.conn.commit()

    def revocar_ticket(self, ticket_id):
        self.conn.execute("""
            UPDATE tickets SET estado='revocado', fecha_revocacion=? WHERE id=?
        """, (datetime.now().isoformat(), ticket_id))
        self.conn.execute(
            "UPDATE credenciales_entregadas SET activa=0, estado_cuenta='revocada' WHERE ticket_id=?",
            (ticket_id,))
        self.conn.commit()

    def registrar_recordatorio(self, ticket_id):
        self.conn.execute("""
            UPDATE tickets SET recordatorios_enviados=recordatorios_enviados+1, ultimo_recordatorio=?
            WHERE id=?
        """, (datetime.now().isoformat(), ticket_id))
        self.conn.commit()

    def cambiar_intervalo(self, ticket_id, horas):
        self.conn.execute("UPDATE tickets SET intervalo_horas=? WHERE id=?", (horas, ticket_id))
        self.conn.commit()

    # ---- RENOVACIONES ----
    def obtener_tickets_por_expirar(self, dias_aviso=2) -> list[dict]:
        """Tickets pagados que expiran en los próximos N días."""
        ahora = datetime.now()
        limite = (ahora + timedelta(days=dias_aviso)).isoformat()
        rows = self.conn.execute("""
            SELECT t.*, c.nombre FROM tickets t
            JOIN clientes c ON c.telegram_id=t.telegram_id
            WHERE t.estado='pagado' AND t.fecha_expiracion IS NOT NULL
              AND t.fecha_expiracion <= ? AND t.fecha_expiracion > ?
        """, (limite, ahora.isoformat())).fetchall()
        return [dict(r) for r in rows]

    def obtener_tickets_expirados(self) -> list[dict]:
        """Tickets pagados cuya fecha de expiración ya pasó."""
        ahora = datetime.now().isoformat()
        rows = self.conn.execute("""
            SELECT t.*, c.nombre FROM tickets t
            JOIN clientes c ON c.telegram_id=t.telegram_id
            WHERE t.estado='pagado' AND t.fecha_expiracion IS NOT NULL
              AND t.fecha_expiracion <= ?
        """, (ahora,)).fetchall()
        return [dict(r) for r in rows]

    def expirar_ticket(self, ticket_id):
        """Marca ticket como expirado."""
        self.conn.execute(
            "UPDATE tickets SET estado='expirado' WHERE id=?", (ticket_id,))
        self.conn.execute(
            "UPDATE credenciales_entregadas SET activa=0, estado_cuenta='expirada' WHERE ticket_id=?",
            (ticket_id,))
        self.conn.commit()

    # ---- CREDENCIALES ----
    def obtener_credenciales_dadas_a_cliente(self, tid) -> list[str]:
        rows = self.conn.execute("""
            SELECT DISTINCT credencial_usuario FROM credenciales_entregadas WHERE telegram_id=?
        """, (tid,)).fetchall()
        return [r[0] for r in rows]

    def registrar_entrega(self, tid, ticket_id, user, pw, reemplazo=False):
        self.conn.execute("""
            INSERT INTO credenciales_entregadas
            (telegram_id, ticket_id, credencial_usuario, credencial_contrasena, es_reemplazo)
            VALUES (?,?,?,?,?)
        """, (tid, ticket_id, user, pw, 1 if reemplazo else 0))
        self.conn.commit()

    def marcar_cuenta_fallo(self, tid, cred_usuario):
        self.conn.execute("""
            UPDATE credenciales_entregadas SET estado_cuenta='fallo'
            WHERE telegram_id=? AND credencial_usuario=? AND activa=1
        """, (tid, cred_usuario))
        self.conn.commit()

    # ---- SOPORTE ----
    def obtener_compra_reciente(self, tid, dias=25):
        limite = (datetime.now() - timedelta(days=dias)).isoformat()
        r = self.conn.execute("""
            SELECT t.id as ticket_id, t.referencia, t.fecha_pago,
                   ce.credencial_usuario, ce.credencial_contrasena
            FROM tickets t
            JOIN credenciales_entregadas ce ON ce.ticket_id=t.id
            WHERE t.telegram_id=? AND t.estado='pagado' AND t.fecha_pago>=?
            ORDER BY t.fecha_pago DESC LIMIT 1
        """, (tid, limite)).fetchone()
        return dict(r) if r else None

    # ---- ENCUESTAS ----
    def guardar_encuesta(self, tid, pregunta, respuesta):
        self.conn.execute(
            "INSERT INTO encuestas (telegram_id, pregunta, respuesta) VALUES (?,?,?)",
            (tid, pregunta, respuesta))
        self.conn.commit()

    def obtener_resultados_encuesta(self) -> list[dict]:
        rows = self.conn.execute("""
            SELECT pregunta, respuesta, COUNT(*) as veces
            FROM encuestas GROUP BY pregunta, respuesta ORDER BY veces DESC
        """).fetchall()
        return [dict(r) for r in rows]

    # ---- STATS ----
    def obtener_estadisticas(self):
        c = self.conn
        return {
            "total_clientes": c.execute("SELECT COUNT(*) FROM clientes").fetchone()[0],
            "total_ventas": c.execute("SELECT COUNT(*) FROM tickets WHERE estado='pagado'").fetchone()[0],
            "tickets_pendientes": c.execute("SELECT COUNT(*) FROM tickets WHERE estado='entregado'").fetchone()[0],
            "revocados": c.execute("SELECT COUNT(*) FROM tickets WHERE estado='revocado'").fetchone()[0],
            "expirados": c.execute("SELECT COUNT(*) FROM tickets WHERE estado='expirado'").fetchone()[0],
            "ingresos": c.execute("SELECT COALESCE(SUM(monto),0) FROM pagos").fetchone()[0],
        }

    def obtener_ventas_recientes(self, n=10):
        rows = self.conn.execute("""
            SELECT t.referencia, t.fecha_pago, c.nombre, t.credencial_usuario, t.monto_pagado
            FROM tickets t JOIN clientes c ON c.telegram_id=t.telegram_id
            WHERE t.estado='pagado' ORDER BY t.fecha_pago DESC LIMIT ?
        """, (n,)).fetchall()
        return [dict(r) for r in rows]

    def obtener_historial_cambios(self):
        c = self.conn
        return {
            "total_reemplazos": c.execute(
                "SELECT COUNT(*) FROM credenciales_entregadas WHERE es_reemplazo=1").fetchone()[0],
            "cuentas_unicas_usadas": c.execute(
                "SELECT COUNT(DISTINCT credencial_usuario) FROM credenciales_entregadas").fetchone()[0],
        }
