# 🚀 Guia Rápido - Análise de CSV com SonarQube

## Como Analisar Repositórios do CSV

### Pré-requisitos

1. **Docker Desktop** rodando
2. **SonarQube** configurado em `http://localhost:9000`
3. **Tokens configurados** no arquivo `.env`:
   ```bash
   SONAR_TOKEN=seu_token_aqui
   SONAR_HOST=http://localhost:9000
   ```

### Passo a Passo

#### 1️⃣ Inicie os Serviços Docker

```bash
# Windows
docker-compose up -d

# Linux/macOS
docker-compose up -d
```

Aguarde ~1-2 minutos e acesse http://localhost:9000 para verificar se o SonarQube está ativo.

### 2️⃣ Analise os Repositórios do CSV

```bash
# Windows PowerShell
python analyze_csv_repos.py --csv slow_release_repos_20251115_053707.csv --workers 4

# Linux/macOS
python3 analyze_csv_repos.py --csv slow_release_repos_20251115_053707.csv --workers 4

# Analisar apenas os primeiros 10 (para teste)
python analyze_csv_repos.py --csv slow_release_repos_20251115_053707.csv --workers 2 --limit 10

# Retomar análise (pula repositórios já analisados)
python analyze_csv_repos.py --csv slow_release_repos_20251115_053707.csv --workers 4 --skip-analyzed
```

#### 3️⃣ Resultados

O script irá criar um arquivo CSV com os resultados:

```
slow_release_repos_20251115_053707_analyzed.csv
```

Este arquivo conterá todas as métricas do SonarQube incluindo:

- `bugs`: Número de bugs detectados
- `vulnerabilities`: Vulnerabilidades de segurança
- `code_smells`: Problemas de manutenibilidade
- `coverage`: Cobertura de testes (%)
- `ncloc`: Linhas de código (sem comentários)
- `complexity`: Complexidade ciclomática

---

## Opções do Comando

```bash
python analyze_csv_repos.py \
  --csv ARQUIVO.csv \          # Arquivo CSV de entrada (obrigatório)
  --workers 4 \                # Número de processos paralelos
  --limit 50 \                 # Limitar análises (opcional)
  --skip-analyzed \            # Pular repositórios já analisados
  --output saida.csv           # Arquivo de saída customizado (opcional)
```

---

## Formato do CSV de Entrada

O CSV deve conter as seguintes colunas:

```csv
owner,name,stars,forks,language,release_count,contributors,median_release_interval,release_type,reason
massgravel,Microsoft-Activation-Scripts,156094,15068,Batchfile,27,700,54,SLOW,54 dias
Genymobile,scrcpy,131088,12276,C,49,15600,62.0,SLOW,62.0 dias
```

**Colunas obrigatórias:**

- `owner`: Proprietário do repositório no GitHub
- `name`: Nome do repositório
- `release_type`: Tipo de release (rapid/slow)

**Colunas opcionais (mas recomendadas):**

- `stars`, `forks`, `language`, `release_count`, `contributors`, `median_release_interval`

---

## Exemplos Práticos

### Teste Rápido (2 repositórios)

```bash
python analyze_csv_repos.py --csv slow_release_repos_20251115_053707.csv --limit 2
```

### Análise Completa em Background

```bash
# Windows PowerShell
Start-Process python -ArgumentList "analyze_csv_repos.py --csv slow_release_repos_20251115_053707.csv --workers 4" -NoNewWindow

# Linux/macOS
nohup python analyze_csv_repos.py --csv slow_release_repos_20251115_053707.csv --workers 4 &
```

### Verificar Progresso

```python
# Em outro terminal Python
from dataset_manager import DatasetManager
dm = DatasetManager('slow_release_repos_20251115_053707.csv')
dataset = dm.load_dataset()
analyzed = sum(1 for r in dataset['repositories'] if r.get('sonarqube_analyzed', False))
print(f"Analisados: {analyzed}/{len(dataset['repositories'])}")
```

---

## Tempo Estimado de Execução

| Repositórios | Workers | Tempo Estimado |
| ------------ | ------- | -------------- |
| 10           | 1       | 30-50 min      |
| 10           | 2       | 15-25 min      |
| 50           | 4       | 60-90 min      |
| 100          | 4       | 2-3 horas      |
| 775 (total)  | 4       | 12-18 horas    |

⚠️ **Limite de Tamanho**: Repositórios maiores que **2GB** são automaticamente pulados para evitar problemas de memória e timeout.

**Fatores que afetam o tempo:**

- Tamanho do repositório (clonagem) - repositórios >2GB são pulados
- Linguagem do código (análise)
- Velocidade da internet (clonagem)
- Disponibilidade de RAM (paralelização)

---

## Troubleshooting

### ❌ Erro: "SONAR_TOKEN não configurado"

```bash
# Linux/macOS
cat .env
echo "SONAR_TOKEN=seu_token_aqui" >> .env

# Windows PowerShell
type .env
Add-Content .env "SONAR_TOKEN=seu_token_aqui"
```

### ❌ Erro: "Falha ao clonar ou >2GB"

- Repositório pode ter mais de **2GB** (limite de segurança automático)
- Repositório pode ser privado ou ter sido deletado
- Verifique sua conexão com a internet
- O script automaticamente pula e continua com o próximo

### ❌ Erro: "Docker não encontrado"

```bash
# Verifique se Docker está rodando (Windows/Linux/macOS)
docker ps

# Windows/macOS: Inicie o Docker Desktop
# Linux (systemd):
sudo systemctl start docker

# Linux (verificar status):
sudo systemctl status docker
```

### ❌ Erro: "Falha ao clonar"

- Repositório pode ser privado ou ter sido deletado
- Verifique sua conexão com a internet
- O script automaticamente pula e continua com o próximo

### ⚠️ Muitas Falhas de Análise

- Reduza o número de workers: `--workers 2`
- Aumente o timeout no código (linha ~190 de `analyze_csv_repos.py`)
- Verifique logs do SonarQube: `docker-compose logs sonarqube`

---

## Estrutura dos Arquivos Gerados

```
slow_release_repos_20251115_053707.csv          # Original (entrada)
slow_release_repos_20251115_053707_analyzed.csv # Com análises (saída)
```

### Diferença entre os arquivos:

**Original:** Apenas metadados do GitHub  
**Analyzed:** Metadados + métricas SonarQube (bugs, vulnerabilities, coverage, etc.)

---

## Dicas de Performance

### 🚀 Máximo Desempenho

```bash
# Use número de workers = número de CPU cores
python analyze_csv_repos.py --csv repos.csv --workers 8
```

### 💾 Economia de Recursos

```bash
# Use menos workers se tiver pouca RAM
python analyze_csv_repos.py --csv repos.csv --workers 2
```

### 🔄 Análise Incremental

```bash
# Dia 1: Analise 50
python analyze_csv_repos.py --csv repos.csv --workers 4 --limit 50

# Dia 2: Analise mais 50 (pula os já analisados)
python analyze_csv_repos.py --csv repos.csv --workers 4 --limit 100 --skip-analyzed
```

---

## Comandos Úteis

### Ver Estatísticas do Dataset

```bash
python -c "from dataset_manager import DatasetManager; DatasetManager('slow_release_repos_20251115_053707.csv').print_statistics()"
```

### Verificar SonarQube

```bash
# Abrir no navegador
start http://localhost:9000  # Windows
open http://localhost:9000   # macOS
xdg-open http://localhost:9000  # Linux
```

### Parar Docker

```bash
docker-compose down
```

---

## Próximos Passos

Após a análise completa:

1. **Abrir CSV analisado** no Excel/LibreOffice/Python
2. **Análise estatística** com R ou Python (pandas)
3. **Visualizações** com matplotlib/seaborn
4. **Comparações** entre repositórios Rapid vs Slow

---

**Data de Criação:** 16/11/2025  
**Versão:** 1.0 - Suporte a CSV
