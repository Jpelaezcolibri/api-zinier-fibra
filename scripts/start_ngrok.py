from pyngrok import ngrok
import time
import sys

# Configurar puerto
PORT = 8001

def start_tunnel():
    try:
        # Abrir túnel HTTP
        public_url = ngrok.connect(PORT).public_url
        print(f"Ngrok Tunnel Started: {public_url}")
        
        # Guardar en archivo para que el agente lo lea
        with open("ngrok.log", "w") as f:
            f.write(public_url)
            
        # Mantener vivo
        while True:
            time.sleep(1)
            
    except Exception as e:
        print(f"Error starting ngrok: {e}")
        with open("ngrok.log", "w") as f:
            f.write(f"Error: {e}")

if __name__ == "__main__":
    start_tunnel()
