# Especificação operacional travada — v0.2

## 1. Escopo

Aplicação desktop em Python para Windows + WSL/OpenFOAM, com:

- validação de templates OpenFOAM com marcadores;
- leitura de CSV primário e secundário;
- execução de campanhas em lote;
- execução opcional por estágios;
- monitoramento de terminal e resíduos em tempo real;
- geração de metadados e resumos de reprodutibilidade.

## 2. Marcadores

Formato oficial:

```text
{[of_var:nome_da_variavel]}
```

### Regras

- `nome_da_variavel` normalizado para minúsculas;
- aceitar letras, números e `_`;
- remover acentos;
- espaços e separadores viram `_`;
- qualquer marcador remanescente após substituição bloqueia a execução.

### Regex oficial

```regex
\{\[of_var:([a-z0-9_]+)\]\}
```

## 3. Normalização

Entrada `"Ângulo Contato"` -> `angulo_contato`

Passos:
1. strip;
2. lower;
3. remoção de acentos;
4. troca de caracteres não alfanuméricos por `_`;
5. colapso de múltiplos `_`;
6. remoção de `_` nas pontas.

## 4. CSV primário

### Estrutura

- `nome_do_caso` obrigatório;
- colunas `cfg__*` reservadas para configuração da ferramenta;
- demais colunas tratadas como parâmetros para marcadores.

### Exemplo

```csv
nome_do_caso,cfg__solver,cfg__n_processors,cfg__runner_mode,viscosidade,end_time
case_001,interFoam,8,internal,1e-6,0.5
```

## 5. CSV secundário

### Estrutura

- `nome_do_caso` obrigatório;
- `tempo` obrigatório;
- `variavel` obrigatório;
- `valor` obrigatório;
- `stage` opcional.

### Regras

- ordenação por `nome_do_caso`, `tempo`, ordem de leitura;
- tempos decrescentes por caso geram erro;
- múltiplas mudanças no mesmo `tempo` formam um único estágio lógico.

### Exemplo

```csv
nome_do_caso,tempo,variavel,valor,stage
case_001,0.5,angulo_contato,100,1
case_001,2.0,angulo_contato,120,2
case_001,2.0,viscosidade,1.5e-6,2
```

## 6. Regras de consistência

- marcador no caso sem valor correspondente: erro;
- valor vazio: erro;
- colunas que normalizam para o mesmo nome: erro;
- coluna extra no CSV sem marcador correspondente: aviso;
- marcadores em comentários são ignorados;
- relação marcador:csv é 1:1.

## 7. Execução

### Modos

- `internal`: pipeline interno controlado pela aplicação;
- `allrun`: execução do script `Allrun` como caixa-preta.

### Estratégia multiestágio

1. agrupar eventos por `tempo`;
2. definir `target_time`;
3. ajustar `endTime`;
4. rodar caso;
5. detectar último tempo salvo;
6. aplicar mudanças do próximo estágio;
7. reiniciar a partir de `latestTime`.

## 8. Estrutura de saída

```text
output/
└─ campaign_YYYY-MM-DD_HHMMSS/
   ├─ logs/
   │  ├─ campaign_...txt
   │  └─ campaign_...json
   ├─ campaign_summary.csv
   ├─ campaign_metrics.json
   ├─ campaign_config.json
   ├─ case_001/
   │  ├─ log_case_001.txt
   │  ├─ log_case_001.json
   │  ├─ case_info.json
   │  ├─ case_info.txt
   │  ├─ changes_log.txt
   │  ├─ residuals.csv
   │  └─ ... arquivos do caso
   └─ case_002/
```

## 9. Métricas obrigatórias

### Campanha
- total de casos;
- concluídos;
- falhos;
- interrompidos;
- tempo total;
- tempo médio por caso;
- total de estágios;
- total de alterações;
- total de marcadores encontrados;
- total de marcadores substituídos;
- total de resíduos extraídos.

### Caso
- duração;
- número de estágios;
- número de alterações;
- número de resíduos lidos;
- último tempo simulado;
- solver;
- número de processadores;
- status final.

## 10. Aba de validação

Antes de permitir execução, a UI deve mostrar:

- marcadores encontrados;
- arquivo onde cada marcador aparece;
- status de consistência;
- variáveis ausentes;
- colunas extras;
- duplicações por normalização;
- tempos inválidos;
- campos vazios.

## 11. Limitações assumidas na v0.2

- foco inicial em Windows + WSL/OpenFOAM;
- parser de resíduos básico;
- `Allrun` suportado, mas sem leitura semântica completa;
- estágios mais confiáveis no modo `internal`.

