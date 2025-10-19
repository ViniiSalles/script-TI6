# Script de Automação de Pesquisa GitHub + SonarQube

Este projeto automatiza a pesquisa comparativa entre projetos de software open-source com Rapid Release Cycles (RRCs) e Slow Releases, coletando dados do GitHub via API GraphQL, executando análises de qualidade de código com SonarQube e persistindo métricas em PostgreSQL.

## 📋 Pré-requisitos

### Software Necessário

- **Docker Desktop** (em execução)
- **Python 3.7+**
- **Git**

### Tokens de API

- **GitHub Personal Access Token** com permissões de leitura de repositórios
- **SonarQube Token** (gerado após configuração inicial)

> ⚠️ **Nota**: O SonarScanner CLI **não** precisa ser instalado separadamente. O script usa a imagem Docker oficial `sonarsource/sonar-scanner-cli`.

## 🚀 Instalação e Configuração

### 1. Clone e Configure o Ambiente

```bash
# Clone ou prepare o diretório
cd script-TI6

# Instale dependências Python
pip install -r requirements.txt
```

### 2. Configure Variáveis de Ambiente

Copie `.env.example` para `.env` e configure:

```bash
cp .env.example .env
```

Edite `.env` com seus tokens:

```bash
# GitHub API Configuration
GITHUB_TOKEN=seu_token_github_aqui

# SonarQube Configuration
SONAR_HOST=http://localhost:9000
SONAR_TOKEN=seu_token_sonar_aqui

# Database Configuration
DB_HOST=localhost
DB_NAME=sonar
DB_USER=sonar
DB_PASSWORD=sonar
DB_PORT=5432
```

### 3. Inicie os Serviços

```bash
# Inicia SonarQube e PostgreSQL
docker-compose up -d

# Verifica se os serviços estão rodando
docker-compose ps
```

### 4. Configure o SonarQube

1. Acesse http://localhost:9000
2. Login inicial: `admin/admin`
3. Altere a senha quando solicitado
4. Vá em **Administration > Security > Users**
5. Clique em **Tokens** para o usuário admin
6. Gere um novo token e copie para a variável `SONAR_TOKEN` no `.env`

### 5. Verificação

Antes de executar, o script verificará automaticamente:

```bash
# Execute o script - ele verificará os pré-requisitos
python research_automation_script.py
```

O script verificará:

- ✅ Git instalado
- ✅ Docker instalado e em execução
- ✅ Variáveis de ambiente configuradas

## 🔧 Uso

### Execução Principal

```bash
# Windows PowerShell
python research_automation_script.py

# Linux/macOS
python3 research_automation_script.py
```

### O que o Script Faz

1. **Busca Repositórios**: Usa a API REST do GitHub para encontrar repositórios com:

   - Mínimo de 50 stars e 50 forks
   - Diferentes linguagens de programação
   - Filtros por colaboradores (≥19) e releases (≥19)

2. **Classifica Releases**:

   - **Rapid**: Intervalo médio entre releases de 5-35 dias
   - **Slow**: Intervalo médio ≥60 dias
   - **Unclassified**: Demais casos

3. **Coleta Métricas GitHub**:

   - Issues, Pull Requests, Releases
   - Taxas de merge, tempos de fechamento
   - Colaboradores, linguagens

4. **Análise SonarQube**:

   - Clona repositórios temporariamente (com tratamento de permissões Windows)
   - Executa análise via Docker: `docker run sonarsource/sonar-scanner-cli`
   - Coleta métricas de qualidade de código
   - Limpa diretórios temporários automaticamente

5. **Armazena Dados**: Persiste tudo no PostgreSQL

## 📊 Estrutura do Banco de Dados

### Tabelas Criadas

- **repositories**: Dados gerais e métricas calculadas
- **pull_requests**: Detalhes de cada PR
- **issues**: Detalhes de cada issue
- **sonarqube_metrics**: Métricas de qualidade de código

### Consultas de Exemplo

```sql
-- Repositórios por tipo de release
SELECT release_type, COUNT(*) FROM repositories GROUP BY release_type;

-- Métricas médias de qualidade por tipo
SELECT r.release_type,
       AVG(s.bugs) as avg_bugs,
       AVG(s.vulnerabilities) as avg_vulnerabilities,
       AVG(s.coverage) as avg_coverage
FROM repositories r
JOIN sonarqube_metrics s ON r.id = s.repo_id
GROUP BY r.release_type;

-- Top repositórios por taxa de merge
SELECT full_name, pull_request_merge_rate
FROM repositories
ORDER BY pull_request_merge_rate DESC
LIMIT 10;
```

## ⚙️ Configurações Avançadas

### Ajustar Número de Repositórios

No arquivo `research_automation_script.py`, modifique:

```python
target_repos_per_type = 500  # Linha ~658
```

### Adicionar Filtros de Busca

Modifique a lista `search_queries` na função `main()`:

```python
search_queries = [
    "stars:>100 forks:>100 language:Python",
    "stars:>50 forks:>50 language:Rust",
    # Adicione mais queries aqui
]
```

### Timeouts e Delays

Ajuste conforme necessário:

```python
# Timeout para clonagem (linha ~490)
timeout=300  # 5 minutos

# Timeout para SonarScanner (linha ~516)
timeout=600  # 10 minutos

# Delay entre requisições (linha ~648)
time.sleep(2)
```

## 🐛 Troubleshooting

### Erro: "Rate limit exceeded"

- O script aguarda automaticamente quando o rate limit é atingido
- GitHub permite 5000 requests/hora para usuários autenticados

### Erro: "Docker não está instalado ou não está no PATH"

- Verifique se o Docker Desktop está instalado
- Verifique se o Docker Desktop está **em execução**
- Teste: `docker --version` e `docker ps`
- Windows: Reinicie o Docker Desktop se necessário

### Erro: "[WinError 5] Acesso negado" (Windows)

- ✅ **Corrigido**: O script agora trata permissões de arquivos Git automaticamente
- Se persistir, execute o PowerShell como Administrador

### Erro de Conexão com SonarQube via Docker

- Verifique se o SonarQube está rodando: `docker-compose ps`
- Teste acesso: http://localhost:9000
- Use `--network host` no Docker (já configurado no script)
- Logs: `docker-compose logs sonarqube`

### Erro de Conexão com Banco

- Verifique se os containers estão rodando: `docker-compose ps`
- Verifique as credenciais no `.env`
- Logs: `docker-compose logs db`

### SonarQube não Inicia

- Aumente memória se necessário:

```yaml
# No docker-compose.yml, adicione:
environment:
  - "SONAR_ES_BOOTSTRAP_CHECKS_DISABLE=true"
```

### Espaço em Disco

- **Windows**: Repositórios clonados em `C:\Users\<Usuario>\AppData\Local\Temp\repos_analise\`
- **Linux/macOS**: Repositórios clonados em `/tmp/repos_analise/`
- Diretórios são limpos automaticamente após análise
- Em caso de falha, limpe manualmente:
  - Windows: `Remove-Item -Recurse -Force $env:TEMP\repos_analise`
  - Linux/macOS: `rm -rf /tmp/repos_analise/`

## 📈 Monitoramento

### Logs do Script

O script exibe progresso em tempo real:

- Status de cada repositório processado
- Relatórios a cada 10 repositórios
- Erros e warnings detalhados

### Logs dos Serviços

```bash
# SonarQube
docker-compose logs sonarqube

# PostgreSQL
docker-compose logs db
```

### Interface SonarQube

- Acesse http://localhost:9000
- Veja projetos analisados em **Projects**
- Monitore qualidade de código por projeto

## 🔧 Manutenção

### Backup do Banco

```bash
docker exec sonarqube_db pg_dump -U sonar sonar > backup.sql
```

### Limpeza de Dados

```sql
-- Limpar dados antigos
DELETE FROM sonarqube_metrics WHERE analysis_date < '2024-01-01';
DELETE FROM pull_requests WHERE repo_id NOT IN (SELECT id FROM repositories);
DELETE FROM issues WHERE repo_id NOT IN (SELECT id FROM repositories);
```

### Restart dos Serviços

```bash
docker-compose restart
```

## 📄 Licença

Este projeto foi desenvolvido para fins de pesquisa acadêmica.

## 🤝 Contribuição

Para melhorias ou correções:

1. Documente o problema encontrado
2. Teste a solução proposta
3. Verifique impacto na performance
4. Considere rate limits das APIs

---

**Nota**: Este script realiza análises intensivas e pode consumir recursos significativos. Monitore o uso de CPU, memória e espaço em disco durante a execução.
