# 📊 Análise SonarQube de Repositórios CSV - README

## ✨ Novidade: Suporte a CSV

Este sistema agora suporta análise de repositórios a partir de arquivos CSV pré-coletados, além do workflow original baseado em JSON.

## 🎯 Quando Usar Cada Abordagem

### Workflow JSON (Original)

✅ Quando você quer coletar **novos** repositórios do GitHub  
✅ Quando precisa de **controle total** sobre os critérios de filtragem  
✅ Quando quer **expandir** o dataset incrementalmente

```bash
# 1. Coleta
python 1_collect_repositories.py --rapid 100 --slow 100

# 2. Análise
python 2_analyze_sonarqube.py --workers 4
```

### Workflow CSV (Novo)

✅ Quando você já tem uma **lista de repositórios** em CSV  
✅ Quando os repositórios foram **coletados externamente**  
✅ Quando quer **analisar rapidamente** sem re-buscar no GitHub

```bash
# Análise direta do CSV
python analyze_csv_repos.py --csv slow_release_repos.csv --workers 4
```

---

## 🚀 Início Rápido (CSV)

### 1. Prepare o Ambiente

```bash
# Instale dependências
pip install -r requirements.txt

# Configure tokens no .env
SONAR_TOKEN=seu_token_aqui
SONAR_HOST=http://localhost:9000

# Inicie Docker
docker-compose up -d
```

### 2. Execute a Análise

```bash
# Teste com 5 repositórios
python analyze_csv_repos.py --csv slow_release_repos_20251115_053707.csv --limit 5

# Análise completa (paralela)
python analyze_csv_repos.py --csv slow_release_repos_20251115_053707.csv --workers 4
```

### 3. Verifique Resultados

O script cria automaticamente um arquivo `*_analyzed.csv` com todas as métricas:

```
slow_release_repos_20251115_053707_analyzed.csv
```

---

## 📋 Formato do CSV de Entrada

### Colunas Necessárias

| Coluna                    | Tipo   | Obrigatório | Descrição                |
| ------------------------- | ------ | ----------- | ------------------------ |
| `owner`                   | string | ✅ Sim      | Proprietário do repo     |
| `name`                    | string | ✅ Sim      | Nome do repositório      |
| `stars`                   | int    | ⚠️ Rec.     | Número de stars          |
| `forks`                   | int    | ⚠️ Rec.     | Número de forks          |
| `language`                | string | ⚠️ Rec.     | Linguagem principal      |
| `release_count`           | int    | ⚠️ Rec.     | Número de releases       |
| `contributors`            | int    | ⚠️ Rec.     | Número de contribuidores |
| `median_release_interval` | float  | ⚠️ Rec.     | Intervalo mediano (dias) |
| `release_type`            | string | ✅ Sim      | rapid/slow               |

### Exemplo de CSV

```csv
owner,name,stars,forks,language,release_count,contributors,median_release_interval,release_type,reason
neovim,neovim,94249,6414,Vim Script,47,134400,62,SLOW,62 dias entre releases
gin-gonic,gin,86983,8488,Go,28,49300,119,SLOW,119 dias entre releases
```

---

## 📊 Métricas Coletadas pelo SonarQube

O arquivo `*_analyzed.csv` incluirá:

| Métrica                    | Descrição                          |
| -------------------------- | ---------------------------------- |
| `bugs`                     | Número de bugs detectados          |
| `vulnerabilities`          | Vulnerabilidades de segurança      |
| `code_smells`              | Problemas de manutenibilidade      |
| `coverage`                 | Cobertura de testes (%)            |
| `duplicated_lines_density` | Densidade de código duplicado (%)  |
| `ncloc`                    | Linhas de código (sem comentários) |
| `complexity`               | Complexidade ciclomática           |
| `cognitive_complexity`     | Complexidade cognitiva             |
| `reliability_rating`       | Rating de confiabilidade (A-E)     |
| `security_rating`          | Rating de segurança (A-E)          |
| `sqale_rating`             | Rating de manutenibilidade (A-E)   |
| `sqale_index`              | Dívida técnica (minutos)           |

---

## ⚙️ Opções de Linha de Comando

### `analyze_csv_repos.py`

```bash
python analyze_csv_repos.py [OPÇÕES]

OPÇÕES:
  --csv FILE          Arquivo CSV de entrada (obrigatório)
  --workers N         Número de processos paralelos (padrão: 1)
  --limit N           Limitar número de análises
  --skip-analyzed     Pular repositórios já analisados
  --output FILE       Arquivo de saída customizado

EXEMPLOS:
  # Teste rápido
  python analyze_csv_repos.py --csv repos.csv --limit 3

  # Produção (paralelo)
  python analyze_csv_repos.py --csv repos.csv --workers 4

  # Retomar análise
  python analyze_csv_repos.py --csv repos.csv --workers 4 --skip-analyzed
```

---

## 🔄 Comparação: JSON vs CSV

| Aspecto              | Workflow JSON                     | Workflow CSV                  |
| -------------------- | --------------------------------- | ----------------------------- |
| **Fonte de Dados**   | GitHub API (coleta automática)    | Arquivo CSV pré-existente     |
| **Scripts**          | 1_collect + 2_analyze             | analyze_csv_repos             |
| **Flexibilidade**    | ⭐⭐⭐⭐⭐ (filtros customizados) | ⭐⭐⭐ (dados fixos)          |
| **Velocidade Setup** | Lenta (busca GitHub)              | Rápida (dados já coletados)   |
| **Saída**            | JSON + CSV opcional               | CSV com análises              |
| **Ideal Para**       | Pesquisa nova, dataset dinâmico   | Análise de lista pré-definida |

---

## 🐛 Troubleshooting

### Problema: "CSV não encontrado"

```bash
# Verifique o caminho
ls slow_release_repos_*.csv  # Linux/macOS
dir slow_release_repos_*.csv  # Windows
```

### Problema: "Erro ao ler CSV"

```python
# Verifique o formato
import csv
with open('seu_arquivo.csv') as f:
    reader = csv.DictReader(f)
    print(reader.fieldnames)  # Mostra as colunas
```

### Problema: "Muitos repositórios falhando"

- ✅ Verifique se os repositórios ainda existem no GitHub
- ✅ Alguns podem ser privados ou deletados
- ✅ Use `--limit 5` primeiro para testar

### Problema: "SonarScanner timeout"

```python
# Aumente o timeout em analyze_csv_repos.py linha ~190
timeout=1800  # 30 minutos ao invés de 15
```

---

## 📈 Performance e Otimização

### Recomendações de Workers

| RAM Disponível | Workers Recomendados |
| -------------- | -------------------- |
| 4 GB           | 1-2                  |
| 8 GB           | 2-4                  |
| 16 GB          | 4-8                  |
| 32 GB          | 8-12                 |

### Tempo por Repositório

- **Pequeno** (< 1 MB): 2-3 minutos
- **Médio** (1-10 MB): 3-5 minutos
- **Grande** (> 10 MB): 5-10 minutos

**Dica:** Use `--limit 5` para estimar o tempo total antes de processar tudo.

---

## 🔬 Análise de Dados Pós-Processamento

### Carregar Resultados em Python

```python
import pandas as pd

# Carrega CSV com análises
df = pd.read_csv('slow_release_repos_20251115_053707_analyzed.csv')

# Filtra apenas os analisados com sucesso
analyzed = df[df['sonarqube_analyzed'] == True]

# Estatísticas descritivas
print(analyzed[['bugs', 'vulnerabilities', 'code_smells', 'coverage']].describe())

# Comparação Rapid vs Slow
rapid = analyzed[analyzed['release_type'] == 'rapid']
slow = analyzed[analyzed['release_type'] == 'slow']

print(f"Rapid - Bugs médios: {rapid['bugs'].mean()}")
print(f"Slow - Bugs médios: {slow['bugs'].mean()}")
```

### Visualização com Matplotlib

```python
import matplotlib.pyplot as plt

# Gráfico de dispersão: Coverage vs Bugs
plt.scatter(analyzed['coverage'], analyzed['bugs'])
plt.xlabel('Cobertura de Testes (%)')
plt.ylabel('Número de Bugs')
plt.title('Relação entre Cobertura e Bugs')
plt.show()
```

---

## 📚 Recursos Adicionais

- **Guia Completo CSV**: `GUIA_CSV_ANALYSIS.md`
- **Instruções Copilot**: `.github/copilot-instructions.md`
- **Guia Rápido Original**: `GUIA_RAPIDO.md`
- **Implementação Completa**: `IMPLEMENTACAO_COMPLETA.md`

---

## 🤝 Suporte

Problemas comuns:

1. **Docker não está rodando** → `docker-compose up -d`
2. **Token não configurado** → Edite `.env`
3. **CSV com formato errado** → Verifique colunas obrigatórias

Para mais detalhes, consulte os guias na raiz do projeto.

---

**Última Atualização:** 16/11/2025  
**Versão do Sistema:** 2.1 (com suporte CSV)
