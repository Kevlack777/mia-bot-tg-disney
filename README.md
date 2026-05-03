# 🤖 Bot de Telegram — Venta de Platica

Bot automático de Telegram que gestiona ventas:
- Responde preguntas frecuentes por palabras clave
- Verifica pagos en Gmail automáticamente
- Entrega credenciales (usuario:contraseña) desde CSV
- Notifica al administrador de cada venta

---

## 📁 Estructura del Proyecto

```
bot tg/
├── main.py              # Lógica principal del bot
├── gmail_checker.py     # Módulo para verificar pagos en Gmail
├── requirements.txt     # Dependencias Python
├── credentials.csv      # Base de datos de credenciales
├── .env.example         # Plantilla de variables de entorno
├── .env                 # Variables de entorno (NO subir a Git)
├── .gitignore           # Archivos ignorados por Git
├── Procfile             # Configuración para Railway
├── gmail_setup.md       # Instrucciones para configurar Gmail
└── README.md            # Este archivo
```

---

## 🚀 Setup Rápido

### 1. Clonar y configurar entorno

```bash
# Clonar repositorio
git clone <tu-repo-url>
cd bot-platica

# Crear entorno virtual (recomendado)
python -m venv venv
source venv/bin/activate        # Linux/Mac
.\venv\Scripts\activate         # Windows

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

```bash
# Copiar plantilla
cp .env.example .env

# Editar con tus valores
notepad .env    # Windows
nano .env       # Linux
```

### 3. Obtener Token de Telegram

1. Abre Telegram y busca **@BotFather**
2. Envía `/newbot`
3. Sigue las instrucciones (nombre y username del bot)
4. Copia el **token** y pégalo en `.env` como `TELEGRAM_TOKEN`

### 4. Obtener tu ID de Telegram

1. Busca **@userinfobot** en Telegram
2. Envía `/start`
3. Copia tu **ID** y pégalo en `.env` como `TU_TELEGRAM_ID`

### 5. Configurar Gmail

Sigue las instrucciones en [gmail_setup.md](gmail_setup.md).

### 6. Preparar credenciales CSV

Edita `credentials.csv` con tus credenciales reales:

```csv
usuario,contraseña
usuario_001,MiPassword123!
usuario_002,OtraPassword456!
```

### 7. Ejecutar el bot

```bash
python main.py
```

---

## 💬 Comandos del Bot

### Para clientes (mensajes de texto):

| Mensaje | Respuesta |
|---------|-----------|
| hola, inicio | Bienvenida con menú |
| comprar, quiero platica | Info de compra |
| precio, cuánto cuesta | Precio |
| incluye, qué es | Descripción |
| dudas, ayuda, faq | Preguntas frecuentes |
| ya pagué | Verifica Gmail y entrega credenciales |

### Para admin (comandos):

| Comando | Función |
|---------|---------|
| `/start` | Mensaje de bienvenida |
| `/status` | Ver credenciales disponibles/entregadas |
| `/recargar` | Recargar CSV después de actualizar |

---

## 🚂 Deploy en Railway

### 1. Subir a GitHub

```bash
git init
git add .
git commit -m "Bot de platica listo"
git remote add origin <tu-repo-url>
git push -u origin main
```

### 2. Configurar Railway

1. Ve a [railway.app](https://railway.app) e inicia sesión con GitHub
2. Haz clic en **"New Project"** → **"Deploy from GitHub repo"**
3. Selecciona tu repositorio
4. Ve a **Settings** → **Variables** y agrega:
   - `TELEGRAM_TOKEN`
   - `TU_TELEGRAM_ID`
   - `GMAIL_USER`
   - `GMAIL_PASSWORD`
5. Railway detectará el `Procfile` y desplegará automáticamente

> ⚠️ **IMPORTANTE:** Sube `credentials.csv` al repo o configúralo dentro de Railway.
> El `.gitignore` lo excluye por seguridad — si quieres incluirlo, quita la línea.

### 3. Verificar

- El bot debería estar corriendo 24/7
- Envíale `/start` desde Telegram para verificar

---

## 🔧 Personalización

### Cambiar respuestas
Edita el diccionario `RESPUESTAS` en `main.py`.

### Cambiar precio
Busca `$99 MXN` en las respuestas y cámbialo.

### Cambiar palabras clave de pago en Gmail
Edita `PALABRAS_PAGO` en `gmail_checker.py`.

### Cambiar ventana de tiempo para pagos
Edita `VENTANA_MINUTOS` en `gmail_checker.py` (default: 30 min).

---

## ❓ FAQ Técnico

**¿El bot usa IA?**
No. Usa coincidencia de palabras clave simples.

**¿Qué pasa si se acaban las credenciales?**
El bot muestra error al cliente y notifica al admin.

**¿Cómo recargo credenciales?**
1. Actualiza `credentials.csv` con nuevas filas
2. Envía `/recargar` al bot como admin

**¿Es seguro?**
Las credenciales sensibles van en `.env` (no en el código).
El `.gitignore` previene que se suban a GitHub.

---

## 📄 Licencia

Uso privado. Proyecto personal.
