"""
Seguimiento: encuestas de salida, follow-up de indecisos, renovación 25 días.
"""
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# Intervalos de follow-up para indecisos (segundos)
FOLLOWUP_INTERVALS = [900, 1800, 3600, 86400]  # 15min, 30min, 1h, 1día

# Preguntas de la encuesta de salida
ENCUESTA_PREGUNTAS = [
    {
        "pregunta": "¿Por qué decidiste no comprar?",
        "opciones": [
            ("💰 El precio es muy alto", "precio_alto"),
            ("🤖 No confío en comprar por bot/IA", "no_confia"),
            ("🔍 Encontré mejores precios", "mejor_precio"),
            ("📺 No está la cuenta que busco", "otra_cuenta"),
            ("⏰ Ahora no, quizá después", "despues"),
            ("🤔 Otro motivo", "otro"),
        ],
    },
    {
        "pregunta": "¿Qué servicio de streaming te interesa más?",
        "opciones": [
            ("🏰 Disney+", "disney"),
            ("🎬 Netflix", "netflix"),
            ("📺 HBO Max", "hbo"),
            ("🎵 Spotify", "spotify"),
            ("⚡ Amazon Prime", "prime"),
            ("🎮 Otro", "otro_servicio"),
        ],
    },
    {
        "pregunta": "¿Qué precio te parecería justo?",
        "opciones": [
            ("💵 $25-30 MXN", "25_30"),
            ("💵 $30-40 MXN", "30_40"),
            ("💵 $40-50 MXN", "40_50"),
            ("💵 Más de $50 MXN está bien", "50_mas"),
        ],
    },
]


def crear_teclado_encuesta(pregunta_idx: int, pregunta_extra: str = None):
    """Crea teclado inline para una pregunta de encuesta."""
    if pregunta_idx >= len(ENCUESTA_PREGUNTAS):
        return None, None
    p = ENCUESTA_PREGUNTAS[pregunta_idx]
    botones = [
        [InlineKeyboardButton(texto, callback_data=f"enc_{pregunta_idx}_{valor}")]
        for texto, valor in p["opciones"]
    ]
    return p["pregunta"], InlineKeyboardMarkup(botones)


async def iniciar_encuesta(bot, tid):
    """Envía la primera pregunta de la encuesta."""
    pregunta, teclado = crear_teclado_encuesta(0)
    if pregunta and teclado:
        await bot.send_message(
            tid,
            f"📋 *Antes de irte, ¿nos ayudas con 3 preguntas rápidas?*\n\n{pregunta}",
            reply_markup=teclado, parse_mode="Markdown",
        )


async def programar_followup(ctx: ContextTypes.DEFAULT_TYPE, tid: int, paso: int = 0):
    """Programa el siguiente follow-up para un indeciso."""
    if paso >= len(FOLLOWUP_INTERVALS):
        return
    ctx.job_queue.run_once(
        followup_indeciso,
        when=FOLLOWUP_INTERVALS[paso],
        data={"tid": tid, "paso": paso},
        name=f"followup_{tid}",
    )


async def followup_indeciso(ctx: ContextTypes.DEFAULT_TYPE):
    """Envía mensaje de follow-up a un indeciso."""
    d = ctx.job.data
    tid, paso = d["tid"], d["paso"]

    mensajes = [
        "😊 ¡Hola! ¿Sigues interesado en tu cuenta de Disney+? Estoy aquí para ayudarte.",
        "👋 Solo quería saber si cambiaste de opinión sobre Disney+. ¡La oferta sigue en pie!",
        "🎬 ¡Última llamada! ¿Te animas a probar Disney+? Cualquier duda estoy aquí.",
        "🌟 ¡Hola de nuevo! Han pasado unas horas. Si cambias de opinión sobre Disney+, aquí estaré 😊",
    ]
    msg = mensajes[min(paso, len(mensajes) - 1)]

    try:
        from database import Database
        _db = Database()
        if _db.obtener_ticket_pendiente(tid):
            return  # Si ya tiene ticket pendiente o pagado, cancelamos

        await ctx.bot.send_message(tid, msg)
        # En el paso 1 (30 min) enviar el 20% extra de referencias
        if paso == 1:
            from main import enviar_refs_20
            await enviar_refs_20(ctx.bot, tid)
            
        # En el paso 3 (1 día), enviar la encuesta
        if paso == 3:
            await iniciar_encuesta(ctx.bot, tid)
    except Exception as e:
        logger.error(f"Followup error: {e}")

    # Programar el siguiente follow-up
    sig = paso + 1
    if sig < len(FOLLOWUP_INTERVALS):
        ctx.job_queue.run_once(
            followup_indeciso,
            when=FOLLOWUP_INTERVALS[sig],
            data={"tid": tid, "paso": sig},
            name=f"followup_{tid}",
        )


async def programar_renovacion(ctx, tid, ref, dias=25):
    """Programa aviso de renovación N días después."""
    # Aviso 2 días antes de expirar
    segundos = (dias - 2) * 86400
    ctx.job_queue.run_once(
        aviso_renovacion,
        when=segundos,
        data={"tid": tid, "ref": ref},
        name=f"renov_{tid}_{ref}",
    )


async def aviso_renovacion(ctx: ContextTypes.DEFAULT_TYPE):
    """Avisa al cliente que su cuenta está por expirar."""
    d = ctx.job.data
    try:
        teclado = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Sí, quiero renovar", callback_data=f"renov_si_{d['ref']}")],
            [InlineKeyboardButton("❌ No, gracias", callback_data=f"renov_no_{d['ref']}")],
        ])
        await ctx.bot.send_message(
            d["tid"],
            "⏰ *¡Tu cuenta Disney+ está por vencer!*\n\n"
            "En 2 días se desactivará tu acceso.\n"
            "¿Quieres renovar por otros 25 días? 😊",
            reply_markup=teclado, parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Renovación error: {e}")


def cancelar_followups(ctx, tid):
    """Cancela todos los follow-ups pendientes de un cliente."""
    for job in ctx.job_queue.get_jobs_by_name(f"followup_{tid}"):
        job.schedule_removal()
