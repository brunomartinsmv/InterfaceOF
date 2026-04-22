# OpenFOAM Campaign v0.2 — Scaffold inicial

Scaffold inicial de uma aplicação desktop em Python para automação de campanhas paramétricas no OpenFOAM.

## Novidades desta revisão

- ativação de ambiente OpenFOAM por:
  - nenhum
  - alias/função do `~/.bashrc`
  - `source /caminho/.../etc/bashrc`
- execução interna baseada em três grupos de comandos:
  - setup commands
  - stage/run commands
  - post commands
- geração de um script temporário por comando
- log individual por comando em `case_xxx/logs`
- monitoramento aponta o **log ativo** da run corrente
- visualizador de resíduos agora associa cada residual ao arquivo de log da run correspondente
- suporte básico a reexecução por estágios reaplicando parâmetros via cache de templates

## Observações

- Em WSL, o padrão automático usa `bash`.
- Em Windows, o padrão automático usa `wsl bash`.
- Para alias/função, o runner usa shell interativo.
- Para `source command`, o runner usa shell não interativo.

## Instalação recomendada no WSL

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python3 main.py
```


- Requer `matplotlib` para o gráfico de resíduos na aba Monitoramento.
