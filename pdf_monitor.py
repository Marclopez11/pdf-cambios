import requests
import hashlib
import time
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, time as dt_time
from typing import Optional
from bs4 import BeautifulSoup
import re
import pytz

# Configuración del logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('pdf_monitor.log'),
        logging.StreamHandler()
    ]
)

class EmailNotifier:
    def __init__(self):
        # Configura aquí tus credenciales de Gmail
        self.sender_email = "marclopezmarco469@gmail.com"
        self.sender_password = "ikwf icqm ypqy danw"  # Contraseña de aplicación de Gmail
        self.receiver_emails = [
            "marclopezmarco469@gmail.com",
            "nuriamarco23@gmail.com",
            "shidalgohurtado@gmail.com",
            "marialopezmarco@gmail.com"
        ]

    def send_email(self, subject: str, body: str):
        try:
            message = MIMEMultipart()
            message["From"] = self.sender_email
            message["To"] = ", ".join(self.receiver_emails)
            message["Subject"] = subject

            message.attach(MIMEText(body, "plain"))

            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(self.sender_email, self.sender_password)
                server.send_message(message)
                
            logging.info(f"[EMAIL] Correo enviado exitosamente a {', '.join(self.receiver_emails)}")
        except Exception as e:
            logging.error(f"[EMAIL] Error al enviar el correo: {str(e)}")

class Monitor:
    def __init__(self):
        self.pdf_hashes = {}  # Almacena los hashes de los PDFs
        self.check_interval = 300  # 5 minutos
        self.email_notifier = EmailNotifier()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Configuración de URLs por región
        self.regions = {
            'Tarragona': {
                'pdf': 'https://educacio.gencat.cat/web/.content/home/departament/serveis-territorials/tarragona/personal-docent/nomenaments-telematics/dificil-cobertura/primaria/TAR-PRI-dificil-cobertura-oferta-vacants.pdf'
            },
            'Lleida': {
                'pdf': 'https://educacio.gencat.cat/web/.content/home/departament/serveis-territorials/lleida/personal-docent/nomenaments-telematics/dificil-cobertura/LLE-Sollicitud-dificil-cobertura.pdf'
            },
            'Penedès': {
                'pdf': 'https://educacio.gencat.cat/web/.content/home/departament/serveis-territorials/penedes/personal-docent/nomenaments-telematics/dificil-cobertura/primaria/PEN-PRI-dificil-cobertura-oferta-vacants.pdf'
            },
            'Baix Llobregat': {
                'pdf': 'https://educacio.gencat.cat/web/.content/home/departament/serveis-territorials/baix-llobregat/personal-docent/nomenaments-telematics/dificil-cobertura/primaria/PENDENTS_BLL-PRI-dificil-cobertura-oferta-vacants.pdf'
            },
            'Terres de l\'Ebre': {
                'pdf': 'https://educacio.gencat.cat/web/.content/home/departament/serveis-territorials/terres-ebre/personal-docent/nomenaments-telematics/dificil-cobertura/primaria/TEB-PRI-dificil-cobertura-oferta-vacants.pdf'
            }
        }

    def _check_pdf_hash(self, url: str) -> bool:
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            if not response.content:
                logging.warning(f"[PDF] El contenido del PDF está vacío: {url}")
                return False
            
            current_hash = hashlib.md5(response.content).hexdigest()
            
            # Si es la primera vez que vemos este PDF
            if url not in self.pdf_hashes:
                self.pdf_hashes[url] = current_hash
                logging.info(f"[PDF] Hash inicial guardado para: {url}")
                return False
            
            # Comparar con el hash anterior
            if current_hash != self.pdf_hashes[url]:
                self.pdf_hashes[url] = current_hash
                logging.info(f"[PDF] Cambio detectado en: {url}")
                return True
                
            return False
            
        except Exception as e:
            logging.error(f"[PDF] Error al verificar el PDF {url}: {str(e)}")
            return False

    def _extract_date_from_web(self, url: str) -> Optional[str]:
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Cambiamos 'text' por 'string' para eliminar el warning de deprecación
            date_element = soup.find('h4', string=lambda text: text and 'Data:' in text)
            
            if not date_element:
                # Búsqueda alternativa si no se encuentra con el primer método
                date_elements = soup.find_all('h4')
                for element in date_elements:
                    if 'Data:' in element.get_text():
                        date_element = element
                        break
            
            if date_element:
                match = re.search(r'Data:?\s*(\d{2}/\d{2}/\d{4})', date_element.get_text())
                if match:
                    found_date = match.group(1)
                    logging.info(f"[WEB] Fecha encontrada en {url}: {found_date}")
                    return found_date
            
            # Log del HTML para debug si no se encuentra la fecha
            logging.warning(f"[WEB] No se encontró la fecha en: {url}")
            logging.debug(f"[WEB] Contenido HTML: {response.text[:500]}...")  # Primeros 500 caracteres
            return None
            
        except Exception as e:
            logging.error(f"[WEB] Error al extraer fecha de {url}: {str(e)}")
            return None

    def check_web_date(self, url: str, region: str):
        try:
            date = self._extract_date_from_web(url)
            
            # Si encontramos una fecha
            if date:
                # Si la región no estaba en web_changes o no tenía fecha anterior
                if region not in self.web_changes:
                    self.web_changes[region] = {
                        'date': date,
                        'changed_at': datetime.now(self.spanish_timezone)
                    }
                    logging.info(f"[WEB] Primera fecha detectada para {region}: {date}")
                # Si había una fecha anterior y es diferente
                elif self.web_changes[region].get('date') and date != self.web_changes[region]['date']:
                    self.web_changes[region] = {
                        'date': date,
                        'changed_at': datetime.now(self.spanish_timezone)
                    }
                    logging.info(f"[WEB] Nueva fecha detectada para {region}: {date}")
                # Si no había fecha anterior (era None)
                elif self.web_changes[region].get('date') is None:
                    self.web_changes[region] = {
                        'date': date,
                        'changed_at': datetime.now(self.spanish_timezone)
                    }
                    logging.info(f"[WEB] Fecha recuperada para {region}: {date}")
            else:
                # Si no encontramos fecha, solo actualizamos el estado sin generar alerta
                if region not in self.web_changes:
                    self.web_changes[region] = {
                        'date': None,
                        'changed_at': datetime.now(self.spanish_timezone)
                    }
                elif self.web_changes[region].get('date'):
                    # Si había fecha y ahora no, asumimos actualización
                    self.web_changes[region]['date'] = None
                    logging.info(f"[WEB] {region} en actualización (sin fecha disponible)")
            
        except Exception as e:
            logging.error(f"[WEB] Error al verificar web de {region}: {str(e)}")

    def send_daily_summary(self):
        now = datetime.now(self.spanish_timezone)
        target_time = dt_time(11, 10)  # 11:10 hora española
        
        # Verificar si es hora de enviar el resumen
        if now.time() >= target_time and (
            self.last_summary_date is None or 
            self.last_summary_date.date() < now.date()
        ):
            changes = []
            for region, data in self.web_changes.items():
                if data['changed_at'].date() == now.date():
                    changes.append(f"{region}: Nueva fecha {data['date']}")
            
            if changes:
                message = "Resumen de cambios en las webs:\n" + "\n".join(changes)
                self.email_notifier.send_email("Resumen diario de cambios", message)
                logging.info("[RESUMEN] Enviado resumen diario de cambios")
            else:
                logging.info("[RESUMEN] No hay cambios para reportar hoy")
            
            self.last_summary_date = now
            self.web_changes = {}  # Limpiar cambios después del resumen

    def notify_startup(self):
        message = f"""
        Monitor de PDFs y Webs iniciado
        
        Regiones monitorizadas:
        {', '.join(self.regions.keys())}
        
        Timestamp: {datetime.now(self.spanish_timezone)}
        """
        self.email_notifier.send_email(
            "Monitor de PDFs y Webs iniciado",
            message
        )
        logging.info("[INICIO] Notificación de inicio enviada")

    def monitor(self):
        logging.info("[INICIO] Iniciando monitoreo de PDFs")
        
        while True:
            try:
                # Verificar PDFs
                for region, urls in self.regions.items():
                    if 'pdf' in urls and self._check_pdf_hash(urls['pdf']):
                        message = f"El PDF de {region} ha sido modificado\nURL: {urls['pdf']}"
                        self.email_notifier.send_email(
                            f"Cambio detectado en PDF de {region}",
                            message
                        )
                
                logging.info("[CICLO] Esperando próximo ciclo de comprobación...")
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                logging.info("[FIN] Monitoreo detenido por el usuario")
                break
            except Exception as e:
                logging.error(f"[ERROR] Error inesperado: {str(e)}")
                time.sleep(60)

if __name__ == "__main__":
    monitor = Monitor()
    monitor.monitor() 