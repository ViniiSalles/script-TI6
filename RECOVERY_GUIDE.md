# Guia de Recuperação de Dados - CSV Corrompido

## 🚨 Problema: CSV Corrompido Durante Análise Paralela

Quando o CSV é corrompido (linha mal formatada), a análise para e você perde o progresso. Este guia mostra como recuperar os dados do banco de dados SonarQube.

## 🛠️ Ferramentas de Recuperação

### 1. `diagnose_csv.py` - Diagnóstico de Problemas

Identifica onde o CSV foi corrompido:

```bash
# Diagnosticar CSV
python diagnose_csv.py slow_release_repos_20251115_053707_analyzed.csv

# Diagnosticar e corrigir automaticamente
python diagnose_csv.py slow_release_repos_20251115_053707_analyzed.csv --fix

# Truncar manualmente na linha 170
python diagnose_csv.py slow_release_repos_20251115_053707_analyzed.csv --truncate-at 170 --output fixed.csv
```

**Saída Esperada:**

```
🔍 DIAGNÓSTICO: slow_release_repos_20251115_053707_analyzed.csv
================================================================================

📊 Total de linhas (raw): 775
📋 Cabeçalho: 25 campos
   Campos: owner, name, full_name, stargazer_count, fork_count...

🔬 Tentando ler com csv.DictReader...
   ❌ Erro na linha 171: field larger than field limit (131072)
   ✅ Linhas válidas lidas: 169
   📍 Última linha válida: 170

================================================================================
❌ PROBLEMAS ENCONTRADOS: 1
================================================================================

1. CSV_ERROR (Linha 171)
   Erro ao ler linha: field larger than field limit (131072)
```

### 2. `recover_from_sonarqube_db.py` - Recuperação do Banco

Extrai métricas do PostgreSQL do SonarQube:

```bash
# Listar projetos no SonarQube
python recover_from_sonarqube_db.py --list-projects

# Dry-run (testa sem modificar)
python recover_from_sonarqube_db.py --csv slow_release_repos_20251115_053707_analyzed.csv --dry-run

# Recuperar métricas de fato
python recover_from_sonarqube_db.py --csv slow_release_repos_20251115_053707_analyzed.csv
```

**Saída Esperada:**

```
🔧 RECUPERAÇÃO DE MÉTRICAS DO BANCO SONARQUBE
================================================================================

📂 Lendo CSV: slow_release_repos_20251115_053707_analyzed.csv
✅ 775 repositórios carregados

📊 Status do CSV:
   ✅ Com métricas: 170
   ❌ Sem métricas: 605

🔍 Buscando projetos no SonarQube...
✅ 590 projetos encontrados no banco

🔄 Recuperando métricas...

[1/605] massgravel/Microsoft-Activation-Scripts
   ⚠️  Projeto não encontrado no SonarQube

[2/605] bitcoin/bitcoin
   ✅ Recuperado: bugs=24, ncloc=60719, rating=A

[3/605] opencv/opencv
   ✅ Recuperado: bugs=142, ncloc=125430, rating=B

...

================================================================================
📊 RELATÓRIO DE RECUPERAÇÃO
================================================================================
✅ Recuperados: 420
⚠️  Não encontrados: 185
❌ Falharam: 0
================================================================================

✅ CSV recuperado salvo: slow_release_repos_20251115_053707_analyzed_recovered.csv
   Total de repositórios: 775
   Com métricas agora: 590
```

## 📋 Fluxo Completo de Recuperação

### Passo 1: Diagnosticar o Problema

```bash
python diagnose_csv.py slow_release_repos_20251115_053707_analyzed.csv
```

Anote a **última linha válida** (ex: linha 170).

### Passo 2: Corrigir CSV (Remover Linhas Corrompidas)

```bash
# Opção A: Correção automática
python diagnose_csv.py slow_release_repos_20251115_053707_analyzed.csv --fix

# Opção B: Truncamento manual
python diagnose_csv.py slow_release_repos_20251115_053707_analyzed.csv --truncate-at 170 --output clean.csv
```

Isso cria `*_fixed.csv` com apenas as linhas válidas.

### Passo 3: Recuperar Métricas do Banco SonarQube

```bash
# Teste primeiro (dry-run)
python recover_from_sonarqube_db.py --csv slow_release_repos_20251115_053707_analyzed_fixed.csv --dry-run

# Se OK, recupera de verdade
python recover_from_sonarqube_db.py --csv slow_release_repos_20251115_053707_analyzed_fixed.csv
```

Isso cria `*_recovered.csv` com métricas extraídas do banco.

### Passo 4: Continuar Análise

Use o CSV recuperado como entrada para continuar:

```bash
# Renomeia recovered para analyzed (substitui corrompido)
mv slow_release_repos_20251115_053707_analyzed_recovered.csv slow_release_repos_20251115_053707_analyzed.csv

# Continua análise dos repos que NÃO estão no SonarQube
python analyze_csv_repos.py --csv slow_release_repos_20251115_053707.csv --workers 4 --skip-analyzed
```

## 🔍 Como Funciona a Recuperação do Banco

### Estrutura do Banco SonarQube

```sql
-- Projetos analisados
SELECT kee, name FROM projects WHERE qualifier = 'TRK';
-- Exemplo: bitcoin_bitcoin, opencv_opencv

-- Métricas de um projeto
SELECT m.name, pm.value, pm.text_value
FROM project_measures pm
JOIN metrics m ON pm.metric_uuid = m.uuid
WHERE pm.component_uuid = '...'
AND m.name IN ('bugs', 'ncloc', 'coverage', ...);
```

### Conversão de Ratings

SonarQube armazena ratings como números:

- `1` = A (melhor)
- `2` = B
- `3` = C
- `4` = D
- `5` = E (pior)

O script converte automaticamente para letras.

## 🎯 Cenários de Uso

### Cenário 1: CSV Corrompido na Linha 171

```bash
# 1. Diagnostica
python diagnose_csv.py file.csv

# 2. Corrige (mantém até linha 170)
python diagnose_csv.py file.csv --fix

# 3. Recupera do banco (170-590)
python recover_from_sonarqube_db.py --csv file_fixed.csv

# 4. Continua análise (590-775)
python analyze_csv_repos.py --csv file.csv --skip-analyzed --workers 4
```

### Cenário 2: Análise Travou mas Banco Tem Dados

```bash
# Se você tem 590 análises no SonarQube mas CSV só tem 170:
python recover_from_sonarqube_db.py --csv file.csv
# Recupera as 420 análises faltantes diretamente do banco
```

### Cenário 3: Verificar Integridade Antes de Continuar

```bash
# Sempre rode diagnóstico antes de análise longa
python diagnose_csv.py slow_release_repos_20251115_053707_analyzed.csv

# Se aparecer "✅ NENHUM PROBLEMA ENCONTRADO", pode continuar
python analyze_csv_repos.py --csv slow_release_repos.csv --workers 4 --skip-analyzed
```

## ⚠️ Limitações

1. **Só recupera projetos que FORAM analisados pelo SonarQube**

   - Se repo nunca foi analisado, o banco não tem dados
   - Use `--list-projects` para ver o que está disponível

2. **Requer acesso ao banco PostgreSQL**

   - Verifique `.env`: `DB_HOST`, `DB_USER`, `DB_PASSWORD`
   - Por padrão: `localhost:5432`, user `sonar`, senha `sonar`

3. **Project key deve bater**
   - Formato: `owner_name` (ex: `bitcoin_bitcoin`)
   - Se nome mudou, não vai encontrar

## 📊 Checklist de Recuperação

- [ ] Diagnosticar CSV com `diagnose_csv.py`
- [ ] Anotar última linha válida
- [ ] Corrigir CSV removendo linhas corrompidas
- [ ] Verificar integridade do CSV corrigido
- [ ] Testar recuperação do banco (dry-run)
- [ ] Recuperar métricas do banco
- [ ] Validar CSV recuperado
- [ ] Substituir CSV corrompido pelo recuperado
- [ ] Continuar análise com `--skip-analyzed`

## 🆘 Troubleshooting

### Erro: "Connection refused" ao conectar no banco

```bash
# Verifica se PostgreSQL está rodando
docker-compose ps

# Se não estiver, inicia
docker-compose up -d

# Testa conexão
psql -h localhost -U sonar -d sonar
# Senha: sonar
```

### Erro: "field larger than field limit"

Linha tem campo muito grande (>131KB). Isso acontece quando dados binários ou muito texto são escritos indevidamente.

**Solução**: Trunca CSV na linha anterior ao erro.

### Muitos repos "não encontrados" no SonarQube

Significa que esses repos nunca foram analisados (processo crashou antes). Você precisa analisá-los do zero:

```bash
python analyze_csv_repos.py --csv file.csv --skip-analyzed --workers 4
```

---

**Criado em**: 16 de novembro de 2025  
**Versão**: 1.0
