# 🚰 Pipeline de Monitoramento de Hidrômetro com Duplo Motor de IA (Gemini + Groq)

Este projeto automatiza a leitura de consumo de água residencial transformando fotos de hidrômetros analógicos enviadas pelo Telegram em registros analíticos dentro de um banco de dados MariaDB, com dashboards em tempo real no Grafana. 

O sistema conta com arquitetura de **Redundância Inteligente (Fallback)**: se o motor de IA principal (Google Gemini) falhar ou estourar a cota, o motor secundário (Groq Cloud) assume o processamento visual instantaneamente.

## 🛠️ Arquitetura do Ecossistema

1. **Telegram Bot**: Interface de entrada para o usuário submeter a foto.
2. **Python Watchdog**: Monitora a pasta local em tempo real aguardando novos arquivos.
3. **Structured Outputs (AI)**: Google Gemini / Groq interpretam o visor tridimensional e retornam estritamente um formato JSON estruturado.
4. **Docker Containers**: Docker isola o banco de dados MariaDB e o servidor de Dashboards do Grafana.

---

## 📂 Organograma do Projeto

```text
Leitor-Hidrometro/
├── docker-compose.yml   # Orquestração dos containers (MariaDB e Grafana)
├── processador.py       # Cérebro em Python (Bot Telegram + Watchdog + Chamadas de IA)
└── fotos_recebidas/     # Pasta local espelhada de uploads
    └── processadas/     # Subpasta de histórico de imagens analisadas
```

---

## 🚀 Guia de Instalação e Configuração

### 1. Instalação do Docker e Dependências no Linux
Atualize as listas do sistema e instale o Docker Engine junto com o Python Pip:


# Atualizar repositórios e instalar o Pip
sudo apt update && sudo apt install -y python3-pip ca-certificates curl gnupg

# Instalar as bibliotecas Python necessárias para o ecossistema
pip install pyTelegramBotAPI google-genai groq mysql-connector-python watchdog pydantic --break-system-packages


### 2. Inicialização dos Containers (Docker Compose)
Crie o arquivo `docker-compose.yml` e suba o banco de dados e o Grafana em segundo plano:

docker compose up -d

### 3. Estruturação do Banco de Dados
Crie a tabela de persistência diretamente no contêiner do MariaDB executando o comando abaixo no terminal do host:

docker exec -i hidrometro_db mariadb -urodrigo -pquimica consumo_agua -e "CREATE TABLE IF NOT EXISTS leituras (id INT AUTO_INCREMENT PRIMARY KEY, data_hora DATETIME DEFAULT CURRENT_TIMESTAMP, valor_m3 DECIMAL(10,2) NOT NULL);"

### 4. Executando o Processador
Após inserir suas chaves de API (`TOKEN_TELEGRAM`, `GEMINI_API_KEY` e `GROQ_API_KEY`) no topo do script `processador.py`, inicie o monitor:

python3 processador.py


## 📊 Configuração no Grafana (Porta 3000)

1. Acesse `http://IP_DA_VM:3000` (Credenciais padrão: `admin`/`admin`).
2. Adicione um **Data Source MySQL** apontando para o IP do seu host, porta `3306`, base `consumo_agua`, usuário `seu_usuario` e senha `sua_senha`.
3. Crie um painel do tipo **Time Series** (Gráfico de Linha) utilizando a seguinte Query SQL:

```sql
SELECT
  data_hora AS "time",
  valor_m3 AS "Consumo Total (m³)"
FROM leituras
WHERE \$__timeFilter(data_hora)
ORDER BY data_hora ASC;
```
*(Dica: Configure o estilo de linha para **Step Before** ou **Step After** para melhor visualização de medidores acumulativos).*

