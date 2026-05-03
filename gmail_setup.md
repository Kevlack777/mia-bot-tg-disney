# 📧 Configuración de Gmail para el Bot

## Método: Contraseña de Aplicación (IMAP)

Este bot usa **IMAP** con una **Contraseña de Aplicación** de Google.
Es el método más simple y no requiere OAuth2 ni credenciales JSON.

---

## Paso 1: Activar Verificación en 2 Pasos

1. Ve a [https://myaccount.google.com/security](https://myaccount.google.com/security)
2. En la sección **"Cómo inicias sesión en Google"**, haz clic en **Verificación en 2 pasos**
3. Sigue los pasos para activarla (necesitarás tu teléfono)

> ⚠️ **IMPORTANTE:** Sin verificación en 2 pasos, no podrás crear contraseñas de aplicación.

---

## Paso 2: Crear Contraseña de Aplicación

1. Ve a [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. En **"Nombre de la app"**, escribe: `Bot Platica`
3. Haz clic en **Crear**
4. Google te mostrará una contraseña de 16 caracteres (algo como `abcd efgh ijkl mnop`)
5. **Copia esa contraseña** — la necesitarás para el `.env`

> ⚠️ **Esta contraseña solo se muestra una vez.** Si la pierdes, tendrás que crear una nueva.

---

## Paso 3: Habilitar IMAP en Gmail

1. Abre Gmail en el navegador
2. Ve a **Configuración** (⚙️) → **Ver todos los ajustes**
3. Ve a la pestaña **"Reenvío y correo POP/IMAP"**
4. En la sección IMAP, selecciona **"Habilitar IMAP"**
5. Haz clic en **Guardar cambios**

---

## Paso 4: Configurar el .env

Copia `.env.example` como `.env` y rellena:

```env
GMAIL_USER=tu_email@gmail.com
GMAIL_PASSWORD=abcdefghijklmnop
```

> Nota: La contraseña de aplicación va **sin espacios** (los 16 caracteres juntos).

---

## Cómo Funciona

1. Cuando un cliente escribe **"ya pagué"**, el bot se conecta a tu Gmail por IMAP
2. Busca correos recientes (últimos 30 minutos) con palabras clave de pago
3. Si encuentra un correo de pago → entrega credenciales automáticamente
4. El correo se marca como "procesado" para no entregar doble

### Palabras clave que busca el bot:
- pago, payment, confirmación, recibido
- transferencia, deposito, comprobante
- notificación de pago, abono

---

## Solución de Problemas

| Problema | Solución |
|----------|----------|
| Error de autenticación | Verifica que la contraseña de app sea correcta y sin espacios |
| No detecta pagos | Revisa que IMAP esté habilitado en Gmail |
| "Less secure apps" error | Usa contraseña de aplicación, no tu contraseña normal |
| Timeout de conexión | Verifica tu conexión a internet y que el firewall no bloquee IMAP |

---

## Seguridad

- ✅ **NUNCA** uses tu contraseña real de Gmail — usa siempre contraseña de aplicación
- ✅ **NUNCA** subas el archivo `.env` a GitHub
- ✅ La contraseña de app solo da acceso a correo, no a toda tu cuenta
- ✅ Puedes revocar la contraseña en cualquier momento desde la configuración de Google
