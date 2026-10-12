# Changelog

Todas as alterações notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [Não publicado]

### Segurança
- **Validação de nomes de casos (Prevenção de Path Traversal)**: Sanitização e validação estrita da coluna `nome_do_caso` no `ParameterLoader` e `CaseBuilder` para bloquear caracteres maliciosos e sequências de diretório (`..`, `/`, `\`), impedindo criação de arquivos fora da pasta da campanha.
- **Encerramento seguro de processos e subprocessos**: Tratamento com blocos `try...finally` no `Runner` e escalonamento automático de `SIGTERM` para `SIGKILL` após timeout, garantindo que solvers OpenFOAM não continuem executando em segundo plano (processos órfãos) ao abortar ou fechar o aplicativo.

### Adicionado
- **Suíte de testes automatizados**: Adição de suíte completa de testes com `pytest` (mais de 40 testes unitários e de integração) cobrindo segurança, templates, marcadores, runners, loaders e integridade de arquivos do OpenFOAM.
- **Configuração de projeto e empacotamento**: Criação do arquivo `pyproject.toml` definindo dependências do projeto, requisitos mínimos do Python (>= 3.10) e parâmetros de execução do `pytest`.
- **Suporte a wrappers e flags de execução paralela**: Suporte a comandos wrappers e argumentos (por exemplo, `mpirun -np N`) no solver override sem sobrescrever indevidamente opções do comando.
- **Portabilidade nativa para macOS e Linux**: Suporte nativo para execução fora do ambiente Windows/WSL, com descoberta automática do executável `bash`, integração com o `etc/bashrc` do OpenFOAM e detecção automática de instalações do ParaView em `/Applications`.

### Modificado
- **Substituição de marcadores no `TemplateEngine`**: Transição para algoritmo de substituição literal baseado em tokens, protegendo comentários e caracteres especiais com escapes de barra invertida (`\`).
- **Validação pré-voo por caso**: No `PreflightValidator`, a validação de parâmetros passou a ser estrita e individual por caso (`per-case parameter validation`), refletindo variáveis faltantes diretamente na respectiva linha da auditoria.
- **Cálculo de métricas de campanha**: Ajuste do cálculo de tempo médio de execução (*mean wall clock time*) para considerar estritamente os casos executados com sucesso.
- **Ciclo de vida e limpeza de casos**: Limpeza de saídas e logs residuais ao repovoar, resetar ou alterar status na fila de casos.
- **Fechamento gracioso da janela principal**: Tratamento em `MainWindow.closeEvent` para aguardar a finalização segura de threads de workers ativos.

### Corrigido
- **Numeração monotônica de logs multi-estágio**: Correção da sobrescrita de logs em campanhas multi-estágio através de numeração incremental contínua em `case_xxx/logs`.
- **Preservação de configurações no `controlDict`**: Preservação do `endTime` e de comentários inline originais ao estender simulações entre estágios consecutivos.
- **Pré-visualização no monitor**: Eliminação de pontos e curvas fantasmas na visualização de gráficos do `MonitorTab` antes do início efetivo da corrida.
- **Mapeamento de configurações e sinais de interface**: Correção na associação do `ProjectConfig` na `MainWindow` e conexão correta de sinais do ParaView no `ExecutionTab`.
- **Robustez na leitura de CSVs**: Tratamento adequado para arquivos CSV vazios e validação de valores de tempo para rejeitar intervalos negativos.

## [0.3.0] - 2026-04-22

### Adicionado
- **Interface gráfica PySide6**: Interface de usuário desktop estruturada em quatro abas principais: Projeto, Execução, Monitoramento e Configurações.
- **Motor de templates e marcadores**: Suporte à parametrização de dicionários e arquivos de configuração OpenFOAM através de marcadores no formato `{[of_var:nome_da_variavel]}`.
- **Entrada de parâmetros via CSV**:
  - CSV primário (`primary_parameters.csv`) para definição de casos e variações paramétricas globais.
  - CSV secundário (`secondary_parameters.csv`) para suporte a estágios dinâmicos ao longo do tempo de simulação.
- **Orquestração de comandos OpenFOAM**:
  - Divisão da execução em três grupos de comandos: preparação (*setup*), execução de estágios (*stage/run*) e pós-processamento (*post*).
  - Criação de scripts temporários de execução por comando.
  - Armazenamento de logs individuais por comando no diretório `case_xxx/logs`.
- **Monitoramento em tempo real**:
  - Visualização de saída de terminal e status da simulação corrente.
  - Gráfico em tempo real de resíduos associado aos arquivos de log do solver em execução.
- **Integração com ParaView**: Inicialização integrada do ParaView para pós-processamento e inspeção dos casos gerados.
- **Metadados e reprodutibilidade**: Geração automática de metadados da campanha e resumo de execução (`reproducibility.json`).
- **Validação pré-voo (*Preflight Validator*)**: Verificação de consistência entre parâmetros informados e marcadores presentes no template antes do início dos cálculos.
- **Caso de exemplo**: Inclusão do caso demonstrativo `bubbleColumn` parametrizado.

[Não publicado]: https://github.com/brunomartinsmv/InterfaceOF/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/brunomartinsmv/InterfaceOF/releases/tag/v0.3.0
