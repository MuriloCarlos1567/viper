# Viper

CLI para orquestrar repositorios locais com Docker Compose.

## Instalacao

Depois de instalar, execute diretamente:

```bash
viper --help
```

### Opcao recomendada: `pipx`

#### macOS

```bash
brew install pipx
pipx ensurepath
pipx install viper
```

#### Windows (PowerShell)

```powershell
python -m pip install --user pipx
python -m pipx ensurepath
pipx install viper
```

#### Linux

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
pipx install viper
```

## Instalacao local deste repositorio

### macOS/Linux

```bash
./scripts/install.sh
```

### Windows (PowerShell)

```powershell
./scripts/install.ps1
```

## mock server local para APIs

Crie um arquivo `viper.mock.yaml` na raiz do projeto:

```yaml
server:
  port: 4010
routes:
  - method: GET
    path: /users
    status: 200
    body:
      users:
        - id: 1
          name: "Ada"
  - method: POST
    path: /auth/login
    status: 401
    body:
      error: "credenciais_invalidas"
```

Comandos:

```bash
viper mock validate
viper mock up --name localdev
viper mock status --name localdev
viper mock logs --name localdev
viper mock down --name localdev
```

Notas:
- Porta padrao: `4010` (pode sobrescrever com `viper mock up --port 4020`).
- DNS interno entre containers: `http://viper-mock:<porta>`.
- Rota nao mapeada retorna `404`.

## Vinculo de biblioteca local (sem mexer no Poetry)

Voce pode apontar uma API para uma biblioteca local dentro de `repos/` sem alterar `pyproject.toml`:

```bash
viper link add --api minha-api --lib minha-lib --subpath src
viper link list
viper link remove --api minha-api --lib minha-lib --subpath src
```

Como funciona:
- O Viper monta `repos/<lib>/<subpath>` no container da API por volume.
- O Viper injeta `PYTHONPATH` com prioridade para a biblioteca local.
- Isso e aplicado automaticamente no `viper up`.

Notas:
- `--subpath` padrao: `src`.
- Use `--subpath .` para montar a raiz da biblioteca.
- Se a API estiver rodando no `link add/remove`, o Viper recria apenas esse servico para aplicar a mudanca.

## Publicacao no PyPI

1. Atualize `version` em `pyproject.toml`.
2. Gere os artefatos:

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
```

3. Publique:

```bash
python -m twine upload dist/*
```
