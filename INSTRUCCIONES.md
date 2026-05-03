# 🤖 MIA Bot — Asistente de Ventas Disney+

Bot de Telegram con IA (Groq/Llama) para venta automatizada de cuentas Disney+ con soporte técnico, pagos parciales, encuestas y seguimiento inteligente.

---

## 📁 Estructura de Archivos

| Archivo | Función |
|---------|---------|
| `main.py` | Lógica principal del bot, handlers, flujo de venta |
| `ai_agent.py` | MIA — Agente IA con Groq (Llama 3.3 70B) |
| `database.py` | SQLite: clientes, tickets, pagos, credenciales, encuestas |
| `gmail_checker.py` | Verificación de pagos por Gmail (IMAP) |
| `seguimiento.py` | Encuestas de salida, follow-ups, renovaciones |
| `credentials.csv` | Pool de cuentas Disney+ (usuario, contraseña) |
| `referencias/` | Fotos de clientes satisfechos (pruebas sociales) |
| `.env` | Variables de entorno (tokens, claves, datos de pago) |

---

## 🔄 Flujo Completo del Bot

```
CLIENTE NUEVO
     │
     ▼
  /start → MIA saluda y pregunta "¿Ya compraste antes o es tu primera vez?"
     │
     ▼
  RESUELVE DUDAS (IA)
  • Qué incluye Disney+
  • Cómo conectar a TV/Roku/Fire Stick
  • Qué películas hay
  • Precio ($45 MXN)
     │
     ▼
  ¿QUIERE CUENTA? ←── MIA pregunta naturalmente
     │                     │
    SÍ                    NO
     │                     │
     ▼                     ▼
  SE CREA TICKET      Follow-up automático:
  + Entrega cuenta     • 15 min → "¿Sigues interesado?"
  + Referencia única   • 30 min → + envía 20% refs extras
     │                 • 1 hora → último intento
     ▼                 • 1 día → último mensaje
  AYUDA A CONFIGURAR   + Encuesta de salida (3 preguntas)
  (TV, Roku, app...)
     │
     ▼
  ¿TODO FUNCIONA? → "pagar" → Muestra datos de pago
     │
     ▼
  RECORDATORIOS CADA HORA (si no paga)
  • Si se molesta → cada 2 horas
  • 24h sin pago → REVOCA cuenta + avisa admin
     │
     ▼
  "ya pagué" → Verifica en Gmail
     │
     ├── Pago completo → ✅ Cierra ticket (25 días soporte)
     ├── Pago parcial → "Faltan $X, misma referencia"
     └── No encontrado → "Espera 1-2 min"
     │
     ▼
  SOPORTE 25 DÍAS
  • Cuenta no funciona → Reemplazo automático
  • Verificación 2 pasos → Reemplazo
  • Hasta agotar pool (sin repetir al mismo cliente)
     │
     ▼
  DÍA 23 → "¿Quieres renovar?" (botones Sí/No)
     │
     ├── SÍ → Nuevo ticket
     └── NO → Expira cuenta + envía a admin para quemar + encuesta
```

---

## 🛠️ Comandos

### Comandos del Cliente
El cliente **no ve** ningún comando especial. Todo es conversacional:

| El cliente escribe... | MIA hace... |
|----------------------|-------------|
| `hola` / `/start` | Saludo + pregunta si es nuevo |
| Preguntas sobre Disney+ | Responde con IA (Groq) |
| `dale` / `sí quiero` / `pásame` | Entrega credenciales |
| `pagar` / `cómo pago` | Muestra datos de pago |
| `ya pagué` | Verifica pago en Gmail |
| `soporte` / `no funciona` | Reemplazo de cuenta |
| `referencias` / `es confiable` | Envía fotos de clientes |
| `no gracias` / `lo pienso` | Inicia follow-up + encuesta |

### Comandos Admin (secretos)

| Comando | Función |
|---------|---------|
| `/admin kevlack` | Panel principal con stats completos |
| `/status` | Resumen rápido |
| `/ventas` | Últimas 10 ventas |
| `/cliente ID` | Historial completo de un cliente |
| `/confirmar ID` | Confirmar pago manualmente |
| `/responder ID msg` | Enviar mensaje a un cliente |
| `/recargar` | Recargar pool de CSV |
| `/cuenta` | Obtener cuenta Disney+ para ti |

### Comandos de Prueba (admin)

| Comando | Simula... |
|---------|-----------|
| `/admin 25dias` | Renovación (25 días pasaron) |
| `/admin 15minutos` | Follow-up de indeciso |
| `/admin 5minutos` | Encuesta de salida |
| `/admin malo` | No-pago (revoca cuenta) |

---

## 💳 Sistema de Pagos

### Pagos Parciales
- El cliente puede pagar en partes (ej: $25 + $20)
- Misma referencia siempre
- MIA le dice cuánto falta
- Se cierra cuando la suma ≥ precio

### Verificación
- Busca en Gmail correos con la referencia
- Extrae el monto real del correo (regex)
- Soporta múltiples correos por referencia

---

## 📸 Sistema de Referencias

| Porción | Cuándo se envía |
|---------|-----------------|
| **80%** (19 fotos) | Cliente pregunta por "referencias", "es seguro", "es confiable" |
| **20%** (5 fotos) | Follow-up 30 min, o encuesta dice "no confío", o pide más |

---

## 🔄 Rotación de Credenciales

- Las cuentas se toman del `credentials.csv`
- **Nunca se repite** la misma cuenta al mismo cliente
- Clientes diferentes **sí** pueden recibir la misma cuenta
- Si pide reemplazo → se da una diferente de las que ya tuvo
- Se registra estado: `entregada`, `funciono`, `fallo`, `revocada`, `expirada`

---

## 🚨 Alertas Automáticas al Admin

| Evento | Mensaje |
|--------|---------|
| Ventas > $300 | 💰 "¡Hey jefe! Ya llevamos $300..." |
| Ventas > $400 | 🚨 "URGENTE YA SACA DINERO JEFE" |
| Cuenta revocada (24h sin pago) | ❌ Envía usuario/contraseña para quemar |
| Cliente no renueva | ❌ Envía cuenta para quemar |
| Reemplazos > 50% del pool | ⚠️ "Considera actualizar la BD" |
| MIA no puede ayudar | 🚨 Escalación con mensaje del cliente |

---

## ⚙️ Configuración (.env)

```env
TELEGRAM_TOKEN=tu_token_de_botfather
TU_TELEGRAM_ID=tu_id_numerico
GMAIL_USER=tu@gmail.com
GMAIL_PASSWORD=contraseña_de_app_gmail
GROQ_API_KEY=gsk_xxxxx
PRECIO=45
CLABE=167420000026819154
CUENTA_OXXO=4741742943681455
TITULAR=Tu Nombre
BANCO=Banregio
```

---

## 📦 Instalación

```bash
pip install -r requirements.txt
```

### Dependencias:
- `python-telegram-bot[job-queue]` — Bot de Telegram
- `groq` — IA (Llama 3.3)
- `python-dotenv` — Variables de entorno

---

## 🚀 Ejecución

```bash
python main.py
```

---

## 🗄️ Base de Datos (SQLite)

Archivo: `bot_mia.db` (se crea automáticamente)

| Tabla | Contenido |
|-------|-----------|
| `clientes` | telegram_id, nombre, username |
| `tickets` | referencia, estado, credenciales, montos, fechas |
| `credenciales_entregadas` | historial de qué cuenta se dio a quién |
| `pagos` | pagos individuales por ticket |
| `encuestas` | respuestas de encuestas de salida |

### Estados de Ticket:
- `entregado` — Cuenta dada, pendiente de pago
- `pagado` — Pago confirmado, 25 días activo
- `revocado` — 24h sin pago, cuenta retirada
- `expirado` — 25 días cumplidos, no renovó

---

## 📋 Encuesta de Salida

Se activa cuando el cliente dice "no" o no renueva. 3 preguntas con botones:

1. **¿Por qué no compraste?** → Precio alto / No confía / Mejor precio / Otra cuenta / Después / Otro
2. **¿Qué streaming te interesa?** → Disney+ / Netflix / HBO / Spotify / Prime / Otro
3. **¿Qué precio te parece justo?** → $25-30 / $30-40 / $40-50 / $50+
