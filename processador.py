import os
import time
import json
import base64
import telebot
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import mysql.connector
from groq import Groq
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# ==================== CONFIGURAÇÕES ====================
TOKEN_TELEGRAM = "SEU_TOKEN_AQUI"
GEMINI_API_KEY = "SEU_TOKEN_AQUI"
GROQ_API_KEY = "SEU_TOKEN_AQUI"  

DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'seu usuario',
    'password': 'sua senha',
    'database': 'consumo_agua',
    'port': 3306,
    'ssl_disabled': True,
    'time_zone': '-03:00'
}

PASTA_VIGIADA = os.path.expanduser('~/Leitor-Hidrometro/fotos_recebidas')
PASTA_PROC = os.path.join(PASTA_VIGIADA, 'processadas')
# =======================================================

bot = telebot.TeleBot(TOKEN_TELEGRAM)
client_gemini = genai.Client(api_key=GEMINI_API_KEY)
client_groq = Groq(api_key=GROQ_API_KEY)

class LeituraHidrometro(BaseModel):
    digitos_sequenciais: int = Field(description="Todos os números visíveis no visor do hidrômetro (pretos e vermelhos em sequência), ignorando pontos ou vírgulas.")
    confianca: float = Field(description="Grau de certeza da leitura de 0.0 a 1.0.")

# MOTOR A: GOOGLE GEMINI (NUVEM主)
def chamar_gemini_ia(caminho_foto):
    with open(caminho_foto, 'rb') as f:
        conteudo_foto = f.read()
    imagem_part = types.Part.from_bytes(data=conteudo_foto, mime_type="image/jpeg")
    prompt = "Analise a imagem deste hidrômetro residencial e extraia o número registrado no visor central (números pretos e vermelhos sequenciais juntos)."
    
    resposta = client_gemini.models.generate_content(
        model='gemini-3.5-flash', #pode mudar ao longo do tempo em 26/07/2026 está funcionando.
        contents=[imagem_part, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=LeituraHidrometro,
            temperature=0.1
        ),
    )
    dados = json.loads(resposta.text)
    return dados['digitos_sequenciais'], dados['confianca'], "Nuvem (Gemini 3.5)"

# MOTOR B: GROQ LLAMA 3.2 VISION (NUVEM SECUNDÁRIA ULTRA RÁPIDA E GRATUITA)
def chamar_groq_local(caminho_foto):
    print("⚡ Acionando o motor de contingência rápida Groq (Llama 3.2 Vision)...")
    
    with open(caminho_foto, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode('utf-8')
        
    prompt = (
        "Analise a imagem do hidrômetro residencial. Identifique o visor numérico central dos roletes. "
        "Retorne APENAS um objeto JSON válido contendo exatamente este formato: "
        '{"digitos_sequenciais": 76238, "confianca": 0.90}. '
        "Não adicione nenhuma introdução, explicação ou marcação markdown fora do JSON. "
        "Junte todos os números sequenciais pretos e vermelhos visíveis em um único valor inteiro."
    )
    
    resposta = client_groq.chat.completions.create(
        model="qwen/qwen3.6-27b",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                    },
                ],
            }
        ],
        temperature=0.1,
        response_format={"type": "json_object"} # Força o Groq a devolver estritamente um JSON limpo
    )
    
    dados = json.loads(resposta.choices[0].message.content)
    return int(dados['digitos_sequenciais']), float(dados['confianca']), "Nuvem (Groq Llama 3.2)"

class Handler(FileSystemEventHandler):
    def __init__(self, chat_id_atual=None):
        super().__init__()
        self.chat_id_atual = chat_id_atual

    def on_created(self, event):
        if event.is_directory or 'processadas' in event.src_path:
            return
            
        caminho_foto = event.src_path
        nome_arquivo = os.path.basename(caminho_foto)
        ext = nome_arquivo.lower().split('.')[-1]
        
        if ext not in ['jpg', 'jpeg', 'png']:
            return

        print(f"📸 Nova foto detectada na pasta: {nome_arquivo}")
        print("⏳ Aguardando 3 segundos para garantir a gravação completa do arquivo...")
        time.sleep(3) 

        motor_utilizado = ""
        try:
            try:
                print("🧠 Enviando imagem para o Google Gemini...")
                valor_lido, confianca, motor_utilizado = chamar_gemini_ia(caminho_foto)
            except Exception as gemini_error:
                print(f"⚠️ Falha na Nuvem Gemini: {gemini_error}. Ativando contingência Groq...")
                if self.chat_id_atual:
                    bot.send_message(self.chat_id_atual, "⚠️ *Cota do Gemini excedida.* Acionando motor de redundância rápida Groq...", parse_mode="Markdown")
                
                # Executa o Groq instantâneo
                valor_lido, confianca, motor_utilizado = chamar_groq_local(caminho_foto)
            
            valor_final = float(valor_lido) / 100 
            print(f"✅ Sucesso [{motor_utilizado}]! Número extraído: {valor_final} m³ (Confiança: {int(confianca*100)}%)")
            
            # Gravação no MariaDB
            conexao = mysql.connector.connect(**DB_CONFIG)
            cursor = conexao.cursor()
            agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            comando_sql = "INSERT INTO leituras (data_hora, valor_m3) VALUES (%s, %s)"
            cursor.execute(comando_sql, (agora, valor_final))
            conexao.commit()
            cursor.close()
            conexao.close()
            print("💾 DADOS GRAVADOS COM SUCESSO NO MARIADB!")
            
            if self.chat_id_atual:
                mensagem_sucesso = (
                    f"✅ *Leitura Processada com Sucesso!*\n\n"
                    f"🔢 *Valor Lido:* {valor_final} m³\n"
                    f"🎯 *Confiança:* {int(confianca * 100)}%\n"
                    f"🤖 *Motor utilizado:* `{motor_utilizado}`\n"
                    f"💾 Gravado no MariaDB e atualizado no Grafana!"
                )
                bot.send_message(self.chat_id_atual, mensagem_sucesso, parse_mode="Markdown")
            
        except Exception as e:
            erro_msg = f"💥 Falha crítica em ambos os motores de IA: {e}"
            print(erro_msg)
            if self.chat_id_atual:
                bot.send_message(self.chat_id_atual, f"❌ *Erro crítico de processamento:*\n`{str(e)}`", parse_mode="Markdown")
            
        finally:
            try:
                os.makedirs(PASTA_PROC, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                os.rename(caminho_foto, os.path.join(PASTA_PROC, f"leitura_{timestamp}.jpg"))
                print(f"📦 Foto organizada e salva no histórico.\n")
            except Exception as e:
                print(f"⚠️ Não foi possível mover para o histórico: {e}")

@bot.message_handler(content_types=['photo'])
def receber_foto_telegram(message):
    try:
        print("🤖 Foto recebida via Telegram Bot! Baixando...")
        global handler_monitor
        handler_monitor.chat_id_atual = message.chat.id
        
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        caminho_destino = os.path.join(PASTA_VIGIADA, f"telegram_{int(time.time())}.jpg")
        with open(caminho_destino, 'wb') as f:
            f.write(downloaded_file)
            
        bot.reply_to(message, "⏳ Foto recebida! Iniciando processamento do hidrômetro...")
    except Exception as e:
        bot.reply_to(message, f"❌ Erro ao receber foto: {e}")

if __name__ == "__main__":
    os.makedirs(PASTA_VIGIADA, exist_ok=True)
    handler_monitor = Handler()
    observer = Observer()
    observer.schedule(handler_monitor, path=PASTA_VIGIADA, recursive=False)
    observer.start()
    print(f"🚀 Sistema de Duplo Motor (Gemini + Groq) Iniciado em: {PASTA_VIGIADA}")
    bot.infinity_polling()

