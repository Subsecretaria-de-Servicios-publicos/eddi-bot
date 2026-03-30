1) Verificá qué archivo vas a subir

En tu máquina local, ubicá el archivo.

Ejemplo:

ls -lh ~/Descargas/

Supongamos que el archivo se llama:

rag_eddi.tar.gz
2) Subir el archivo al server

Desde tu máquina local, usá scp.

Opción normal
scp ~/Descargas/rag_eddi.tar.gz USUARIO@IP_O_DOMINIO:/home/USUARIO/
Si usás clave privada
scp -i /ruta/a/tu_clave.pem ~/Descargas/rag_eddi.tar.gz USUARIO@IP_O_DOMINIO:/home/USUARIO/
3) Entrar al server
ssh USUARIO@IP_O_DOMINIO

o con clave:

ssh -i /ruta/a/tu_clave.pem USUARIO@IP_O_DOMINIO
4) Crear carpeta destino del proyecto

Por ejemplo:

mkdir -p /opt/rag_eddi

Si no tenés permisos en /opt, usá home:

mkdir -p ~/rag_eddi
5) Mover el archivo a la carpeta destino

Si lo subiste al home:

mv ~/rag_eddi.tar.gz /opt/rag_eddi/

o si trabajás en home:

mv ~/rag_eddi.tar.gz ~/rag_eddi/
6) Entrar a la carpeta del proyecto
cd /opt/rag_eddi

o:

cd ~/rag_eddi
7) Descomprimir el archivo
Si es .tar.gz
tar -xzf rag_eddi.tar.gz
Si es .tar
tar -xf rag_eddi.tar

Después verificá:

ls -lah

Si al descomprimir quedó una carpeta tipo RAG EDDI/, entrá ahí:

cd "RAG EDDI"
8) Ver estructura
ls -lah

Deberías ver algo como:

app/
alembic/
requirements.txt
alembic.ini
9) Crear entorno virtual
python3 -m venv .venv

Activarlo:

source .venv/bin/activate

Verificar:

which python
python --version
10) Instalar dependencias
pip install --upgrade pip
pip install -r requirements.txt

Si además usás OCR visual y no está en requirements.txt, asegurate de instalar:

pip install pymupdf pillow pytesseract
11) Instalar dependencias del sistema

Si el proyecto usa PostgreSQL, OCR y compilación típica, en Ubuntu/Debian conviene:

sudo apt update
sudo apt install -y \
  python3-venv \
  python3-dev \
  build-essential \
  libpq-dev \
  postgresql-client \
  tesseract-ocr \
  tesseract-ocr-spa

Si usás psycopg2, pgvector, OCR, esto ayuda bastante.

12) Crear o subir archivo .env

Si el proyecto usa variables de entorno, creá .env.

Ejemplo:

nano .env

Y completás con tus valores reales, por ejemplo:

DATABASE_URL=postgresql+psycopg2://usuario:password@127.0.0.1:5432/eddi
OPENAI_API_KEY=...
ADMIN_TOKEN=...
SECRET_KEY=...
CHAT_MODEL=gpt-4o-mini
RAG_TOP_K=6
RAG_MIN_SCORE=0.15

Guardás:

Ctrl + O
Enter
Ctrl + X
13) Probar conexión a la DB

Si querés validar rápido:

python -c "from app.db import engine; print(engine)"

o directamente seguir con Alembic.

14) Ejecutar migraciones
alembic upgrade head

Verificá si termina sin error.

Si querés confirmar:

alembic current
alembic heads
15) Probar arranque manual

Antes de dejarlo en producción, levantalo manualmente:

uvicorn app.main:app --host 0.0.0.0 --port 8000

Probá desde navegador:

http://IP_O_DOMINIO:8000
http://IP_O_DOMINIO:8000/rag/admin/docs

Si funciona, cortás con:

Ctrl + C
16) Dejarlo corriendo en producción con systemd

Creá un servicio:

sudo nano /etc/systemd/system/rag_eddi.service

Pegá esto, ajustando rutas y usuario:

[Unit]
Description=RAG EDDI FastAPI
After=network.target

[Service]
User=USUARIO
WorkingDirectory=/opt/rag_eddi/RAG EDDI
Environment="PATH=/opt/rag_eddi/RAG EDDI/.venv/bin"
ExecStart=/opt/rag_eddi/RAG EDDI/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target

Guardá.

17) Habilitar y arrancar el servicio
sudo systemctl daemon-reload
sudo systemctl enable rag_eddi
sudo systemctl start rag_eddi

Ver estado:

sudo systemctl status rag_eddi

Ver logs:

sudo journalctl -u rag_eddi -n 100 --no-pager
18) Abrir puerto en firewall si hace falta

Si usás UFW:

sudo ufw allow 8000
sudo ufw status
19) Recomendado: poner Nginx adelante

Si querés dejarlo prolijo con dominio y reverse proxy:

sudo apt install -y nginx

Crear config:

sudo nano /etc/nginx/sites-available/rag_eddi

Ejemplo:

server {
    listen 80;
    server_name TU_DOMINIO_O_IP;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

Activar:

sudo ln -s /etc/nginx/sites-available/rag_eddi /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
20) Si querés HTTPS

Con Certbot:

sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d TU_DOMINIO
21) Comandos completos resumidos
En local
scp ~/Descargas/rag_eddi.tar.gz USUARIO@IP_O_DOMINIO:/home/USUARIO/
En server
ssh USUARIO@IP_O_DOMINIO
mkdir -p /opt/rag_eddi
mv ~/rag_eddi.tar.gz /opt/rag_eddi/
cd /opt/rag_eddi
tar -xzf rag_eddi.tar.gz
cd "RAG EDDI"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install pymupdf pillow pytesseract
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential libpq-dev postgresql-client tesseract-ocr tesseract-ocr-spa
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
22) Qué revisar antes de darlo por terminado
alembic upgrade head sin errores
/rag/admin/docs carga
/rag/admin/candidates carga
chat responde
OCR visual genera imágenes
document_images se llena
static sirve bien /static/...
23) Si querés actualizar una versión nueva después

Subís nuevo .tar.gz, hacés backup y reemplazás:

cd /opt
mv rag_eddi rag_eddi_backup_$(date +%F_%H%M)
mkdir -p rag_eddi

y repetís descompresión e instalación.