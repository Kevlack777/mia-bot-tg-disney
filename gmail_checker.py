"""
MÓDULO DE VERIFICACIÓN DE GMAIL
Busca pagos por referencia, extrae monto real pagado, soporta pagos parciales.
"""

import imaplib
import email
import re
import logging
from email.header import decode_header
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

VENTANA_MINUTOS = 120  # Buscar en últimas 2 horas


class GmailChecker:
    def __init__(self, usuario: str, password: str):
        self.usuario = usuario
        self.password = password
        self.servidor = "imap.gmail.com"
        self.puerto = 993
        # msg_ids ya procesados por referencia (evita contar el mismo correo 2 veces)
        self.correos_procesados: dict[str, set[str]] = {}

    def _conectar(self):
        try:
            c = imaplib.IMAP4_SSL(self.servidor, self.puerto)
            c.login(self.usuario, self.password)
            return c
        except Exception as e:
            logger.error(f"Error Gmail: {e}")
            return None

    def buscar_pagos_por_referencia(self, referencia: str) -> list[dict]:
        """
        Busca TODOS los correos con esta referencia y extrae el monto de cada uno.

        Returns:
            Lista de dicts con 'monto' (float) y 'msg_id' (str).
            Ejemplo: [{"monto": 25.0, "msg_id": "123"}, {"monto": 20.0, "msg_id": "456"}]
        """
        if not self.usuario or not self.password:
            return []

        if referencia not in self.correos_procesados:
            self.correos_procesados[referencia] = set()

        conexion = self._conectar()
        if not conexion:
            return []

        pagos = []
        try:
            conexion.select("INBOX")
            fecha_desde = (datetime.now() - timedelta(days=2))
            fecha_str = fecha_desde.strftime("%d-%b-%Y")
            status, mensajes = conexion.search(None, f'(SINCE "{fecha_str}")')

            if status != "OK" or not mensajes[0]:
                return []

            ids_correo = mensajes[0].split()
            logger.info(f"{len(ids_correo)} correos revisados")

            for msg_id in reversed(ids_correo):
                mid = msg_id.decode()
                # Saltar correos ya contados para esta referencia
                if mid in self.correos_procesados[referencia]:
                    continue

                status, datos = conexion.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue

                mensaje = email.message_from_bytes(datos[0][1])
                asunto = self._decodificar_header(mensaje.get("Subject", ""))
                cuerpo = self._extraer_cuerpo(mensaje)
                texto = f"{asunto} {cuerpo}"

                if referencia.upper() in texto.upper():
                    monto = self._extraer_monto(texto)
                    if monto > 0:
                        self.correos_procesados[referencia].add(mid)
                        pagos.append({"monto": monto, "msg_id": mid})
                        logger.info(f"Pago encontrado: ${monto} con ref {referencia}")

        except Exception as e:
            logger.error(f"Error buscando: {e}")
        finally:
            try:
                conexion.logout()
            except Exception:
                pass

        return pagos

    def _extraer_monto(self, texto: str) -> float:
        """Extrae el monto en MXN del texto del correo."""
        # Buscar patrones como $45.00, $99.00, $25, etc.
        patrones = [
            r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)\s*MXN',  # $45.00 MXN
            r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:pesos|mxn)',  # $45.00 pesos
            r'Monto[:\s]*\$?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',  # Monto: $45.00
            r'\$\s*(\d+\.\d{2})',  # $45.00 genérico
        ]
        for patron in patrones:
            match = re.search(patron, texto, re.IGNORECASE)
            if match:
                monto_str = match.group(1).replace(",", "")
                try:
                    return float(monto_str)
                except ValueError:
                    continue
        return 0.0

    def _decodificar_header(self, header):
        try:
            partes = decode_header(header)
            resultado = ""
            for contenido, charset in partes:
                if isinstance(contenido, bytes):
                    resultado += contenido.decode(charset or "utf-8", errors="ignore")
                else:
                    resultado += contenido
            return resultado
        except Exception:
            return str(header)

    def _extraer_cuerpo(self, mensaje):
        cuerpo = ""
        try:
            if mensaje.is_multipart():
                for parte in mensaje.walk():
                    tipo = parte.get_content_type()
                    if tipo in ("text/plain", "text/html"):
                        payload = parte.get_payload(decode=True)
                        if payload:
                            texto = payload.decode("utf-8", errors="ignore")
                            if tipo == "text/html":
                                texto = self._html_a_texto(texto)
                            cuerpo += " " + texto
            else:
                payload = mensaje.get_payload(decode=True)
                if payload:
                    texto = payload.decode("utf-8", errors="ignore")
                    if mensaje.get_content_type() == "text/html":
                        texto = self._html_a_texto(texto)
                    cuerpo = texto
        except Exception as e:
            logger.error(f"Error cuerpo: {e}")
        return cuerpo

    def _html_a_texto(self, html):
        texto = re.sub(r'<[^>]+>', ' ', html)
        texto = texto.replace('&nbsp;', ' ').replace('&amp;', '&')
        texto = texto.replace('&lt;', '<').replace('&gt;', '>')
        return re.sub(r'\s+', ' ', texto).strip()
