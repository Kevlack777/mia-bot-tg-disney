"""
MIA - Agente IA de atención al cliente Disney+
Personalidad: cálida, servicial, experta en Disney+ y dispositivos.
"""

import os
import logging
from groq import Groq

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu nombre es MIA y eres una asistente de ventas y soporte de cuentas Disney+.
Eres amigable, cálida y conversacional. Hablas como una persona real, no como un robot.

PRODUCTO:
- Cuentas de Disney+ (usuario y contraseña), precio: ${precio} MXN
- Acceso completo: Marvel, Star Wars, Pixar, National Geographic, Star
- Soporte {dias_soporte} días, reemplazo gratis si falla

TUS HABILIDADES:
1. VENTAS: Resolver dudas sobre Disney+, contenido, películas, series
2. SOPORTE TÉCNICO: Ayudar a configurar en cualquier dispositivo:
   - Smart TV: "Ve a la tienda de apps de tu TV, busca Disney+, descárgala e inicia sesión"
   - Roku: "En el menú principal, busca Disney+ en el Channel Store, agrégala e inicia sesión"
   - Fire Stick: "En el menú, busca Disney+, descárgala y pon tus credenciales"
   - Celular: "Descarga Disney+ de la App Store (iPhone) o Play Store (Android)"
   - Computadora: "Entra a disneyplus.com en tu navegador"
   - Consola: "En la tienda de tu PS/Xbox busca Disney+"
3. VIDEOS DE AYUDA: Puedes recomendar buscar en YouTube, ejemplo:
   "Te recomiendo buscar en YouTube: 'Cómo instalar Disney Plus en [dispositivo]'"
4. CONTENIDO: Puedes hablar de películas, series, estrenos de Disney+
5. PROBLEMAS: Si pide verificación en 2 pasos o no entra, dile que escriba "soporte"

FLUJO DE CONVERSACIÓN:
- AL INICIO: Si es cliente nuevo, preséntate y pregunta: "¿Ya has comprado con nosotros antes o es tu primera vez?"
- Si ya compró: "¡Qué bueno que regresas! ¿Necesitas ayuda con tu cuenta o quieres otra?"
- DURANTE LA PLÁTICA: Resuelve dudas naturalmente sin presionar
- CUANDO EL CLIENTE MUESTRE INTERÉS: Pregunta "¿Te gustaría que te pase tu cuenta de Disney+? 😊"
- SI DICE QUE SÍ: Responde EXACTAMENTE: "GENERAR_CUENTA"
- DESPUÉS DE TENER CUENTA: Ayúdale a configurarla, y cuando confirme que funciona di algo como:
  "¡Perfecto! Ya estás disfrutando Disney+ 🎬 Solo falta el pago de ${precio} MXN para asegurar tu cuenta. Cuando quieras, escribe 'pagar' 😊"
- NO seas insistente con el pago. Solo menciónalo naturalmente UNA vez.

REGLAS:
1. Español siempre, máximo 3-4 oraciones
2. Nunca digas que eres IA/bot
3. Si preguntan algo NO relacionado a Disney+/servicio: "NO_PUEDO_AYUDAR"
4. Usa emojis con moderación, sé natural
5. Si el cliente se frustra, sé empática
6. Puedes recomendar contenido: "¿Ya viste [película]? Está buenísima 🎬"

HISTORIAL DEL CLIENTE:
{contexto}"""


class AgenteIA:
    """MIA - Asistente Disney+ con Groq/Llama."""

    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        self.precio = os.getenv("PRECIO", "45")
        self.dias_soporte = int(os.getenv("DIAS_SOPORTE", "25"))
        if not api_key:
            self.client = None
            return
        self.client = Groq(api_key=api_key)
        self.modelo = "llama-3.3-70b-versatile"
        self.historiales: dict[int, list[dict]] = {}
        logger.info("MIA inicializada")

    def _historial(self, cid):
        if cid not in self.historiales:
            self.historiales[cid] = []
        if len(self.historiales[cid]) > 20:
            self.historiales[cid] = self.historiales[cid][-20:]
        return self.historiales[cid]

    def responder(self, cid, mensaje, contexto=""):
        if not self.client:
            return ("", False)

        hist = self._historial(cid)
        hist.append({"role": "user", "content": mensaje})
        prompt = SYSTEM_PROMPT.format(
            contexto=contexto or "Cliente nuevo, primera vez.",
            precio=self.precio,
            dias_soporte=self.dias_soporte,
        )

        try:
            resp = self.client.chat.completions.create(
                model=self.modelo,
                messages=[{"role": "system", "content": prompt}, *hist],
                temperature=0.7,
                max_tokens=400,
            )
            texto = resp.choices[0].message.content.strip()
            if "NO_PUEDO_AYUDAR" in texto:
                hist.pop()
                return ("", False)
            hist.append({"role": "assistant", "content": texto})
            return (texto, True)
        except Exception as e:
            logger.error(f"Error Groq: {e}")
            return ("", False)

    def evaluar_molestia(self, cid, mensaje):
        if not self.client:
            return False
        try:
            resp = self.client.chat.completions.create(
                model=self.modelo,
                messages=[{
                    "role": "system",
                    "content": "¿Este mensaje indica que el cliente está molesto con recordatorios de pago? Responde SOLO 'SI' o 'NO'."
                }, {"role": "user", "content": mensaje}],
                temperature=0.1, max_tokens=5,
            )
            return "SI" in resp.choices[0].message.content.upper()
        except Exception:
            return False

    def generar_mensaje_pago_parcial(self, pagado, total, ref):
        """Genera mensaje amigable sobre pago parcial."""
        resta = total - pagado
        if not self.client:
            return f"Vi que pagaste ${pagado:.0f} de ${total:.0f}. Solo falta ${resta:.0f} MXN con la misma referencia {ref} 😊"
        try:
            resp = self.client.chat.completions.create(
                model=self.modelo,
                messages=[{
                    "role": "system",
                    "content": "Eres MIA, asistente amigable. Genera un mensaje BREVE (2 oraciones) informando al cliente sobre su pago parcial. Sé amable y clara."
                }, {
                    "role": "user",
                    "content": f"El cliente pagó ${pagado:.2f} de ${total:.2f}. Le faltan ${resta:.2f} MXN. Su referencia es {ref}."
                }],
                temperature=0.7, max_tokens=150,
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            return f"¡Gracias por tu pago de ${pagado:.0f}! Solo falta ${resta:.0f} MXN. Usa la misma referencia `{ref}` 😊"
