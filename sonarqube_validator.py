#!/usr/bin/env python3
"""
Módulo de Validação e Sanitização para SonarQube

OBJETIVO:
Prevenir erros de análise causados por nomes de repositórios inválidos.
Protege contra caracteres especiais, tamanhos excessivos e formatos incorretos.

REGRAS DO SONARQUBE:
- Project key: máximo 400 caracteres
- Permitidos: letras, números, '-', '_', '.' e ':'
- NÃO permitidos: '/', '\', espaços, caracteres especiais
- Case sensitive

USO:
from sonarqube_validator import sanitize_project_key, validate_repository_data

project_key = sanitize_project_key(owner, name)
is_valid, errors = validate_repository_data(repo_data)
"""

import re
import logging
from typing import Tuple, List, Dict, Optional

# Configuração de logging
logger = logging.getLogger(__name__)


def sanitize_project_key(owner: str, name: str) -> str:
    """
    Cria um project_key válido para SonarQube a partir de owner/name
    
    PROTEÇÕES:
    1. Remove caracteres inválidos (/, \\, espaços, etc)
    2. Substitui múltiplos underscores por um só
    3. Remove underscores no início/fim
    4. Limita tamanho máximo
    5. Garante formato owner_name
    
    Args:
        owner: Nome do dono do repositório
        name: Nome do repositório
    
    Returns:
        Project key sanitizado e válido
    
    Examples:
        >>> sanitize_project_key("user/org", "repo-name")
        'user-org_repo-name'
        
        >>> sanitize_project_key("", "invalid")
        'unknown_invalid'
    """
    # 1. Validação básica
    if not owner or not isinstance(owner, str):
        owner = "unknown"
        logger.warning(f"Owner inválido, usando 'unknown'")
    
    if not name or not isinstance(name, str):
        name = "unnamed"
        logger.warning(f"Name inválido, usando 'unnamed'")
    
    # 2. Remove espaços e converte para string limpa
    owner = str(owner).strip()
    name = str(name).strip()
    
    # 3. Substitui caracteres inválidos por hífen ou underscore
    # CRÍTICO: '/' e '\' são PROIBIDOS no SonarQube
    owner = re.sub(r'[/\\]', '-', owner)  # Barras viram hífen
    name = re.sub(r'[/\\]', '-', name)
    
    # Remove outros caracteres especiais (mantém apenas: a-z, A-Z, 0-9, -, _, .)
    owner = re.sub(r'[^a-zA-Z0-9\-_.]', '_', owner)
    name = re.sub(r'[^a-zA-Z0-9\-_.]', '_', name)
    
    # 4. Remove múltiplos underscores/hífens consecutivos
    owner = re.sub(r'[-_]{2,}', '_', owner)
    name = re.sub(r'[-_]{2,}', '_', name)
    
    # 5. Remove underscores/hífens no início e fim
    owner = owner.strip('-_')
    name = name.strip('-_')
    
    # 6. Garante que não estão vazios após sanitização
    if not owner:
        owner = "unknown"
    if not name:
        name = "unnamed"
    
    # 7. Cria project_key no formato padrão
    project_key = f"{owner}_{name}"
    
    # 8. Limita tamanho (SonarQube aceita até 400 caracteres)
    if len(project_key) > 400:
        # Trunca mantendo proporção owner:name
        max_owner = min(len(owner), 150)
        max_name = min(len(name), 240)
        owner = owner[:max_owner]
        name = name[:max_name]
        project_key = f"{owner}_{name}"
        logger.warning(f"Project key muito longo, truncado para: {project_key}")
    
    return project_key


def validate_project_key(project_key: str) -> Tuple[bool, List[str]]:
    """
    Valida se um project_key está no formato correto do SonarQube
    
    Args:
        project_key: Chave a ser validada
    
    Returns:
        (is_valid, errors): Tupla com booleano e lista de erros
    """
    errors = []
    
    if not project_key:
        errors.append("Project key está vazio")
        return False, errors
    
    if not isinstance(project_key, str):
        errors.append(f"Project key deve ser string, recebido: {type(project_key)}")
        return False, errors
    
    # Tamanho máximo
    if len(project_key) > 400:
        errors.append(f"Project key muito longo: {len(project_key)} caracteres (máx: 400)")
    
    # Caracteres inválidos (CRÍTICO: sem barras!)
    invalid_chars = re.findall(r'[^a-zA-Z0-9\-_.:]+', project_key)
    if invalid_chars:
        errors.append(f"Caracteres inválidos encontrados: {set(invalid_chars)}")
    
    # Não deve conter barras (causa principal do bug)
    if '/' in project_key or '\\' in project_key:
        errors.append("CRÍTICO: Project key contém barras (/ ou \\) - PROIBIDO no SonarQube!")
    
    # Formato esperado: owner_name
    if '_' not in project_key:
        errors.append("Formato esperado: owner_name (deve conter underscore)")
    
    return len(errors) == 0, errors


def validate_repository_data(repo: Dict) -> Tuple[bool, List[str]]:
    """
    Valida dados completos de um repositório antes da análise
    
    Args:
        repo: Dicionário com dados do repositório
    
    Returns:
        (is_valid, errors): Tupla com booleano e lista de erros
    """
    errors = []
    
    # Campos obrigatórios
    required_fields = ['owner', 'name']
    for field in required_fields:
        if field not in repo or not repo[field]:
            errors.append(f"Campo obrigatório ausente ou vazio: {field}")
    
    # Valida tipos
    if 'owner' in repo and not isinstance(repo['owner'], str):
        errors.append(f"Campo 'owner' deve ser string, recebido: {type(repo['owner'])}")
    
    if 'name' in repo and not isinstance(repo['name'], str):
        errors.append(f"Campo 'name' deve ser string, recebido: {type(repo['name'])}")
    
    # Valida caracteres problemáticos
    if 'owner' in repo and repo['owner']:
        if '/' in repo['owner'] or '\\' in repo['owner']:
            errors.append(f"ATENÇÃO: Campo 'owner' contém barras: {repo['owner']}")
    
    if 'name' in repo and repo['name']:
        if '/' in repo['name'] or '\\' in repo['name']:
            errors.append(f"ATENÇÃO: Campo 'name' contém barras: {repo['name']}")
    
    # Valida tamanhos razoáveis
    if 'owner' in repo and len(str(repo['owner'])) > 200:
        errors.append(f"Campo 'owner' muito longo: {len(repo['owner'])} caracteres")
    
    if 'name' in repo and len(str(repo['name'])) > 200:
        errors.append(f"Campo 'name' muito longo: {len(repo['name'])} caracteres")
    
    return len(errors) == 0, errors


def fix_corrupted_csv_line(line_data: Dict) -> Optional[Dict]:
    """
    Tenta corrigir linha corrompida do CSV (como a linha 505)
    
    Detecta e corrige casos onde:
    - Campo owner está vazio
    - Dados estão desalinhados
    - Nome do projeto contém barras
    
    Args:
        line_data: Dicionário com dados da linha
    
    Returns:
        Dicionário corrigido ou None se não puder corrigir
    """
    # Caso 1: owner vazio mas full_name tem formato correto
    if not line_data.get('owner') and line_data.get('full_name'):
        full_name = line_data['full_name']
        
        if '/' in full_name:
            parts = full_name.split('/', 1)
            if len(parts) == 2:
                line_data['owner'] = parts[0]
                # Se name também está errado, corrige
                if not line_data.get('name') or '/' in line_data.get('name', ''):
                    line_data['name'] = parts[1]
                logger.info(f"Linha corrigida via full_name: {parts[0]}/{parts[1]}")
                return line_data
    
    # Caso 2: owner vazio mas name tem formato owner+name concatenado
    if not line_data.get('owner') and line_data.get('name'):
        name = line_data['name']
        
        # Tenta extrair owner/name de campos adjacentes
        if '/' in name:
            parts = name.split('/', 1)
            if len(parts) == 2:
                line_data['owner'] = parts[0]
                line_data['name'] = parts[1]
                logger.info(f"Linha corrigida via name: {parts[0]}/{parts[1]}")
                return line_data
        
        # Caso especial: name=wgcloutianshiyeben, full_name=wgcloud
        # Isso sugere que os campos estão todos trocados
        # Precisa de análise manual ou contexto extra
        # Podemos tentar buscar padrões conhecidos
        
        # Exemplo: se temos "wgcloud" e "tianshiyeben/wgcloud" em algum lugar
        # Tentativa de extrair do campo errado
        if line_data.get('full_name') and not '/' in line_data.get('full_name', ''):
            # full_name deveria ter /, se não tem, pode ser name
            potential_name = line_data.get('full_name')
            potential_owner = None
            
            # Tenta inferir owner do name mal formado
            # Ex: "wgcloutianshiyeben" pode ser "wgcloud" + "tianshiyeben"
            # Mas isso é muito específico
            
            logger.warning(f"Linha corrompida complexa, não foi possível corrigir automaticamente")
            logger.warning(f"  owner='{line_data.get('owner', '')}', name='{line_data.get('name', '')}', full_name='{line_data.get('full_name', '')}'")
    
    return None


def test_sanitization():
    """Testa casos problemáticos de sanitização"""
    test_cases = [
        # (owner, name, expected_key)
        ("user", "repo", "user_repo"),
        ("user/org", "repo", "user-org_repo"),
        ("user\\org", "repo", "user-org_repo"),
        ("", "repo", "unknown_repo"),
        ("user", "", "user_unnamed"),
        ("user@domain", "repo-name", "user_domain_repo-name"),
        ("user___", "___repo", "user_repo"),
        ("a" * 300, "b" * 300, None),  # Vai truncar
    ]
    
    print("🧪 Testando sanitização de project_key:\n")
    
    for owner, name, expected in test_cases:
        result = sanitize_project_key(owner, name)
        status = "✅" if (expected is None or result == expected) else "❌"
        print(f"{status} sanitize_project_key('{owner}', '{name}')")
        print(f"   → {result}")
        
        # Valida resultado
        is_valid, errors = validate_project_key(result)
        if not is_valid:
            print(f"   ⚠️  INVÁLIDO: {errors}")
        print()


if __name__ == "__main__":
    # Configura logging
    logging.basicConfig(level=logging.INFO)
    
    # Roda testes
    test_sanitization()
    
    # Testa caso específico do bug
    print("\n" + "="*80)
    print("🐛 TESTANDO CASO ESPECÍFICO DO BUG (linha 505)")
    print("="*80 + "\n")
    
    # Simula dados corrompidos
    corrupted = {
        'owner': '',
        'name': 'wgcloutianshiyeben',
        'full_name': 'tianshiyeben/wgcloud'
    }
    
    print("Dados corrompidos:")
    print(f"  owner: '{corrupted['owner']}'")
    print(f"  name: '{corrupted['name']}'")
    print(f"  full_name: '{corrupted['full_name']}'")
    
    # Tenta corrigir
    fixed = fix_corrupted_csv_line(corrupted)
    
    if fixed:
        print("\n✅ Linha corrigida:")
        print(f"  owner: '{fixed['owner']}'")
        print(f"  name: '{fixed['name']}'")
        
        # Cria project_key correto
        project_key = sanitize_project_key(fixed['owner'], fixed['name'])
        print(f"\n✅ Project key sanitizado: {project_key}")
        
        # Valida
        is_valid, errors = validate_project_key(project_key)
        if is_valid:
            print("✅ Project key VÁLIDO!")
        else:
            print(f"❌ Erros: {errors}")
    else:
        print("\n❌ Não foi possível corrigir automaticamente")
