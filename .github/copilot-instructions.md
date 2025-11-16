# Copilot Instructions - GitHub + SonarQube Research Automation

## Project Overview

Academic research system for comparing **Rapid Release Cycle (RRC)** vs **Slow Release** repositories. Collects GitHub metrics via GraphQL/REST APIs, analyzes code quality with SonarQube (Docker), and persists data to PostgreSQL.

**Critical Classification Logic:**

- **Rapid**: 5-35 days average between releases + >19 releases + >19 contributors
- **Slow**: >60 days average between releases + >19 releases + >19 contributors
- All repos require: >50 stars, >50 forks

## Architecture: Two-Phase Modular Design

### Phase 1: Collection (`1_collect_repositories.py`)

- **Purpose**: Search GitHub, filter repositories, save to `repositories_dataset.json`
- **Key**: Avoids API re-calls; dataset is reusable for multiple analyses
- **Run**: `python 1_collect_repositories.py --rapid 50 --slow 50`

### Phase 2: Analysis (`2_analyze_sonarqube.py` or `analyze_csv_repos.py`)

- **Purpose**: Clone repos, run SonarScanner (Docker), extract metrics, update dataset
- **Parallelization**: `--workers 4` runs 4 repos simultaneously
- **Recovery**: `--skip-analyzed` resumes from failures
- **JSON Input**: `python 2_analyze_sonarqube.py --workers 4 --skip-analyzed`
- **CSV Input**: `python analyze_csv_repos.py --csv slow_release_repos.csv --workers 4`

**Why Modular?** Original monolithic script (`research_automation_script.py`) re-fetched GitHub data on every run. New system: collect once, analyze multiple times, handle failures gracefully.

## Critical File Patterns

### DatasetManager (`dataset_manager.py`)

Central persistence layer. **Always use this** instead of raw JSON/SQL. **Supports both JSON and CSV inputs with incremental analysis**:

```python
from dataset_manager import DatasetManager

# JSON mode
dm = DatasetManager("repositories_dataset.json")
dm.add_repository(repo_data)  # Auto-handles duplicates, timestamps
repos = dm.get_repositories(release_type='rapid', limit=10)

# CSV mode (auto-detected by .csv extension)
dm_csv = DatasetManager("slow_release_repos.csv")
repos = dm_csv.get_repositories(release_type='slow')
# Saves analysis to *_analyzed.csv
dataset = dm_csv.load_dataset()
dm_csv.save_dataset(dataset)  # Creates slow_release_repos_analyzed.csv
```

**CSV Format**: Expects columns: `owner,name,stars,forks,language,release_count,contributors,median_release_interval,release_type,reason`

**Incremental persistence**: When `_analyzed.csv` exists, loads from it instead of original CSV, preserving previous analyses. This enables:
- Resume after crashes with `--skip-analyzed`
- Analyze 100s of repos across multiple runs
- Never lose completed work

**Dual persistence**: JSON/CSV (portable, versionable) + PostgreSQL (optional, for BI queries). Table prefix: `research_*` to avoid SonarQube conflicts.

### GitHub API (`utils.py` - `GitHubAPI`)

- **GraphQL**: Batch queries for releases/PRs/issues (fewer API calls)
- **REST**: Repository search, contributor counts (pagination required)
- **Rate limiting**: Auto-waits when `X-RateLimit-Remaining: 0`, sleeps 2s between calls
- **Contributor counting trick**: Uses `Link` header pagination instead of fetching all pages

### SonarQube Integration

**Never install SonarScanner CLI locally.** Always use Docker:

```python
docker_cmd = [
    'docker', 'run', '--rm', '--network', 'host',
    '-v', f'{repo_dir}:/usr/src',
    'sonarsource/sonar-scanner-cli',
    '-Dsonar.projectKey=owner_name'
]
```

**Repository Size Limit**: Repositories larger than 2GB are automatically skipped to prevent resource exhaustion.

**Windows/Linux Compatibility**:

- Path normalization: `os.path.abspath()` works on both platforms
- File cleanup: Enhanced `handle_remove_readonly()` handles permissions on both systems
- Temp directories: Uses `tempfile.gettempdir()` (Windows: `%TEMP%`, Linux: `/tmp`)

```python
def handle_remove_readonly(func, path, exc):
    """Handles file permissions on Windows and Linux"""
    if not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
        func(path)
    else:
        raise

shutil.rmtree(temp_dir, onerror=handle_remove_readonly)
```

**Size Check**: Repositories are checked after cloning:

```python
repo_size = sum(os.path.getsize(f) for f in Path(repo_dir).rglob('*'))
if repo_size > 2 * 1024**3:  # 2GB limit
    return None  # Skip analysis
```

## Environment Setup (`.env`)

```bash
GITHUB_TOKEN=ghp_...        # Required for collection
SONAR_TOKEN=sqa_...         # Required for analysis
SONAR_HOST=http://localhost:9000
DB_HOST=localhost           # Optional (auto-disables if unavailable)
```

**Startup sequence:**

1. `docker-compose up -d` (starts SonarQube + PostgreSQL)
2. Configure SonarQube admin password at http://localhost:9000
3. Generate token: Administration → Security → Users → Tokens
4. Run collection → analysis

## Common Workflows

### Incremental Research Collection (JSON)

```bash
# Initial dataset
python 1_collect_repositories.py --rapid 50 --slow 50

# Expand later
python 1_collect_repositories.py --rapid 100 --slow 100  # Adds more

# Analyze only new repos
python 2_analyze_sonarqube.py --skip-analyzed --workers 4
```

### Analyzing Pre-Collected CSV Data

```bash
# Analyze all repos from CSV
python analyze_csv_repos.py --csv slow_release_repos_20251115_053707.csv --workers 4

# Analyze first 10 repos only (testing)
python analyze_csv_repos.py --csv slow_release_repos.csv --workers 2 --limit 10

# Resume after failures
python analyze_csv_repos.py --csv slow_release_repos.csv --workers 4 --skip-analyzed

# Output: Creates slow_release_repos_20251115_053707_analyzed.csv
```

### Troubleshooting Failed Analysis

```python
# Check pending analyses
from dataset_manager import DatasetManager
dm = DatasetManager()
dataset = dm.load_dataset()
pending = [r for r in dataset['repositories']
           if not r.get('sonarqube_analyzed', False)]
print(f"{len(pending)} repos pending")

# Re-analyze specific type
python 2_analyze_sonarqube.py --type rapid --limit 10
```

### Database-Free Mode

System auto-detects PostgreSQL availability. If DB connection fails, continues with JSON-only persistence (warns but doesn't crash).

## Performance Patterns

### API Rate Limits

- GitHub: 5000 requests/hour (authenticated)
- Script auto-sleeps when limit hit (checks `X-RateLimit-Reset` header)
- Collection of 100 repos ≈ 200-300 API calls (30-60 min)

### Parallelization Strategy (`2_analyze_sonarqube.py`)

- Each worker: clone → size check → scan → extract → cleanup
- Temp dirs: `%TEMP%\repos_analise\owner_name_{worker_id}` (Windows) or `/tmp/repos_analise/owner_name_{worker_id}` (Linux)
- **Memory**: ~500MB per worker (cloned repo)
- **Size Limit**: 2GB per repository (automatically skipped if larger)
- **Optimal**: 4 workers on 8GB RAM, SSD

### Progress Tracking

`ProgressTracker` class provides organized output for parallel runs:

```
[15/100] ✅ kubernetes/kubernetes - Concluído
[████████████░░░░░] 75% | ✅ 70 | ❌ 5 | ETA: 12.3min
```

## Testing Guidelines

Run verification tests before major changes:

```bash
python tests/test_filters.py       # Validates classification logic
python tests/test_db_connection.py # PostgreSQL connectivity
python tests/test_sonar_docker.py  # Docker + SonarQube setup
```

## Anti-Patterns to Avoid

❌ **Don't** modify `repositories_dataset.json` manually (breaks timestamps)  
✅ **Do** use `DatasetManager` methods

❌ **Don't** run SonarScanner without Docker (dependencies nightmare)  
✅ **Do** use provided Docker command pattern

❌ **Don't** delete repos from dataset (breaks research continuity)  
✅ **Do** mark as `sonarqube_analyzed: false` to re-analyze

❌ **Don't** commit `.env` with real tokens  
✅ **Do** use `.env.example` template

## Key Metrics Explained

### Release Type Classification

```python
avg_interval = calculate_avg_release_interval(releases)
if 5 <= avg_interval <= 35: return 'rapid'
if avg_interval > 60: return 'slow'
return 'unclassified'  # Rejected
```

### SonarQube Metrics Mapping

**All 13 metrics saved to CSV:**

- `bugs`: Number of bug issues
- `vulnerabilities`: Number of vulnerability issues
- `code_smells`: Number of code smell issues
- `sqale_index`: Technical debt in minutes
- `coverage`: Test coverage percentage
- `duplicated_lines_density`: Percentage of duplicated lines
- `ncloc`: Number of lines of code (non-comment, non-blank)
- `complexity`: Cyclomatic complexity
- `cognitive_complexity`: Cognitive complexity score
- `reliability_rating`: Reliability rating (A-E)
- `security_rating`: Security rating (A-E)
- `sqale_rating`: Maintainability rating (A-E)
- `alert_status`: Quality Gate status (OK/ERROR)

## File Organization

```
1_collect_repositories.py    # Phase 1: GitHub collection (creates JSON)
2_analyze_sonarqube.py       # Phase 2: SonarQube analysis (JSON input)
analyze_csv_repos.py         # Phase 2: SonarQube analysis (CSV input)
dataset_manager.py           # Central data persistence (JSON/CSV support)
utils.py                     # GitHubAPI, SonarQubeAPI classes
docker-compose.yml           # SonarQube + PostgreSQL services
repositories_dataset.json    # Primary dataset (generated by script 1)
*_analyzed.csv              # Analysis results (generated from CSV input)
```

Legacy file: `research_automation_script.py` (deprecated monolith, kept for reference)

## Quick Reference Commands

```bash
# Full workflow (JSON-based)
python 1_collect_repositories.py --rapid 100 --slow 100 --max-search 2000
python 2_analyze_sonarqube.py --workers 4

# Analyze from CSV (common for pre-collected data)
python analyze_csv_repos.py --csv slow_release_repos.csv --workers 4 --limit 50

# Export results
python -c "from dataset_manager import DatasetManager; DatasetManager().export_to_csv('results.csv')"

# Check dataset status (works with both JSON and CSV)
python -c "from dataset_manager import DatasetManager; DatasetManager('slow_release_repos.csv').print_statistics()"

# Docker management
docker-compose up -d          # Start services
docker-compose logs sonarqube # Check SonarQube logs
docker-compose down           # Stop all
```

---

**Critical for AI agents**: When adding features, maintain the two-phase separation. Collection scripts should never clone repos; analysis scripts should never search GitHub. DatasetManager is the only source of truth for repository state.
