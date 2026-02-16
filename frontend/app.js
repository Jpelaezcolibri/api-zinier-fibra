const fileInput = document.getElementById('file-input');
const dropZone = document.getElementById('drop-zone');
const previewSection = document.getElementById('preview-section');
const uploadSection = document.getElementById('upload-section');
const imagePreview = document.getElementById('image-preview');
const removeBtn = document.getElementById('remove-img');
const analyzeBtn = document.getElementById('analyze-btn');
const resultsSection = document.getElementById('results-section');
const errorMessage = document.getElementById('error-message');

// CONFIGURACIÓN API
// URL de Producción (Render) - Funciona siempre, 24/7
let API_URL = "https://api-zinier-fibra.onrender.com/api/analyze";

// Manejo de Archivos
dropZone.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', (e) => handleFile(e.target.files[0]));

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    handleFile(e.dataTransfer.files[0]);
});

function handleFile(file) {
    if (file && file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = (e) => {
            imagePreview.src = e.target.result;
            uploadSection.classList.add('hidden');
            previewSection.classList.remove('hidden');
            resultsSection.classList.add('hidden');
        };
        reader.readAsDataURL(file);

        // Guardar archivo para enviar
        analyzeBtn.onclick = () => analyzeImage(file);
    } else {
        showError("Por favor sube un archivo de imagen válido.");
    }
}

removeBtn.addEventListener('click', () => {
    fileInput.value = '';
    previewSection.classList.add('hidden');
    uploadSection.classList.remove('hidden');
    resultsSection.classList.add('hidden');
});

async function analyzeImage(file) {
    setLoading(true);

    // Si la URL es localhost, verificar si el usuario quiere probar con mock o intentar conectar
    console.log("Enviando a:", API_URL);

    const formData = new FormData();
    formData.append('image', file);

    try {
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: {
                'getting-started': 'true', // Header específico para saltar aviso de localtunnel
                'Bypass-Tunnel-Reminder': 'true'
            },
            body: formData
        });

        if (!response.ok) throw new Error(`Error API: ${response.status}`);

        const result = await response.json();
        renderResults(result);

    } catch (error) {
        console.error(error);
        showError("Error al conectar con la API. Asegúrate de que backend esté corriendo.");
    } finally {
        setLoading(false);
    }
}

function renderResults(data) {
    // n8n devuelve { "mensaje": "...", "total_puertos": N ... }
    // A veces puede venir anidado, ajustamos defensa
    const info = data.json || data;

    // Validar si es error
    if (info.error) {
        showError("Error del Analizador: " + info.error);
        return;
    }

    document.getElementById('res-total').textContent = info.total_puertos || '-';
    document.getElementById('res-occupied').textContent = (info.ocupados_lista ? info.ocupados_lista.length : 0);
    document.getElementById('res-available').textContent = (info.disponibles_lista ? info.disponibles_lista.length : 0);
    document.getElementById('res-message').textContent = info.mensaje || "Análisis completado.";

    resultsSection.classList.remove('hidden');
}

function setLoading(isLoading) {
    const btnText = analyzeBtn.querySelector('.btn-text');
    const loader = analyzeBtn.querySelector('.loader');

    analyzeBtn.disabled = isLoading;
    if (isLoading) {
        btnText.classList.add('hidden');
        loader.classList.remove('hidden');
    } else {
        btnText.classList.remove('hidden');
        loader.classList.add('hidden');
    }
}

function showError(msg) {
    errorMessage.textContent = msg;
    errorMessage.classList.remove('hidden');
    setTimeout(() => errorMessage.classList.add('hidden'), 5000);
}
