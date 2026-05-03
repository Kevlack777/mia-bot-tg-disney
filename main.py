"""
MIA BOT - Venta de cuentas Disney+
Pagos parciales, historial completo, soporte 25 días.
"""

import os, csv, random, string, logging, asyncio, glob
from datetime import datetime, timedelta

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from seguimiento import (
    iniciar_encuesta, programar_followup, programar_renovacion,
    cancelar_followups, crear_teclado_encuesta, ENCUESTA_PREGUNTAS,
)
from gmail_checker import GmailChecker
from ai_agent import AgenteIA
from database import Database

load_dotenv()
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("TU_TELEGRAM_ID", "0"))
CSV_PATH = os.getenv("CSV_PATH", "credentials.csv")
PRECIO = float(os.getenv("PRECIO", "45"))
DIAS_SOPORTE = 25
COOLDOWN = 60
CLABE = os.getenv("CLABE", "")
CUENTA_OXXO = os.getenv("CUENTA_OXXO", "")
TITULAR = os.getenv("TITULAR", "")
BANCO = os.getenv("BANCO", "")
ADMIN_PASS = "kevlack"
ALERTA_300 = False
ALERTA_400 = False


# ---- POOL ----
def cargar_pool(ruta):
    pool = []
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            for fila in csv.DictReader(f):
                u = fila.get("usuario", fila.get("user", ""))
                p = fila.get("contraseña", fila.get("contrasena", fila.get("password", "")))
                if u and p:
                    pool.append({"usuario": u.strip(), "contrasena": p.strip()})
        logger.info(f"Pool: {len(pool)} cuentas")
    except Exception as e:
        logger.error(f"CSV: {e}")
    return pool

def elegir_cred(pool, excluir):
    ok = [c for c in pool if c["usuario"] not in excluir]
    return random.choice(ok) if ok else None

def gen_ref():
    return "PLA" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))


pool = cargar_pool(CSV_PATH)
db = Database()
gmail = GmailChecker(os.getenv("GMAIL_USER"), os.getenv("GMAIL_PASSWORD"))
mia = AgenteIA()
ultimo_chequeo: dict[int, datetime] = {}
ultimas_resp: dict[int, str] = {}
admin_autenticado: set[int] = set()
clientes_indecisos: set[int] = set()
refs_enviadas: dict[int, str] = {}  # tid -> '80' o '100' (qué porción ya se envió)

# ---- REFERENCIAS (fotos de prueba) ----
REFS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "referencias")
def cargar_referencias():
    fotos = sorted(glob.glob(os.path.join(REFS_DIR, "*.jpg")) + glob.glob(os.path.join(REFS_DIR, "*.png")))
    corte = int(len(fotos) * 0.8)
    return fotos[:corte], fotos[corte:]  # 80%, 20%

REFS_80, REFS_20 = cargar_referencias()
logger.info(f"Referencias: {len(REFS_80)} (80%) + {len(REFS_20)} (20%)")

async def enviar_refs_80(bot, tid):
    if refs_enviadas.get(tid) in ('80', '100'): return  # Ya se mandaron
    refs_enviadas[tid] = '80'
    await bot.send_message(tid, "📸 *Mira lo que dicen nuestros clientes:*", parse_mode="Markdown")
    for foto in REFS_80:
        try:
            with open(foto, 'rb') as f:
                await bot.send_photo(tid, f)
        except Exception as e:
            logger.error(f"Foto: {e}")

async def enviar_refs_20(bot, tid):
    if refs_enviadas.get(tid) == '100': return  # Ya se mandó todo
    refs_enviadas[tid] = '100'
    await bot.send_message(tid, "📸 *Más referencias de clientes satisfechos:*", parse_mode="Markdown")
    for foto in REFS_20:
        try:
            with open(foto, 'rb') as f:
                await bot.send_photo(tid, f)
        except Exception as e:
            logger.error(f"Foto: {e}")


# ---- HELPERS ----
async def admin_msg(ctx, texto):
    try:
        await ctx.bot.send_message(ADMIN_ID, texto, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Admin: {e}")

async def check_alertas_venta(ctx):
    """Revisa umbrales de venta y alerta al jefe."""
    global ALERTA_300, ALERTA_400
    s = db.obtener_estadisticas()
    ingresos = s["ingresos"]
    if ingresos >= 400 and not ALERTA_400:
        ALERTA_400 = True
        await admin_msg(ctx, "🚨🚨🚨 *URGENTE YA SACA DINERO JEFE* 🚨🚨🚨\n\n"
            f"💰 Llevamos *${ingresos:.0f}* en ventas.\nRetira la lana ya, jefe. 💸")
    elif ingresos >= 300 and not ALERTA_300:
        ALERTA_300 = True
        await admin_msg(ctx, "💰 *¡Hey jefe!* Ya llevamos *${:.0f}* en ventas.\n"
            "Ve pensando en retirar. 👀".format(ingresos))


def ctx_cliente(tid):
    """Genera contexto completo del cliente para MIA."""
    hist = db.obtener_historial_cliente(tid)
    es_cliente = db.es_cliente_existente(tid)
    ticket = db.obtener_ticket_pendiente(tid)

    partes = []
    if es_cliente:
        partes.append(f"Cliente recurrente. Ha comprado {hist['total_compras']} veces.")
        if hist["total_reemplazos"] > 0:
            partes.append(f"Ha pedido {hist['total_reemplazos']} reemplazos.")
    else:
        partes.append("Cliente nuevo, primera vez.")

    if ticket:
        pagado = ticket["monto_pagado"]
        total = ticket["monto_total"]
        partes.append(f"Tiene cuenta entregada (ref {ticket['referencia']}). Pagado ${pagado:.0f} de ${total:.0f}.")

    # Historial de credenciales
    for c in hist["credenciales"][:5]:
        estado = c["estado_cuenta"]
        partes.append(f"Cuenta {c['credencial_usuario']}: {estado}")

    return " ".join(partes)


def detectar_intencion(texto):
    t = texto.lower().strip()
    if any(p in t for p in ["ya pagué", "ya pague", "pagué", "pague", "hice el pago",
                             "ya transferí", "ya transferi", "ya deposite", "ya deposité"]):
        return "verificar_pago"
    if any(p in t for p in ["no funciona", "no sirve", "no puedo entrar", "error", "soporte",
                             "no jala", "falla", "contraseña incorrecta", "no me deja",
                             "dos pasos", "cambiar cuenta", "otra cuenta", "no entra"]):
        return "soporte"
    if any(p in t for p in ["pagar", "datos de pago", "donde pago", "dónde pago",
                             "como pago", "cómo pago", "depositar"]):
        return "pagar"
    if any(p in t for p in ["hola", "inicio", "start", "buenas"]):
        return "bienvenida"
    if any(p in t for p in ["si dame", "sí dame", "si quiero", "sí quiero", "dale",
                             "pásame", "pasame", "mándame", "mandame", "dame mi cuenta",
                             "quiero mi cuenta", "si por favor", "va dale", "si pasala",
                             "sí pásala"]):
        return "quiere_cuenta"
    if any(p in t for p in ["no gracias", "no quiero", "no por ahora", "lo pienso",
                             "lo voy a pensar", "despues", "después", "no me interesa",
                             "luego", "tal vez", "quizás", "quizas", "ahorita no"]):
        return "rechazo"
    if any(p in t for p in ["referencias", "pruebas", "comprobantes", "evidencia",
                             "capturas", "es seguro", "es confiable", "no confío",
                             "cómo sé que", "como se que", "es real", "es estafa",
                             "testimonios", "reseñas"]):
        return "referencias"
    return "ia"


# ---- HANDLERS ----
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.registrar_cliente(user.id, user.full_name, user.username)
    ticket = db.obtener_ticket_pendiente(user.id)

    if ticket:
        pagado = ticket["monto_pagado"]
        total = ticket["monto_total"]
        resta = total - pagado
        msg = (
            f"👋 *¡Hola de nuevo, {user.first_name}!* Soy *MIA* 😊\n\n"
            f"Tienes una cuenta pendiente de pago.\n"
            f"Ref: `{ticket['referencia']}`\n"
            f"💰 Pagado: ${pagado:.0f} / ${total:.0f} (falta ${resta:.0f})\n\n"
            "Escribe *pagar* para ver los datos, o pregúntame si necesitas ayuda."
        )
    elif db.es_cliente_existente(user.id):
        msg = (
            f"👋 *¡Hola, {user.first_name}!* Soy *MIA* 😊\n\n"
            "¡Qué bueno que regresas! ¿En qué puedo ayudarte?\n"
            "🔧 *soporte* — Problemas con tu cuenta\n"
            "🛒 ¿Otra cuenta? Solo dime\n\n"
            "O pregúntame lo que necesites 🎬"
        )
    else:
        msg = (
            f"👋 *¡Hola, {user.first_name}!* Soy *MIA* 😊\n\n"
            "Te ayudo con cuentas de *Disney+*: Marvel, Star Wars, "
            "Pixar, National Geographic y mucho más.\n\n"
            f"💰 Solo *${PRECIO:.0f} MXN*\n\n"
            "¿Ya has comprado con nosotros antes o es tu primera vez?\n"
            "Pregúntame lo que quieras 🎬"
        )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    s = db.obtener_estadisticas()
    await update.message.reply_text(
        f"📊 *MIA*\n👥 {s['total_clientes']} | 💰 {s['total_ventas']} ventas | "
        f"🎫 {s['tickets_pendientes']} pendientes | ❌ {s['revocados']} revocados\n"
        f"💵 Ingresos: ${s['ingresos']:.0f} | Pool: {len(pool)} cuentas",
        parse_mode="Markdown",
    )

async def cmd_ventas(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    ventas = db.obtener_ventas_recientes(10)
    if not ventas:
        await update.message.reply_text("Sin ventas."); return
    lines = ["📋 *Ventas:*\n"]
    for v in ventas:
        lines.append(f"• {v['nombre']} `{v['referencia']}` {v['credencial_usuario']} ${v['monto_pagado']:.0f}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_recargar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    global pool
    pool = cargar_pool(CSV_PATH)
    await update.message.reply_text(f"🔄 {len(pool)} cuentas", parse_mode="Markdown")

async def cmd_responder(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        args = update.message.text.split(maxsplit=2)
        cid = int(args[1])
        # Mostrar último mensaje del cliente
        ultimo = ultimas_resp.get(cid, "(sin mensajes)")
        await ctx.bot.send_message(cid, f"💬 *MIA:*\n\n{args[2]}", parse_mode="Markdown")
        await update.message.reply_text(f"Enviado a `{cid}`.\n💬 Último msg del cliente: _{ultimo}_", parse_mode="Markdown")
    except (IndexError, ValueError):
        # Si solo puso /responder ID sin msg, mostrar último mensaje
        try:
            cid = int(args[1])
            ultimo = ultimas_resp.get(cid, "(sin mensajes)")
            await update.message.reply_text(f"💬 Último msg de `{cid}`: _{ultimo}_\n\nUso: `/responder {cid} tu mensaje`", parse_mode="Markdown")
        except:
            await update.message.reply_text("Uso: `/responder ID msg`", parse_mode="Markdown")

async def cmd_confirmar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        cid = int(update.message.text.split()[1])
        ticket = db.obtener_ticket_pendiente(cid)
        if not ticket:
            await update.message.reply_text("Sin ticket pendiente."); return
        db.registrar_pago_parcial(ticket["id"], ticket["monto_total"] - ticket["monto_pagado"])
        db.cerrar_ticket(ticket["referencia"])
        cancelar_jobs(ctx, cid, ticket["referencia"])
        await ctx.bot.send_message(cid,
            f"✅ *¡Pago confirmado!* Tu Disney+ está asegurado por *{DIAS_SOPORTE} días*.\n"
            "Si tienes problemas, escribe *soporte*. ¡Disfruta! 🎬🍿",
            parse_mode="Markdown")
        await update.message.reply_text(f"Ticket `{ticket['referencia']}` confirmado.")
    except: await update.message.reply_text("Uso: `/confirmar ID`", parse_mode="Markdown")


def cancelar_jobs(ctx, tid, ref):
    jq = getattr(ctx, 'job_queue', None)
    if not jq: return
    for name in [f"rec_{tid}_{ref}", f"rev_{tid}_{ref}"]:
        for job in jq.get_jobs_by_name(name):
            job.schedule_removal()


# ---- PANEL ADMIN SECRETO ----
async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Comando secreto: /admin kevlack + subcomandos de prueba"""
    args = update.message.text.split(maxsplit=1)
    if len(args) < 2:
        return
    sub = args[1].strip().lower()
    uid = update.effective_user.id

    # ---- PRUEBAS DE SIMULACIÓN ----
    if sub == "25dias":
        compra = db.obtener_compra_reciente(uid, dias=9999)
        if not compra:
            await update.message.reply_text("No tienes compras, jefe. Primero haz una."); return
        await update.message.reply_text("🧪 *Simulando 25 días...*", parse_mode="Markdown")
        from seguimiento import aviso_renovacion
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Sí, quiero renovar", callback_data=f"renov_si_{compra['referencia']}")],
            [InlineKeyboardButton("❌ No, gracias", callback_data=f"renov_no_{compra['referencia']}")],
        ])
        await ctx.bot.send_message(uid,
            "⏰ *¡Tu cuenta Disney+ está por vencer!*\n\nEn 2 días se desactivará.\n¿Quieres renovar? 😊",
            reply_markup=teclado, parse_mode="Markdown")
        return

    if sub == "malo":
        ticket = db.obtener_ticket_pendiente(uid)
        if not ticket:
            await update.message.reply_text("No tienes ticket pendiente, jefe."); return
        await update.message.reply_text("🧪 *Simulando no-pago (24h)...*", parse_mode="Markdown")
        db.revocar_ticket(ticket["id"])
        ref = ticket["referencia"]
        jq = getattr(ctx, 'job_queue', None)
        if jq:
            for name in [f"rec_{uid}_{ref}", f"rev_{uid}_{ref}"]:
                for job in jq.get_jobs_by_name(name):
                    job.schedule_removal()
        await ctx.bot.send_message(uid,
            "❌ *Tu cuenta Disney+ fue desactivada* por falta de pago.\nSi quieres otra, escríbeme 😊",
            parse_mode="Markdown")
        await admin_msg(ctx,
            f"❌ *Revocada (simulación)*\n`{uid}` | `{ref}`\n"
            f"📦 `{ticket['credencial_usuario']}` / `{ticket['credencial_contrasena']}`\nQuémala, jefe.")
        return

    # ---- PANEL PRINCIPAL ----
    if sub != ADMIN_PASS:
        return

    admin_autenticado.add(uid)
    s = db.obtener_estadisticas()
    hist = db.obtener_historial_cambios()

    await update.message.reply_text(
        f"👑 *Panel Admin — Bienvenido jefe*\n\n"
        f"💰 Ventas totales: *${s['ingresos']:.0f} MXN*\n"
        f"🛒 Ventas completadas: *{s['total_ventas']}*\n"
        f"🎫 Pendientes de pago: *{s['tickets_pendientes']}*\n"
        f"❌ Revocados: *{s['revocados']}*\n"
        f"👥 Clientes: *{s['total_clientes']}*\n"
        f"🔄 Cambios/reemplazos: *{hist['total_reemplazos']}*\n"
        f"📦 Cuentas en pool: *{len(pool)}*\n"
        f"📊 Cuentas únicas usadas: *{hist['cuentas_unicas_usadas']}*\n\n"
        f"{'⚠️ *Actualiza la BD de cuentas*' if hist['total_reemplazos'] > len(pool) * 0.5 else '✅ BD OK'}\n\n"
        "*Comandos, jefe:*\n"
        "`/status` — Resumen\n"
        "`/ventas` — Últimas ventas\n"
        "`/cliente ID` — Info cliente\n"
        "`/confirmar ID` — Confirmar pago\n"
        "`/responder ID` — Ver último msg + responder\n"
        "`/recargar` — Recargar credentials.csv\n"
        "`/cuenta` — Cuenta para ti\n\n"
        "*🧪 Pruebas:*\n"
        "`/admin 25dias` — Simular renovación\n"
        "`/admin malo` — Simular no-pago",
        parse_mode="Markdown",
    )


async def cmd_cliente(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Busca info completa de un cliente."""
    if update.effective_user.id not in admin_autenticado and update.effective_user.id != ADMIN_ID:
        return
    try:
        cid = int(update.message.text.split()[1])
    except:
        await update.message.reply_text("Uso: `/cliente ID`", parse_mode="Markdown")
        return

    hist = db.obtener_historial_cliente(cid)
    if not hist["tickets"] and not hist["credenciales"]:
        await update.message.reply_text(f"No hay datos del cliente `{cid}`, jefe.", parse_mode="Markdown")
        return

    lines = [f"👤 *Cliente `{cid}`*\n"]
    lines.append(f"🛒 Compras: *{hist['total_compras']}* | 🔄 Reemplazos: *{hist['total_reemplazos']}*\n")

    for t in hist["tickets"][:5]:
        emoji = {"pagado": "✅", "entregado": "🎫", "revocado": "❌"}.get(t["estado"], "❓")
        lines.append(f"{emoji} `{t['referencia']}` — {t['estado']} — {t['credencial_usuario']} — ${t['monto_pagado']:.0f}/{t['monto_total']:.0f}")

    lines.append("\n*Cuentas:*")
    for c in hist["credenciales"][:10]:
        estado = c["estado_cuenta"]
        emoji = {"funciono": "✅", "fallo": "❌", "entregada": "📦", "revocada": "🚫"}.get(estado, "❓")
        remp = " (reemplazo)" if c["es_reemplazo"] else ""
        lines.append(f"{emoji} `{c['credencial_usuario']}` — {estado}{remp}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_cuenta_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Da una cuenta Disney+ al admin."""
    if update.effective_user.id not in admin_autenticado and update.effective_user.id != ADMIN_ID:
        return
    cred = elegir_cred(pool, [])
    if not cred:
        await update.message.reply_text("No hay cuentas, jefe.")
        return
    await update.message.reply_text(
        f"🎬 *Tu cuenta, jefe:*\n\n👤 `{cred['usuario']}`\n🔑 `{cred['contrasena']}`\n\nDisfruta 👑",
        parse_mode="Markdown")


# ---- LÓGICA PRINCIPAL ----
async def procesar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    user = update.effective_user
    db.registrar_cliente(user.id, user.full_name, user.username)
    ultimas_resp[user.id] = texto

    intent = detectar_intencion(texto)
    logger.info(f"{user.full_name}: {texto} -> {intent}")

    if intent == "verificar_pago": await verificar_pago(update, ctx); return
    if intent == "soporte": await manejar_soporte(update, ctx); return
    if intent == "pagar": await mostrar_pago(update, ctx); return
    if intent == "bienvenida": await cmd_start(update, ctx); return
    if intent == "quiere_cuenta":
        cancelar_followups(ctx, user.id)
        clientes_indecisos.discard(user.id)
        await entregar_cuenta(update, ctx); return
    if intent == "rechazo":
        if user.id not in clientes_indecisos:
            clientes_indecisos.add(user.id)
            await update.message.reply_text("¡Sin problema! Si cambias de opinión estoy aquí 😊")
            await programar_followup(ctx, user.id, 0)
            await iniciar_encuesta(ctx.bot, user.id)
        else:
            await update.message.reply_text("¡Entendido! Cuando quieras, aquí estaré 😊")
        return
    if intent == "referencias":
        await enviar_refs_80(ctx.bot, user.id)
        ya_vio = refs_enviadas.get(user.id)
        if ya_vio == '80':
            await update.message.reply_text("¡Ahí tienes! Si quieres ver más, solo dime 😊")
        elif ya_vio == '100':
            await update.message.reply_text("¡Ya te mandé todas! ¿Te animas? 😊")
        return

    # MIA (Groq)
    contexto = ctx_cliente(user.id)
    resp, ok = mia.responder(user.id, texto, contexto)
    if ok and resp:
        if "GENERAR_CUENTA" in resp:
            resp = resp.replace("GENERAR_CUENTA", "").strip()
            if resp: await update.message.reply_text(resp)
            await entregar_cuenta(update, ctx)
            return
        await update.message.reply_text(resp)
    else:
        await update.message.reply_text("Déjame pasar tu mensaje al equipo, te ayudamos pronto 😊")
        await admin_msg(ctx, f"🚨 *Escalación*\n👤 {user.full_name} (`{user.id}`)\n💬 _{texto}_\n`/responder {user.id} msg`")


# ---- ENTREGA CUENTA ----
async def entregar_cuenta(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ticket = db.obtener_ticket_pendiente(user.id)
    if ticket:
        await update.message.reply_text(
            f"Ya tienes una cuenta activa 😊\n\n"
            f"👤 `{ticket['credencial_usuario']}`\n🔑 `{ticket['credencial_contrasena']}`\n\n"
            "¿Necesitas ayuda para configurarla? ¿En qué dispositivo? 📺",
            parse_mode="Markdown")
        return

    ya_dadas = db.obtener_credenciales_dadas_a_cliente(user.id)
    cred = elegir_cred(pool, ya_dadas)
    if not cred:
        await update.message.reply_text("No hay cuentas disponibles ahora. Contacta soporte.")
        await admin_msg(ctx, f"🚨 Sin cuentas para {user.full_name} (`{user.id}`)")
        return

    ref = gen_ref()
    tid = db.crear_ticket(user.id, ref, cred["usuario"], cred["contrasena"], PRECIO)
    db.registrar_entrega(user.id, tid, cred["usuario"], cred["contrasena"])

    await update.message.reply_text(
        "🎬 *¡Aquí están tus credenciales de Disney+!*\n\n"
        f"👤 Usuario: `{cred['usuario']}`\n🔑 Contraseña: `{cred['contrasena']}`\n\n"
        f"🔖 Tu referencia: `{ref}`\n\n"
        "Pruébalas ahora mismo 😊 ¿En qué dispositivo las vas a usar?\n"
        "• Smart TV • Roku • Fire Stick • Celular • PC • Consola",
        parse_mode="Markdown")

    await admin_msg(ctx,
        f"🎫 *Cuenta entregada*\n👤 {user.full_name} (`{user.id}`)\n"
        f"🔖 `{ref}` | 📦 `{cred['usuario']}`")

    ctx.job_queue.run_repeating(recordar, interval=3600, first=3600,
        data={"tid": user.id, "tkid": tid, "ref": ref}, name=f"rec_{user.id}_{ref}")
    ctx.job_queue.run_once(revocar, when=86400,
        data={"tid": user.id, "tkid": tid, "ref": ref}, name=f"rev_{user.id}_{ref}")


# ---- PAGO ----
async def mostrar_pago(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ticket = db.obtener_ticket_pendiente(user.id)
    if not ticket:
        await update.message.reply_text("No tienes cuenta pendiente. ¿Quieres que te pase una? 😊")
        return
    ref = ticket["referencia"]
    pagado = ticket["monto_pagado"]
    total = ticket["monto_total"]
    resta = total - pagado

    msg_pagado = ""
    if pagado > 0:
        msg_pagado = f"\n✅ Ya pagaste: *${pagado:.0f}*\n💰 Restante: *${resta:.0f} MXN*\n"
    else:
        msg_pagado = f"\n💰 Monto: *${total:.0f}.00 MXN*\n"

    await update.message.reply_text(
        "💳 *Datos para tu pago*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🏦 *Transferencia*\n• Banco: *{BANCO}*\n• Titular: *{TITULAR}*\n• CLABE: `{CLABE}`\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🏪 *OXXO*\n• Tarjeta: `{CUENTA_OXXO}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n{msg_pagado}\n"
        f"📝 Concepto: *{ref}*\n\n"
        f"Pon `{ref}` como referencia/concepto.\nDespués escribe *ya pagué* ✅",
        parse_mode="Markdown")


# ---- VERIFICAR PAGO ----
async def verificar_pago(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ticket = db.obtener_ticket_pendiente(user.id)
    if not ticket:
        await update.message.reply_text("No tienes pago pendiente. ¿Necesitas ayuda? 😊")
        return

    ref = ticket["referencia"]
    ahora = datetime.now()
    ult = ultimo_chequeo.get(user.id)
    if ult and (ahora - ult).total_seconds() < COOLDOWN:
        await update.message.reply_text("⏳ Espera 1 minuto."); return
    ultimo_chequeo[user.id] = ahora

    espera = await update.message.reply_text(f"🔍 *Buscando pagos con ref `{ref}`...*", parse_mode="Markdown")

    try:
        pagos = await asyncio.to_thread(gmail.buscar_pagos_por_referencia, ref)
    except Exception as e:
        logger.error(f"Gmail: {e}")
        await espera.edit_text("Error verificando. Reintenta."); return

    if not pagos:
        await espera.edit_text(
            f"⏳ No encontré pagos con ref `{ref}`.\n\n"
            f"• Pon *{ref}* como concepto\n• Espera 1-2 min tras pagar",
            parse_mode="Markdown")
        return

    # Sumar montos de todos los pagos encontrados
    total_nuevo = sum(p["monto"] for p in pagos)
    for p in pagos:
        db.registrar_pago_parcial(ticket["id"], p["monto"])

    # Recargar ticket con montos actualizados
    ticket = db.obtener_ticket_pendiente(user.id)
    pagado = ticket["monto_pagado"]
    total = ticket["monto_total"]
    resta = total - pagado

    if resta <= 0.50:  # Tolerancia de centavos
        # PAGO COMPLETO
        db.cerrar_ticket(ref)
        cancelar_jobs(ctx, user.id, ref)

        await espera.edit_text(
            "✅ *¡Pago completo confirmado!*\n\n"
            f"Tu Disney+ está asegurado por *{DIAS_SOPORTE} días* 🎉\n"
            "Si tienes problemas, escribe *soporte*.\n¡Disfruta! 🎬🍿",
            parse_mode="Markdown")

        await admin_msg(ctx,
            f"💰 *VENTA, jefe!*\n👤 {user.full_name} (`{user.id}`)\n"
            f"🔖 `{ref}` | 📦 `{ticket['credencial_usuario']}` | ${pagado:.0f}")
        await check_alertas_venta(ctx)
        await programar_renovacion(ctx, user.id, ref, DIAS_SOPORTE)
    else:
        # PAGO PARCIAL
        msg = mia.generar_mensaje_pago_parcial(pagado, total, ref)
        await espera.edit_text(
            f"💳 *Pago parcial detectado*\n\n"
            f"✅ Pagado: *${pagado:.0f}*\n"
            f"⏳ Falta: *${resta:.0f} MXN*\n\n"
            f"{msg}\n\n"
            f"Usa la misma referencia `{ref}` para el pago restante.\n"
            "Después escribe *ya pagué* otra vez ✅",
            parse_mode="Markdown")

        await admin_msg(ctx,
            f"💳 *Pago parcial*\n{user.full_name} | `{ref}` | ${pagado:.0f}/{total:.0f}")


# ---- RECORDATORIOS ----
async def recordar(ctx: ContextTypes.DEFAULT_TYPE):
    d = ctx.job.data
    ticket = db.obtener_ticket_pendiente(d["tid"])
    if not ticket or ticket["referencia"] != d["ref"]:
        ctx.job.schedule_removal(); return

    ult = ultimas_resp.get(d["tid"], "")
    if ult and mia.evaluar_molestia(d["tid"], ult):
        db.cambiar_intervalo(d["tkid"], 2)
        ctx.job.schedule_removal()
        ctx.job_queue.run_repeating(recordar, interval=7200, first=7200,
            data=d, name=f"rec_{d['tid']}_{d['ref']}")
        return

    db.registrar_recordatorio(d["tkid"])
    resta = ticket["monto_total"] - ticket["monto_pagado"]
    recs = ticket["recordatorios_enviados"] + 1

    if recs <= 3:
        msg = f"👋 ¡Hola! Tu cuenta Disney+ sigue activa. Para mantenerla, falta pagar *${resta:.0f} MXN*. Escribe *pagar* 😊"
    elif recs <= 10:
        msg = f"⏳ Recordatorio: tu cuenta Disney+ (ref `{d['ref']}`) necesita pago de *${resta:.0f} MXN* para seguir activa."
    else:
        msg = f"⚠️ Tu cuenta Disney+ se desactivará pronto. Paga *${resta:.0f}* con ref `{d['ref']}`."

    try:
        await ctx.bot.send_message(d["tid"], msg, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Recordatorio: {e}")


async def revocar(ctx: ContextTypes.DEFAULT_TYPE):
    d = ctx.job.data
    ticket = db.obtener_ticket_pendiente(d["tid"])
    if not ticket or ticket["referencia"] != d["ref"]: return

    db.revocar_ticket(d["tkid"])
    for job in ctx.job_queue.get_jobs_by_name(f"rec_{d['tid']}_{d['ref']}"):
        job.schedule_removal()

    try:
        await ctx.bot.send_message(d["tid"],
            "❌ *Tu cuenta Disney+ fue desactivada* por falta de pago.\n"
            "Si quieres otra, escríbeme 😊", parse_mode="Markdown")
    except: pass

    await admin_msg(ctx,
        f"❌ *Revocada*\n`{d['tid']}` | `{d['ref']}` | "
        f"`{ticket['credencial_usuario']}` / `{ticket['credencial_contrasena']}`")


# ---- SOPORTE ----
async def manejar_soporte(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    compra = db.obtener_compra_reciente(user.id, DIAS_SOPORTE)

    if not compra:
        vieja = db.obtener_compra_reciente(user.id, 9999)
        if vieja:
            await update.message.reply_text(
                f"Tu soporte de {DIAS_SOPORTE} días expiró. ¿Quieres otra cuenta? 😊")
        else:
            await update.message.reply_text(
                "No encontré compra en tu cuenta. Si pagaste, escribe *ya pagué*.", parse_mode="Markdown")
        return

    # Marcar cuenta anterior como fallo
    db.marcar_cuenta_fallo(user.id, compra["credencial_usuario"])

    ya_dadas = db.obtener_credenciales_dadas_a_cliente(user.id)
    cred = elegir_cred(pool, ya_dadas)
    if not cred:
        await update.message.reply_text("Has recibido todas las cuentas disponibles. Contacta admin.")
        await admin_msg(ctx, f"🚨 {user.full_name} agotó reemplazos")
        return

    db.registrar_entrega(user.id, compra["ticket_id"], cred["usuario"], cred["contrasena"], reemplazo=True)

    await update.message.reply_text(
        "🔄 *Cuenta de reemplazo:*\n\n"
        f"👤 `{cred['usuario']}`\n🔑 `{cred['contrasena']}`\n\n"
        "Pruébala y dime si funciona 😊 Si necesitas ayuda para configurarla, pregúntame.",
        parse_mode="Markdown")

    await admin_msg(ctx, f"🔄 *Reemplazo*\n{user.full_name} → `{cred['usuario']}`")


async def error_handler(update, ctx):
    logger.error(f"Error: {ctx.error}")
    try: await admin_msg(ctx, f"Error: `{ctx.error}`")
    except: pass


# ---- CALLBACKS (encuestas y renovación) ----
async def callback_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    tid = query.from_user.id

    # Encuesta: enc_0_precio_alto
    if data.startswith("enc_"):
        parts = data.split("_", 2)
        idx = int(parts[1])
        resp = parts[2]
        p = ENCUESTA_PREGUNTAS[idx]["pregunta"]
        db.guardar_encuesta(tid, p, resp)

        if resp == "otra_cuenta":
            await query.edit_message_text("¿Qué cuenta/servicio buscabas? Escríbemelo 😊")
            return

        # Si no confía → enviar 20% extra de referencias
        if resp == "no_confia":
            await enviar_refs_20(ctx.bot, tid)

        sig = idx + 1
        if sig < len(ENCUESTA_PREGUNTAS):
            pregunta, teclado = crear_teclado_encuesta(sig)
            await query.edit_message_text(pregunta, reply_markup=teclado)
        else:
            await query.edit_message_text("¡Gracias por tus respuestas! Si cambias de opinión, escríbeme 😊")
            await admin_msg(ctx, f"📋 *Encuesta completada*\n`{tid}`")
        return

    # Renovación: renov_si_PLAXXXXX o renov_no_PLAXXXXX
    if data.startswith("renov_si_"):
        ref = data[9:]
        await query.edit_message_text("¡Genial! Te preparo una nueva cuenta. Escribe *pagar* cuando estés listo 😊", parse_mode="Markdown")
        return

    if data.startswith("renov_no_"):
        ref = data[9:]
        ticket = db.conn.execute("SELECT * FROM tickets WHERE referencia=?", (ref,)).fetchone()
        if ticket:
            db.expirar_ticket(ticket["id"])
            await admin_msg(ctx,
                f"❌ *No renueva*\n`{tid}` | `{ref}`\n"
                f"📦 `{ticket['credencial_usuario']}` / `{ticket['credencial_contrasena']}`\n"
                "Quémala, jefe.")
        await query.edit_message_text("Entendido. ¡Tu cuenta se desactivará pronto! Si cambias de opinión, escríbeme 😊")
        await iniciar_encuesta(ctx.bot, tid)
        return


# ---- MAIN ----
def main():
    if not TELEGRAM_TOKEN: raise ValueError("Falta TELEGRAM_TOKEN")
    logger.info(f"MIA iniciando ({len(pool)} cuentas)")

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("cliente", cmd_cliente))
    app.add_handler(CommandHandler("cuenta", cmd_cuenta_admin))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("ventas", cmd_ventas))
    app.add_handler(CommandHandler("recargar", cmd_recargar))
    app.add_handler(CommandHandler("responder", cmd_responder))
    app.add_handler(CommandHandler("confirmar", cmd_confirmar))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, procesar))
    app.add_error_handler(error_handler)

    logger.info("MIA escuchando...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
