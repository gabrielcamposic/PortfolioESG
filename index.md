Modelo Portfolio ESG: Investimento Consciente e Rentável em Python
Visão Geral: Alinhando Lucro e Propósito ESG
No cenário de investimentos atual, a integração de fatores Ambientais, Sociais e de Governança (ESG) é crucial. No entanto, o desafio reside em encontrar o equilíbrio entre métricas ESG publicly disponíveis e a rentabilidade desejada.

O Modelo Portfolio ESG é um projeto pessoal desenvolvido para investigar se é possível usar ações de empresas brasileiras para incentivar companhias genuinamente orientadas a ESG, ao mesmo tempo em que se busca otimizar o retorno financeiro. Meu objetivo é democratizar a análise aprofundada de carteiras com foco em sustentabilidade, governança e impacto social, combinando solidez teórica e aplicação prática.

Como Funciona: Inteligência Quantitativa Aplicada
Nosso modelo opera de forma autônoma para construir e otimizar carteiras de ações.

Coleta de Dados: O modelo baixa dados históricos de empresas da B3 (Bolsa de Valores do Brasil) através do Yahoo Finance, a partir de uma lista pré-selecionada de ações que compõem carteiras ESG relevantes do mercado (XP, S&P, Moody's, entre outras). Para garantir a coleta contínua, são utilizadas proxies que evitam bloqueios.
Organização e Análise: As informações são organizadas individualmente por ação e consolidadas em uma base de dados robusta.
Otimização da Carteira: Utilizando algoritmos avançados, como Simulação de Monte Carlo e Algoritmos Genéticos, o modelo seleciona a combinação ideal de ações e seus respectivos pesos na carteira que resultará no melhor Sharpe Ratio (medida de retorno ajustada ao risco).
Simulação Histórica: A melhor combinação encontrada é então avaliada através de simulações históricas, permitindo visualizar seu desempenho ao longo do tempo.
Funcionalidades Principais
O Modelo Portfolio ESG oferece um conjunto de ferramentas para análise e monitoramento de carteiras:

Coleta Robusta de Dados: Baixa dados históricos do Yahoo Finance com suporte a proxies para evitar bloqueios.
Organização e Consolidação de Dados: Estrutura informações individuais de ações e constrói uma base de dados consolidada.
Cálculo de Sharpe Ratio: Calcula o Sharpe Ratio para ações individuais e para cada conjunto simulado de carteiras.
Otimização Inteligente de Portfólio: Apresenta a melhor combinação de ações e pesos, maximizando o Sharpe Ratio através de Monte Carlo e Algoritmos Genéticos.
Análise Histórica de Desempenho: Simula e exibe o valor histórico da carteira otimizada.
Ferramentas de Controle de Performance: Inclui mecanismos para monitoramento contínuo do desempenho da carteira.
Interface de Monitoramento: Conjunto de páginas HTML interativas para visualização e análise de dados.
Tecnologia e Desenvolvimento
O Modelo Portfolio ESG é desenvolvido em Python, com uma interface de monitoramento em HTML e JavaScript.

Linguagens e Bibliotecas Principais:

Python: pandas, numpy, matplotlib, yfinance.
HTML & JavaScript: cdn.jsdelivr.net/npm/chart.js, cdn.jsdelivr.net/npm/date-fns@^2, cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@^2/dist/chartjs-adapter-date-fns.bundle.min.js, cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js, cdn.jsdelivr.net/npm/papaparse@5.3.0/papaparse.min.js.
Desenvolvimento Acelerado por IA:

Este projeto foi significativamente otimizado e acelerado pela colaboração estratégica com ferramentas de Inteligência Artificial, como Gemini Code Assistant, ChatGPT e Pilot. O uso de IAs foi fundamental para a otimização de código, validação de algoritmos e exploração de abordagens, permitindo focar na aplicação da teoria financeira e na evolução contínua do modelo.
Status e Futuro do Projeto (Open Source)
O Modelo Portfolio ESG atingiu uma fase de estabilidade e atualmente estou focado em ajustar parâmetros e avaliar a evolução da composição da carteira ao longo do tempo.

Como parte da evolução futura, pretendo desenvolver modelos regressivos para construir métricas inovadoras ESG baseadas em dados públicos. A regressão será utilizada para selecionar as ações candidatas que comporão a carteira, aprimorando ainda mais a inteligência do modelo.

Este é um projeto open source, disponível publicamente para a comunidade. A premissa é que a análise aprofundada de carteiras ESG deve ser acessível a todos, fomentando o benefício coletivo e o desenvolvimento colaborativo de investimentos mais conscientes e sustentáveis.

Acesse o Código e Conecte-se
O código completo do Modelo Portfolio ESG está disponível no meu repositório GitHub. Sinta-se à vontade para explorar, usar e contribuir!

Repositório GitHub: https://github.com/gabrielcamposic/PortfolioESG
Conecte-se comigo no LinkedIn: https://www.linkedin.com/in/gabrielcampos
