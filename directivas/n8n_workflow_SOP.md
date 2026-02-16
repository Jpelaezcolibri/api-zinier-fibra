# Configuración n8n - Workflow Análisis de Imagen con OpenAI Vision

## Objetivo
Configurar un workflow en n8n que reciba la URL de una imagen desde nuestra API FastAPI, la envíe a OpenAI Vision para análisis, y devuelva el resultado como JSON array.

## Flujo del Workflow
```
```
Webhook (recibe binario) → OpenAI Vision (analiza binario) → Code (parsea) → Respond to Webhook
```

> **Nota**: El workflow original incluía un nodo HTTP Request para descargar la imagen. Se eliminó porque causaba errores (403/404) al descargar desde servidores externos. OpenAI Vision acepta URLs directamente en el prompt.

---

## Paso a Paso

### Paso 1: Crear Nuevo Workflow
1. En n8n, clic en **"Add workflow"** (esquina superior derecha).
2. Nómbralo: `Análisis Imagen Fibra Óptica`.

---

### Paso 2: Nodo Webhook (Trigger)
Este nodo recibe la llamada de nuestra API FastAPI.

1. Clic en **"+"** → buscar **"Webhook"**.
2. Configurar:
   - **HTTP Method**: `POST`
   - **Path**: `analyze-image`
   - **Authentication**: `None`
   - **Respond**: **"Using 'Respond to Webhook' Node"**
   - **Binary Data**: Activar/Configurar para que reciba el archivo en el campo `data`.
3. Clic en **"Listen for Test Event"** para obtener la URL de pruebas, o activa el workflow para obtener la URL de producción.
4. **Copiar la URL del webhook** (Producción) y pegarla en tu `.env`:
   ```
   N8N_WEBHOOK_URL=https://tu-n8n.com/webhook/analyze-image
   ```

> **Nota**: La URL de Test y la de Producción son diferentes. Usa la de Producción cuando actives el workflow.

---

### ~~Paso 3: Nodo HTTP Request~~ (ELIMINADO)
> **Eliminado.** No se necesita descargar la imagen. OpenAI Vision acepta URLs directamente.
> Causaba errores 403 (Wikipedia) y 404 (Unsplash) por restricciones de User-Agent.

---

### Paso 3: Nodo OpenAI - Análisis con Vision
1. Agregar nodo **"OpenAI"** después del Webhook.
2. Configurar:
   - **Credential**: `OpenAI API`
   - **Resource**: `Image`
   - **Operation**: `Analyze`
   - **Input Data Field Name**: `data` (o el nombre del campo binario que viene del webhook)
   - **Prompt**:
     ```
     Analiza esta imagen de un panel de fibra óptica. Devuelve un JSON con los puertos, estado (occupied/available) y observaciones.
     ```
   - **JSON Output**: Habilitar si el modelo lo permite, o especificar en el prompt que devuelva solo JSON.

---

### Paso 4: Parsear la Respuesta
1. Agregar nodo **"Code"** (o **"Function"**) después de OpenAI.
2. Código JavaScript:
```javascript
// Extraer el texto de respuesta de OpenAI
const responseText = $input.first().json.message.content;

// Parsear el JSON array
let ports;
try {
  ports = JSON.parse(responseText);
} catch (e) {
  // Si OpenAI envolvió el JSON en markdown code blocks
  const match = responseText.match(/\[[\s\S]*\]/);
  ports = match ? JSON.parse(match[0]) : [];
}

return [{
  json: {
    technician_id: $('Webhook').first().json.body.technician_id,
    site_id: $('Webhook').first().json.body.site_id,
    total_ports: ports.length,
    occupied: ports.filter(p => p.status === 'occupied').length,
    available: ports.filter(p => p.status === 'available').length,
    damaged: ports.filter(p => p.status === 'damaged').length,
    ports: ports,
    analyzed_at: new Date().toISOString()
  }
}];
```
3. Renombrar nodo a: `Formatear Resultado`.

---

### Paso 5: Nodo Respond to Webhook
1. Agregar nodo **"Respond to Webhook"** al final.
2. Configurar:
   - **Respond With**: `All Incoming Items`
   
Esto devolverá el JSON completo a nuestra API FastAPI, que a su vez lo devuelve al cliente.

---

### Paso 6: Activar Workflow
1. Clic en **"Active"** (toggle en la parte superior derecha).
2. Copiar la **URL de Producción** del nodo Webhook.
3. Pegarla en `.env`:
   ```
   N8N_WEBHOOK_URL=https://tu-n8n.com/webhook/analyze-image
   ```

---

## Ejemplo de Respuesta Final
```json
{
  "ports": [
    {"port_number": 1, "status": "occupied", "observations": "azul"},
    ...
  ]
}
```

## Diagrama Visual del Workflow
```
┌──────────┐    ┌──────────────┐    ┌───────────────┐    ┌──────────────────┐
│ Webhook  │───▶│   OpenAI     │───▶│ Code (Parser) │───▶│ Respond Webhook  │
│ (POST)   │    │ Vision (URL) │    │               │    │ (JSON response)  │
└──────────┘    └──────────────┘    └───────────────┘    └──────────────────┘
```

## Credenciales Necesarias en n8n
- **OpenAI API Key**: Configurar en n8n → Settings → Credentials → Agregar "OpenAI API".

## Restricciones / Casos Borde
- La `image_url` debe ser accesible públicamente (usar ngrok en desarrollo local).
- OpenAI Vision tiene un costo por imagen (~$0.01-0.03 por análisis dependiendo del modelo).
- Si la imagen es muy grande o de baja calidad, la detección puede ser imprecisa.
- El nodo Code parsea la respuesta por si OpenAI la envuelve en markdown code blocks.
- **No usar nodo HTTP Request para descargar imágenes** → causa errores 403/404 por restricciones de User-Agent en servidores externos. OpenAI acepta URLs directamente.

## Historial de Cambios
| Fecha | Cambio |
|-------|--------|
| 2026-02-16 | Creación inicial de la directiva. |
| 2026-02-16 | Eliminado nodo HTTP Request (403/404). OpenAI recibe URL directamente. Corregido Resource→Conversation, Operation→Create. |
