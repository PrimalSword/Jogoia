# Orbis Node

Fundação do **Orbis Link** e do **Orbis Trade Forex** para o Itautec/Alpine.

## Objetivo do primeiro marco

- serviço HTTP local extremamente leve, sem frameworks;
- autenticação por token;
- leitura remota de estado do nó;
- fila de sinais para o aplicativo Android;
- scanner Forex desacoplado da fonte de cotações;
- persistência SQLite dos sinais;
- replay CSV determinístico para testes;
- operação somente informativa, sem envio de ordens;
- foco inicial em M1 e M5.

## Decisão técnica importante

O MetaTrader 5 não será instalado diretamente no Itautec nesta fase. No Linux ele depende do Wine, e a instalação oficial não contempla Alpine. Para um Atom N455 com 2 GB de RAM, isso adicionaria peso e fragilidade desnecessários.

A arquitetura separa a coleta de preços do motor de análise. Assim, podemos conectar depois:

1. uma API gratuita ou conta demonstrativa de corretora;
2. um pequeno coletor MT5 executado em outro computador Windows;
3. replay de CSV para backtest e calibração.

## Estrutura

```text
orbis-node/
├── config.example.json
├── orbis_link.py
├── orbis_provider.py
├── orbis_storage.py
├── orbis_trade.py
├── replay.py
├── test_replay.py
└── README.md
```

## Execução local

```sh
cd orbis-node
cp config.example.json config.json
python3 orbis_link.py
```

O serviço escuta, por padrão, em `0.0.0.0:8765`.

## Replay CSV

O CSV deve conter, no mínimo:

```text
timestamp,open,high,low,close
```

Também aceita `volume` e `spread_pips`.

Exemplo de execução sem gravar no banco:

```sh
python3 replay.py candles.csv --symbol EUR_USD --timeframe 1 --dry-run
```

Execução gravando os sinais no SQLite:

```sh
python3 replay.py candles.csv --symbol EUR_USD --timeframe 1
```

O provedor produz janelas progressivas de candles, executa o mesmo motor usado pela API e grava apenas sinais que atendem aos critérios configurados.

## Testes

```sh
python3 -m unittest test_replay.py
```

## Endpoints iniciais

- `GET /health` — disponibilidade do serviço;
- `GET /api/v1/status` — CPU, memória, uptime, IP, versão e resumo do Trade;
- `GET /api/v1/trade/signals?limit=50` — sinais persistidos;
- `GET /api/v1/trade/summary` — estatísticas do banco;
- `POST /api/v1/trade/scan` — executa uma varredura usando candles enviados pelo cliente.

Todos os endpoints em `/api/` exigem:

```text
Authorization: Bearer SEU_TOKEN
```

## Segurança

O serviço não expõe shell. Reiniciar, desligar e atualizar serão implementados como ações previamente autorizadas, com confirmação e registro de auditoria. O acesso pela internet será feito por VPN privada, preferencialmente Tailscale ou WireGuard, nunca por porta aberta diretamente no roteador.

## Próximos passos

1. avaliação automática dos sinais abertos contra candles posteriores;
2. backtest com spread, slippage e custos;
3. adaptador para uma fonte gratuita ou conta demo;
4. aplicativo Android para pareamento, status e notificações.
