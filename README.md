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

- Testado apenas para Windows WSL, 
- Testado apenas para a versão OpenFOAM 13 (mas provavelmente deve funcionar em outras versões).
- Versão ainda não conta com suporte de escolha de versão dentro da interface, em casos de multiplas versões instaladas, realizar o source da versão de interesse antes de rodar o main.py do projeto.

## Instalação recomendada no WSL

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python3 main.py
```


