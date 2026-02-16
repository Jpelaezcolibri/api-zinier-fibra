# API Recepción de Imagen → n8n - SOP

## Objetivo
Crear una API (FastAPI) que reciba una imagen desde un dispositivo móvil/web, la almacene temporalmente, y envíe la URL + metadatos a un webhook de n8n. La respuesta de n8n se devuelve al cliente que hizo la llamada original.

## Flujo
```
Cliente (foto) → API FastAPI → Almacena imagen → Webhook n8n → (n8n procesa con OpenAI Vision) → Respuesta → Cliente
```

## Entradas
- **Imagen**: archivo binario (multipart/form-data)

## Salidas
- Respuesta JSON de n8n al cliente (passthrough directo).

## Lógica / Pasos
120. El cliente envía un POST a `/api/analyze` con la imagen.
21. La API lee el archivo binario.
22. La API reenvía el archivo directamente al Webhook de n8n como `multipart/form-data`.
23. La API devuelve la respuesta JSON de n8n al cliente.

> **Nota**: No se guarda el archivo en disco ni se generan URLs locales. Es un pasamanos directo de datos binarios.

## Variables de Entorno (`.env`)
- `N8N_WEBHOOK_URL` → URL del webhook de n8n
- `API_HOST` → Host público de la API (para construir image_url)
- `API_PORT` → Puerto (default: 8000)

## Dependencias
- `fastapi`
- `uvicorn`
- `python-multipart` (para recibir archivos)
- `httpx` (para llamar al webhook de n8n)
- `python-dotenv`

## Restricciones / Casos Borde
## Restricciones / Casos Borde
- N8N debe estar configurado para recibir datos binarios en el Webhook.
- Limitar tamaño de imagen a 10MB para no saturar la memoria.
- Si n8n no responde en 60s, devolver timeout.

## Historial de Cambios
| Fecha | Cambio |
|-------|--------|
| 2026-02-16 | Creación inicial de la directiva. |
