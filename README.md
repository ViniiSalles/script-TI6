# Script de Automação de Pesquisa GitHub + SonarQube

Este projeto automatiza a pesquisa comparativa entre projetos de software open-source com **Rapid Release Cycles (RRCs)** e **Slow Releases**, coletando dados do GitHub via API GraphQL/REST e executando análises de qualidade de código com SonarQube.

### 🏗️ Arquitetura: Sistema Modular em Duas Fases

#### **Fase 1: Coleta de Repositórios** (`1_collect_repositories.py`)

- Busca repositórios no GitHub via API
- Filtra por critérios (stars, forks, releases, contribuidores)
- Classifica como Rapid ou Slow
- Salva dataset em `repositories_dataset.json`
- **Vantagem**: Evita re-consultar a API GitHub a cada análise

#### **Fase 2: Análise SonarQube** (`2_analyze_sonarqube.py` ou `analyze_csv_repos.py`)

- Clona repositórios temporariamente
- Executa SonarScanner via Docker
- Extrai métricas das tabelas do próprio SonarQube
- Atualiza dataset (JSON ou CSV)
- **Vantagem**: Análise incremental com recuperação de falhas

### 📋 Pré-requisitos

#### Software Necessário

- **Docker Desktop** (em execução) - para SonarQube
- **Python 3.7+**
- **Git**

#### Tokens de API

- **GitHub Personal Access Token** com permissões de leitura de repositórios
- **SonarQube Token** (gerado após configuração inicial)

> ⚠️ **Nota**: O SonarScanner CLI **não** precisa ser instalado localmente. O script usa a imagem Docker oficial `sonarsource/sonar-scanner-cli`.

### 🚀 Instalação e Configuração

#### 1. Clone e Configure o Ambiente

```bash
# Clone ou prepare o diretório
cd script-TI6

# Instale dependências Python
pip install -r requirements.txt
```

#### 2. Configure Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto:

```bash
# GitHub API Configuration
GITHUB_TOKEN=seu_token_github_aqui

# SonarQube Configuration
SONAR_HOST=http://localhost:9000
SONAR_TOKEN=seu_token_sonar_aqui

# Database Configuration (opcional - o SonarQube gerencia suas próprias tabelas)
DB_HOST=localhost
DB_NAME=sonar
DB_USER=sonar
DB_PASSWORD=sonar
DB_PORT=5432
```

> **Nota**: O PostgreSQL é usado apenas pelo SonarQube. Os dados da pesquisa são salvos em JSON/CSV.

#### 3. Inicie os Serviços

```bash
# Inicia SonarQube e PostgreSQL
docker-compose up -d

# Verifica se os serviços estão rodando
docker-compose ps
```

#### 4. Configure o SonarQube

1. Acesse http://localhost:9000
2. Login inicial: `admin/admin`
3. Altere a senha quando solicitado
4. Vá em **Administration > Security > Users**
5. Clique em **Tokens** para o usuário admin
6. Gere um novo token e copie para a variável `SONAR_TOKEN` no `.env`

#### 5. Verificação Inicial

Execute testes para verificar o ambiente:

```bash
# Testa conexão com SonarQube
python tests/test_sonar_docker.py

# Testa configuração Python
python tests/test_platform_compatibility.py
```

### 🔧 Uso

#### Workflow Completo (JSON)

```bash
# FASE 1: Coleta repositórios do GitHub
python 1_collect_repositories.py --rapid 50 --slow 50 --max-search 2000

# FASE 2: Analisa com SonarQube (paralelizado)
python 2_analyze_sonarqube.py --workers 4 --skip-analyzed
```

#### Workflow com CSV Pré-Coletado

Se você já tem um CSV com repositórios:

```bash
# Analisa repositórios do CSV
python analyze_csv_repos.py --csv slow_release_repos.csv --workers 4 --limit 50

# Retoma análise após falhas
python analyze_csv_repos.py --csv slow_release_repos.csv --workers 4 --skip-analyzed
```

#### Detalhamento das Fases

##### **Fase 1: Coleta (`1_collect_repositories.py`)**

```bash
# Coleta 100 rapid + 100 slow
python 1_collect_repositories.py --rapid 100 --slow 100

# Expande dataset existente (adiciona mais)
python 1_collect_repositories.py --rapid 200 --slow 200 --max-search 5000
```

**O que faz:**

- Busca repositórios via API REST do GitHub
- Filtra por: stars ≥50, forks ≥50, contributors ≥19, releases ≥19
- Classifica como **Rapid** (5-35 dias entre releases) ou **Slow** (≥60 dias)
- Salva em `repositories_dataset.json`
- **Não faz** clonagem ou análise (rápido e reutilizável)

##### **Fase 2: Análise (`2_analyze_sonarqube.py`)**

```bash
# Analisa todos os repositórios do dataset
python 2_analyze_sonarqube.py --workers 4

# Analisa apenas tipo específico
python 2_analyze_sonarqube.py --type rapid --limit 20 --workers 2

# Pula já analisados (recuperação de falhas)
python 2_analyze_sonarqube.py --skip-analyzed --workers 4
```

**O que faz:**

1. Clona repositórios em diretório temporário (`%TEMP%\repos_analise\`)
2. Verifica tamanho (pula se >2GB)
3. Executa SonarScanner via Docker: `docker run sonarsource/sonar-scanner-cli`
4. Extrai 13 métricas das **tabelas do próprio SonarQube**
5. Atualiza dataset JSON/CSV
6. Limpa diretório temporário automaticamente

**Paralelização:**

- `--workers 4`: Analisa 4 repos simultaneamente
- Recomendado: 4 workers em máquina com 8GB RAM e SSD

### 📊 Dados Coletados e Métricas

#### Persistência de Dados

O sistema usa **JSON/CSV como fonte única de verdade**, gerenciado pelo `DatasetManager`:

```python
from dataset_manager import DatasetManager

# Modo JSON
dm = DatasetManager("repositories_dataset.json")
repos = dm.get_repositories(release_type='rapid', limit=10)

# Modo CSV (auto-detectado por extensão .csv)
dm_csv = DatasetManager("slow_release_repos.csv")
repos = dm_csv.get_repositories()
```

**Formato CSV esperado:**

```
owner,name,stars,forks,language,release_count,contributors,median_release_interval,release_type,reason
```

**Persistência incremental**: Quando existe `*_analyzed.csv`, carrega dele ao invés do CSV original, preservando análises anteriores.

#### Métricas do SonarQube (13 Métricas)

As métricas são extraídas diretamente das **tabelas do próprio SonarQube** (não criamos tabelas customizadas):

| Métrica                    | Descrição                                  |
| -------------------------- | ------------------------------------------ |
| `bugs`                     | Número de bugs detectados                  |
| `vulnerabilities`          | Número de vulnerabilidades de segurança    |
| `code_smells`              | Número de code smells                      |
| `sqale_index`              | Débito técnico (em minutos)                |
| `coverage`                 | Cobertura de testes (%)                    |
| `duplicated_lines_density` | Densidade de linhas duplicadas (%)         |
| `ncloc`                    | Linhas de código (sem comentários/brancos) |
| `complexity`               | Complexidade ciclomática                   |
| `cognitive_complexity`     | Complexidade cognitiva                     |
| `reliability_rating`       | Rating de confiabilidade (A-E)             |
| `security_rating`          | Rating de segurança (A-E)                  |
| `sqale_rating`             | Rating de manutenibilidade (A-E)           |
| `alert_status`             | Status do Quality Gate (OK/ERROR)          |

#### Consultar Dados

```bash
# Estatísticas do dataset
python -c "from dataset_manager import DatasetManager; DatasetManager().print_statistics()"

# Exportar para CSV
python -c "from dataset_manager import DatasetManager; DatasetManager().export_to_csv('results.csv')"
```

#### Acesso Direto ao SonarQube

Interface web: http://localhost:9000

- Login: `admin` (senha configurada na instalação)
- Visualize projetos analisados em **Projects**
- Métricas detalhadas por projeto

### ⚙️ Configurações Avançadas

#### Critérios de Classificação

Editável em `1_collect_repositories.py`:

```python
# Rapid Release: 5-35 dias entre releases
if 5 <= avg_interval <= 35 and release_count >= 19 and contributors >= 19:
    return 'rapid'

# Slow Release: ≥60 dias entre releases
if avg_interval >= 60 and release_count >= 19 and contributors >= 19:
    return 'slow'
```

#### Ajustar Quantidade de Repositórios

```bash
# Coletar mais repositórios
python 1_collect_repositories.py --rapid 500 --slow 500 --max-search 10000
```

#### Timeouts e Paralelização

No arquivo `2_analyze_sonarqube.py`:

```python
# Timeout para clonagem
timeout=300  # 5 minutos

# Timeout para SonarScanner
timeout=600  # 10 minutos

# Número de workers paralelos
--workers 4  # Via linha de comando
```

#### Adicionar Linguagens de Programação

Modifique queries em `1_collect_repositories.py`:

```python
search_queries = [
    "stars:>50 forks:>50 language:Python",
    "stars:>50 forks:>50 language:JavaScript",
    "stars:>50 forks:>50 language:Rust",
    # Adicione mais linguagens
]
```

### 🐛 Troubleshooting

#### Erro: "Rate limit exceeded" (GitHub API)

- ✅ O script aguarda automaticamente quando o rate limit é atingido
- GitHub permite 5000 requests/hora para usuários autenticados
- Verifique se o `GITHUB_TOKEN` está configurado no `.env`

#### Erro: "Docker não está instalado ou não está no PATH"

```bash
# Verifique instalação
docker --version
docker ps

# Windows: Reinicie o Docker Desktop
# Linux: sudo systemctl restart docker
```

#### Erro: "[WinError 5] Acesso negado" (Windows)

✅ **Corrigido**: O script agora trata permissões de arquivos Git automaticamente via `handle_remove_readonly()`.

Se persistir:

```powershell
# Execute como Administrador
Remove-Item -Recurse -Force $env:TEMP\repos_analise
```

#### Erro de Conexão com SonarQube

```bash
# Verifique status dos containers
docker-compose ps

# Teste acesso
curl http://localhost:9000/api/system/status

# Visualize logs
docker-compose logs sonarqube
```

Se o SonarQube não responder, aguarde ~2 minutos para inicialização completa.

#### Repositório >2GB Pulado Automaticamente

✅ **Comportamento esperado**: O script pula automaticamente repositórios maiores que 2GB para evitar consumo excessivo de recursos.

#### Análise Falhou para Repositório Específico

```bash
# Retome análise pulando já concluídos
python 2_analyze_sonarqube.py --skip-analyzed --workers 4

# Para CSV
python analyze_csv_repos.py --csv repos.csv --skip-analyzed --workers 4
```

#### Espaço em Disco

- **Windows**: `%TEMP%\repos_analise\owner_name_{worker_id}`
- **Linux/macOS**: `/tmp/repos_analise/owner_name_{worker_id}`
- Limpeza automática após análise
- Limpeza manual se necessário:

```bash
# Windows PowerShell
Remove-Item -Recurse -Force $env:TEMP\repos_analise

# Linux/macOS
rm -rf /tmp/repos_analise/
```

#### Verificação de Integridade

```bash
# Testa SonarQube via Docker
python tests/test_sonar_docker.py

# Testa compatibilidade do sistema
python tests/test_platform_compatibility.py

# Valida CSV/JSON
python tests/test_incremental_csv.py
```

### 📈 Monitoramento e Performance

#### Progresso em Tempo Real

O `ProgressTracker` exibe status durante análise paralela:

```
[15/100] ✅ kubernetes/kubernetes - Concluído
[████████████░░░░░] 75% | ✅ 70 | ❌ 5 | ETA: 12.3min
```

#### Logs dos Serviços

```bash
# SonarQube
docker-compose logs -f sonarqube

# PostgreSQL
docker-compose logs -f db
```

#### Interface SonarQube

- **URL**: http://localhost:9000
- **Login**: `admin` (senha configurada na primeira execução)
- Visualize todos os projetos analisados
- Métricas detalhadas por repositório

#### Estatísticas do Dataset

```bash
# Status dos repositórios
python -c "from dataset_manager import DatasetManager; DatasetManager().print_statistics()"

# Exemplo de saída:
# Total: 100 repos
# Rapid: 50 (40 analisados)
# Slow: 50 (35 analisados)
# Pendentes: 15
```

### 🔧 Manutenção

#### Backup de Dados

```bash
# Backup do dataset JSON
cp repositories_dataset.json repositories_dataset_backup_$(date +%Y%m%d).json

# Backup do banco SonarQube
docker exec sonarqube_db pg_dump -U sonar sonar > sonarqube_backup.sql

# Backup de CSV analisados
cp *_analyzed.csv backups/
```

#### Limpeza de Projetos no SonarQube

```bash
# Acesse: http://localhost:9000/admin/projects_management
# Ou via API:
curl -u admin:sua_senha -X POST "http://localhost:9000/api/projects/delete?project=owner_name"
```

#### Restart dos Serviços

```bash
# Reinicia tudo
docker-compose restart

# Apenas SonarQube
docker-compose restart sonarqube
```

#### Re-analisar Repositório Específico

```python
from dataset_manager import DatasetManager

# Marca como não analisado
dm = DatasetManager()
dataset = dm.load_dataset()
for repo in dataset['repositories']:
    if repo['full_name'] == 'owner/name':
        repo['sonarqube_analyzed'] = False
dm.save_dataset(dataset)

# Depois execute:
# python 2_analyze_sonarqube.py --skip-analyzed
```

### 📂 Estrutura de Arquivos

```
1_collect_repositories.py       # Fase 1: Coleta repositórios do GitHub
2_analyze_sonarqube.py          # Fase 2: Análise SonarQube (entrada JSON)
analyze_csv_repos.py            # Fase 2: Análise SonarQube (entrada CSV)
dataset_manager.py              # Gerenciador de persistência (JSON/CSV)
utils.py                        # GitHubAPI, SonarQubeAPI, helpers
docker-compose.yml              # SonarQube + PostgreSQL
repositories_dataset.json       # Dataset principal (gerado por script 1)
*_analyzed.csv                  # Resultados de análise (gerado por CSV)
tests/                          # Testes de validação
```

**Arquivo Legado**: `research_automation_script.py` (monolítico, deprecated)

### 📊 Performance

#### Coleta (Fase 1)

- 100 repositórios ≈ 200-300 chamadas de API
- Tempo estimado: 30-60 minutos
- Rate limit: 5000 requests/hora (GitHub autenticado)

#### Análise (Fase 2)

- **Sequencial**: ~5-10 minutos por repositório
- **Paralelo (4 workers)**: ~2-3 minutos por repositório
- **Memória**: ~500MB por worker
- **Limite**: Repositórios >2GB são automaticamente pulados

#### Otimização

```bash
# Máquina com 8GB RAM + SSD
python 2_analyze_sonarqube.py --workers 4

# Máquina com 16GB RAM + SSD
python 2_analyze_sonarqube.py --workers 8

# Análise limitada (teste)
python 2_analyze_sonarqube.py --limit 10 --workers 2
```

### 🧪 Testes

Execute antes de mudanças críticas:

```bash
# Valida lógica de classificação
python tests/test_filters.py

# Testa Docker + SonarQube
python tests/test_sonar_docker.py

# Compatibilidade Windows/Linux
python tests/test_platform_compatibility.py

# Persistência incremental CSV
python tests/test_incremental_csv.py
```

### 📚 Documentação Adicional

- [RECOVERY_GUIDE.md](RECOVERY_GUIDE.md) - Recuperação de análises falhadas
- [README_CSV.md](README_CSV.md) - Guia específico para análise via CSV
- [PROTECOES_SONARQUBE.md](PROTECOES_SONARQUBE.md) - Segurança e limites

### 📄 Licença

Este projeto foi desenvolvido para fins de pesquisa acadêmica.

### 🤝 Contribuição

Para melhorias ou correções:

1. Documente o problema encontrado
2. Teste a solução proposta
3. Execute os testes de verificação
4. Considere impacto em rate limits e performance
5. Mantenha separação entre Fase 1 (coleta) e Fase 2 (análise)

---

**⚠️ Notas Importantes**:

- Este sistema realiza análises intensivas. Monitore CPU, memória e disco durante execução.
- Scripts de coleta **nunca** clonam repositórios.
- Scripts de análise **nunca** buscam no GitHub.
- `DatasetManager` é a única fonte de verdade para estado dos repositórios.
- SonarQube gerencia suas próprias tabelas - não criamos tabelas customizadas.
