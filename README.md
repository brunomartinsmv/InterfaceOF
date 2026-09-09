# OpenFOAM Campaign v0.3 — Primeiro Commit

Versão 0.3 do conjunto de códigos para uma interface visual com automatização de parâmetros para simulações no OpenFOAM. 

A elaboração da sintaxe de partes do código, correção de bugs e refinamento do código contaram com o apoio de ferramentas de inteligência artificial generativa, modelo GPT-5.4 Thinking, da OpenAI. A concepção da ferramenta, definição da lógica do programa, testes, correções e a validação final permaneceram sob responsabilidade dos autores.

Ferramenta não oficial para automação de simulações no OpenFOAM. Não afiliada nem endossada pelos detentores da marca OPENFOAM®



## Novidades desta revisão

- automatização per meio de alteração das variáveis de interesse por: 
```
{[of_var:Nome_da_Variavel]}
```
- execução interna baseada em três grupos de comandos:
  - setup commands
  - stage/run commands
  - post commands
- geração de um script temporário por comando
- log individual por comando em `case_xxx/logs`
- monitoramento da run corrente
- visualizador de resíduos agora associa cada residual ao arquivo de log da run correspondente

## Observações

- Hosts suportados: macOS e Linux nativos, além de Windows + WSL.
- Testado originalmente no Windows WSL com OpenFOAM 13. Outras versões provavelmente funcionam se `blockMesh`/`foamRun` estiverem no ambiente.
- Sem seletor de versão na interface. Com várias instalações, use o campo de ativação na aba Configuração ou faça o source da versão desejada antes de abrir o `main.py`.
- No macOS, `bash -lc` passa pelo `path_helper` e costuma perder o PATH do OpenFOAM. A interface usa `bash -c` e herda o ambiente do processo, ou carrega o `etc/bashrc` se a ativação estiver ligada.

## Instalação no macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python3 main.py
```

Esta GUI não instala o OpenFOAM. No Mac, compile ou instale o OpenFOAM à parte e informe o source na aba Configuração, por exemplo:

```bash
source ~/OpenFOAM/OpenFOAM-13/etc/bashrc
```

Depois use Verificar ambiente. O ParaView, se estiver em `/Applications/ParaView*.app`, é localizado sem precisar estar no PATH.

## Instalação recomendada no WSL

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python3 main.py
```


