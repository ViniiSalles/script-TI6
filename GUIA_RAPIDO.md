# 🚀 Guia Rápido - Sistema Modular

## ⚡ Comandos Essenciais

### 1️⃣ Coleta de Repositórios

```bash
# Básico: 50 Rapid + 50 Slow
python 1_collect_repositories.py --rapid 50 --slow 50

# Grande escala: 100 Rapid + 100 Slow
python 1_collect_repositories.py --rapid 100 --slow 100 --max-search 2000

# Apenas Rapid
python 1_collect_repositories.py --rapid 100 --slow 0

# Apenas Slow
python 1_collect_repositories.py --rapid 0 --slow 100
```

---

### 2️⃣ Análise SonarQube

```bash
# Sequencial (1 por vez)
python 2_analyze_sonarqube.py

# Paralelo (4 workers) - RECOMENDADO
python 2_analyze_sonarqube.py --workers 4

# Apenas Rapid
python 2_analyze_sonarqube.py --type rapid --workers 4

# Apenas Slow
python 2_analyze_sonarqube.py --type slow --workers 4

# Pular já analisados (retomar)
python 2_analyze_sonarqube.py --skip-analyzed --workers 4

# Limitar análises (teste)
python 2_analyze_sonarqube.py --limit 10 --workers 2
```

---

### 3️⃣ Consultar Dataset (Python)

```python
from dataset_manager import DatasetManager

dm = DatasetManager()

# Ver estatísticas
dm.print_statistics()

# Listar todos
repos = dm.get_repositories()
print(f"Total: {len(repos)}")

# Filtrar por tipo
rapid = dm.get_repositories(release_type='rapid')
slow = dm.get_repositories(release_type='slow')

# Exportar CSV
dm.export_to_csv('meus_dados.csv')

# Verificar pendentes
dataset = dm.load_dataset()
pending = [r for r in dataset['repositories']
           if not r.get('sonarqube_analyzed', False)]
print(f"Faltam analisar: {len(pending)}")
```

---

### 4️⃣ Testar Sistema

```bash
# Testar filtros
python test_filters.py

# Testar dataset manager
python dataset_manager.py

# Exemplo completo
python example_usage.py
```

---

## 📊 Workflow Típico

### Dia 1: Coleta

```bash
python 1_collect_repositories.py --rapid 100 --slow 100 --max-search 2000
```

**Resultado:** `repositories_dataset.json` com ~200 repositórios

### Dia 2-5: Análise em Lotes

```bash
# Processar todos (recomendado - progresso organizado)
python 2_analyze_sonarqube.py --workers 4 --skip-analyzed

# Ou em lotes menores
python 2_analyze_sonarqube.py --workers 4 --limit 50 --skip-analyzed
python 2_analyze_sonarqube.py --workers 4 --limit 50 --skip-analyzed
# ... até completar todos
```

### Exportar Resultados

```python
from dataset_manager import DatasetManager
DatasetManager().export_to_csv('dataset_final.csv')
```

---

## 🔍 Verificações Úteis

### Ver status do dataset

```python
from dataset_manager import DatasetManager
dm = DatasetManager()
stats = dm.get_statistics()
print(f"Total: {stats['total']}")
print(f"Rapid: {stats['rapid']}, Slow: {stats['slow']}")
```

### Contar não analisados

```python
from dataset_manager import DatasetManager
dm = DatasetManager()
dataset = dm.load_dataset()
not_analyzed = [r for r in dataset['repositories']
                if not r.get('sonarqube_analyzed', False)]
print(f"Pendentes: {len(not_analyzed)}")
```

### Listar repositórios pendentes

```python
from dataset_manager import DatasetManager
dm = DatasetManager()
dataset = dm.load_dataset()
pending = [r for r in dataset['repositories']
           if not r.get('sonarqube_analyzed', False)]

for i, repo in enumerate(pending, 1):
    print(f"{i}. {repo['full_name']} ({repo['release_type']})")
```

---

## ⚙️ Configuração Inicial

### 1. Arquivo .env

```bash
# GitHub (obrigatório para coleta)
GITHUB_TOKEN=seu_token_aqui

# SonarQube (obrigatório para análise)
SONAR_HOST=http://localhost:9000
SONAR_TOKEN=seu_token_aqui

# PostgreSQL (opcional)
DB_HOST=localhost
DB_NAME=sonar
DB_USER=sonar
DB_PASSWORD=sonar
DB_PORT=5432
```

### 2. Instalar dependências

```bash
pip install -r requirements.txt
```

### 3. Iniciar Docker (para análise)

```bash
docker-compose up -d
```

---

## 🛠️ Troubleshooting

### Erro: "Rate limit"

```bash
# Aguardar ou reduzir --max-search
python 1_collect_repositories.py --rapid 50 --slow 50 --max-search 500
```

### Erro: "Docker not found"

```bash
# Instalar Docker Desktop e iniciar
# https://www.docker.com/products/docker-desktop
```

### Análise travando

```bash
# Reduzir workers
python 2_analyze_sonarqube.py --workers 1

# Ou limitar quantidade
python 2_analyze_sonarqube.py --workers 2 --limit 10
```

### Re-analisar tudo

```python
# Marcar todos como não analisados
from dataset_manager import DatasetManager
dm = DatasetManager()
dataset = dm.load_dataset()
for repo in dataset['repositories']:
    repo['sonarqube_analyzed'] = False
dm.save_dataset(dataset)
```

---

## 📁 Arquivos Gerados

```
repositories_dataset.json  → Dataset principal (JSON)
repositories_dataset.csv   → Exportação CSV
test_dataset.json         → Dataset de teste
example_dataset.json      → Dataset do exemplo
```

---

## 🎯 Dicas de Performance

### Coleta Rápida

- Use `--max-search` menor para coletas rápidas
- Aumenta taxa de aprovação: busque repos mais populares

### Análise Rápida

- Use `--workers 4` em máquinas com 4+ cores
- Monitore uso de RAM (cada worker = repositório clonado)
- Em SSDs, análise é mais rápida

### Economia de API Calls

- Dataset evita re-buscar mesmos repos
- Use `--skip-analyzed` para retomar
- GitHub API: 5000 calls/hora (com token)

---

## 📞 Ajuda

```bash
# Ajuda do Script 1
python 1_collect_repositories.py --help

# Ajuda do Script 2
python 2_analyze_sonarqube.py --help
```

---

**Última atualização:** 19/10/2025  
**Versão:** 2.0
