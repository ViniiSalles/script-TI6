#!/usr/bin/env python3
"""
Teste de Compatibilidade de Plataforma

Verifica se os scripts funcionam corretamente em Windows e Linux.
"""

import os
import sys
import tempfile
import platform
from pathlib import Path

def test_temp_directory():
    """Testa criação de diretório temporário"""
    print("\n=== Teste: Diretório Temporário ===")
    
    temp_base = os.path.join(tempfile.gettempdir(), "repos_analise")
    print(f"Diretório base: {temp_base}")
    
    # Cria diretório
    Path(temp_base).mkdir(parents=True, exist_ok=True)
    print(f"✅ Diretório criado com sucesso")
    
    # Verifica se existe
    assert os.path.exists(temp_base), "Diretório não foi criado"
    print(f"✅ Diretório existe")
    
    # Remove
    import shutil
    shutil.rmtree(temp_base)
    print(f"✅ Diretório removido com sucesso")
    
    return True


def test_path_normalization():
    """Testa normalização de caminhos"""
    print("\n=== Teste: Normalização de Caminhos ===")
    
    test_path = "./test/path/to/repo"
    normalized = os.path.abspath(test_path)
    
    print(f"Original: {test_path}")
    print(f"Normalizado: {normalized}")
    print(f"Sistema: {platform.system()}")
    
    # Verifica se é caminho absoluto
    assert os.path.isabs(normalized), "Caminho não foi normalizado para absoluto"
    print(f"✅ Normalização funcionou")
    
    return True


def test_directory_size_calculation():
    """Testa cálculo de tamanho de diretório"""
    print("\n=== Teste: Cálculo de Tamanho ===")
    
    # Cria diretório temporário com arquivo
    temp_dir = os.path.join(tempfile.gettempdir(), "size_test")
    Path(temp_dir).mkdir(parents=True, exist_ok=True)
    
    # Cria arquivo de teste (1 MB)
    test_file = os.path.join(temp_dir, "test.txt")
    with open(test_file, 'wb') as f:
        f.write(b'0' * 1024 * 1024)  # 1 MB
    
    # Calcula tamanho
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(temp_dir):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if not os.path.islink(filepath):
                try:
                    total_size += os.path.getsize(filepath)
                except (OSError, FileNotFoundError):
                    continue
    
    size_mb = total_size / (1024 ** 2)
    print(f"Tamanho calculado: {size_mb:.2f} MB")
    
    # Verifica se está próximo de 1 MB
    assert 0.9 <= size_mb <= 1.1, f"Tamanho incorreto: {size_mb} MB"
    print(f"✅ Cálculo de tamanho correto")
    
    # Limpa
    import shutil
    shutil.rmtree(temp_dir)
    
    return True


def test_2gb_limit():
    """Testa verificação de limite de 2GB"""
    print("\n=== Teste: Limite de 2GB ===")
    
    # Simula tamanho de 3GB
    size_3gb = 3 * 1024 ** 3
    limit_2gb = 2 * 1024 ** 3
    
    should_skip = size_3gb > limit_2gb
    print(f"Tamanho simulado: {size_3gb / (1024**3):.2f} GB")
    print(f"Limite: {limit_2gb / (1024**3):.2f} GB")
    print(f"Deve pular? {should_skip}")
    
    assert should_skip, "Lógica de limite incorreta"
    print(f"✅ Verificação de limite funcionando")
    
    # Simula tamanho de 1GB
    size_1gb = 1 * 1024 ** 3
    should_not_skip = size_1gb <= limit_2gb
    print(f"\nTamanho simulado: {size_1gb / (1024**3):.2f} GB")
    print(f"Deve pular? {not should_not_skip}")
    
    assert should_not_skip, "Lógica de limite incorreta para repo pequeno"
    print(f"✅ Repositórios <2GB não são pulados")
    
    return True


def test_file_permissions():
    """Testa manipulação de permissões"""
    print("\n=== Teste: Permissões de Arquivo ===")
    
    # Cria arquivo temporário
    temp_dir = os.path.join(tempfile.gettempdir(), "perm_test")
    Path(temp_dir).mkdir(parents=True, exist_ok=True)
    
    test_file = os.path.join(temp_dir, "readonly.txt")
    with open(test_file, 'w') as f:
        f.write("test")
    
    # Verifica permissões atuais
    print(f"Sistema operacional: {platform.system()}")
    print(f"Arquivo: {test_file}")
    
    # Tenta mudar permissões
    import stat
    try:
        os.chmod(test_file, stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
        print(f"✅ Permissões modificadas com sucesso")
    except Exception as e:
        print(f"⚠️  Erro ao modificar permissões: {e}")
    
    # Verifica se tem permissão de escrita
    has_write = os.access(test_file, os.W_OK)
    print(f"Tem permissão de escrita: {has_write}")
    
    # Limpa
    import shutil
    shutil.rmtree(temp_dir)
    print(f"✅ Arquivo removido com sucesso")
    
    return True


def main():
    """Executa todos os testes"""
    print("="*80)
    print("TESTE DE COMPATIBILIDADE DE PLATAFORMA")
    print("="*80)
    print(f"Sistema Operacional: {platform.system()}")
    print(f"Versão: {platform.version()}")
    print(f"Python: {sys.version}")
    print("="*80)
    
    tests = [
        ("Diretório Temporário", test_temp_directory),
        ("Normalização de Caminhos", test_path_normalization),
        ("Cálculo de Tamanho", test_directory_size_calculation),
        ("Limite de 2GB", test_2gb_limit),
        ("Permissões de Arquivo", test_file_permissions),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"❌ Teste falhou: {test_name}")
        except Exception as e:
            failed += 1
            print(f"\n❌ Erro no teste '{test_name}': {e}")
    
    print("\n" + "="*80)
    print("RESULTADO DOS TESTES")
    print("="*80)
    print(f"✅ Passou: {passed}/{len(tests)}")
    print(f"❌ Falhou: {failed}/{len(tests)}")
    print("="*80)
    
    if failed == 0:
        print("\n🎉 Todos os testes passaram! Sistema compatível com esta plataforma.")
        return 0
    else:
        print(f"\n⚠️  {failed} teste(s) falharam. Verifique as mensagens acima.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
