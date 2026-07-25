# market-intelligence-analytics

Parte do **Market Intelligence Ecosystem** · Produto de dados: *Flight Intelligence Platform*.

## Papel neste ecossistema
Camada de **transformação (Analytics)**: transforma o dado bruto de voo (**C1**) no
**indicador de pontualidade** (**C2**) por rota direcional × companhia × mês. Todo o
cálculo (mapa ICAO→IATA, janela de 15 min, denominador, taxa) é resolvido aqui — a API
apenas serve o número pronto (princípio RT5: a API não calcula nada).

## Escopo (Sprint 1 — Walking Skeleton)
Uma métrica (**pontualidade**), arquivos planos. Sem banco, framework ou orquestrador
(deferido, RT6). Python 3, **somente stdlib** (`csv`, `json`, `hashlib`, `datetime`, `argparse`).

## Contratos (fonte da verdade: repo de governança do ecossistema)
- **Entrada — C1 `v1.0.0`**: registro bruto de voo (CSV). Colunas de origem VRA + colunas
  de proveniência (`source_file`, `file_sha256`, `source_year_month`, …). Camada bruta:
  valores como publicados, sem re-mapeamento semântico.
- **Saída — C2 `v1.0.0`**: `output/c2_punctuality.json`, array de registros, um por
  **(`route_id` direcional × `airline_icao` × `reference_month`)**. Cada registro carrega
  dimensões (incl. `route_pair_id` não-direcional e IATA derivado), medidas, proveniência
  da métrica e linhagem C1.
- **Métrica — pontualidade `v1.0.0`**: pontual ⟺ (`actual_arrival − scheduled_arrival`) ≤ 15 min
  (inclusivo; antecipado = pontual). Base = chegada. Denominador = `REALIZADO` com
  `actual_arrival` não nulo.

Contratos, princípios e governança:
https://github.com/FranciscoPedro06/Market-Intelligence-Ecosystem

## Medidas C2 produzidas (todas as do contrato)
| Campo | Regra |
|---|---|
| `flights_operated` | **Denominador**: `REALIZADO` **E** `actual_arrival` não nulo. |
| `flights_on_time` | **Numerador**: subconjunto com `(actual_arrival − scheduled_arrival) ≤ 15 min`. |
| `on_time_rate` | `on_time / operated`; **`null` se operated = 0** (nunca 0/0); precisão plena. |
| `flights_cancelled` | Transparência: `CANCELADO` (fora do denominador). |
| `flights_not_reported` | Transparência: `NÃO INFORMADO` (fora do denominador). |
| `flights_operated_missing_arrival` | Transparência: `REALIZADO` sem `actual_arrival`. |
| `flights_source_total` | `operated + missing_arrival + cancelled + not_reported` — fecha a reconciliação; nenhuma linha C1 some. |

Também preenche: `route_id`/`route_pair_id`, `origin/dest_icao/iata`, `airline_icao/name`
(`null` se ausente, nunca inventado), `reference_month`, `timezone`; proveniência da métrica
(`metric_id`, `metric_version`, `on_time_basis=arrival`, `on_time_threshold_minutes=15`, …);
linhagem C1 (`c1_contract_version`, `source_year_month`, `source_lineage[]`); e auditoria
(`analytics_version`, `computed_at_utc`).

## Determinismo
Mesmo input C1 → C2 idêntico em **todos** os campos exceto `computed_at_utc` (metadado de
auditoria). Ordenação estável dos registros por (`route_id`, `airline_icao`, `reference_month`);
`source_lineage` ordenado; sem floats dependentes de ordem.

## Como executar
```bash
# padrão: input/c1_flights.csv -> output/c2_punctuality.json
python src/analyze.py

# explícito
python src/analyze.py --input input/sample_c1.csv --output output/c2_punctuality.json

# saída bit-a-bit reprodutível (fixa o único campo não determinístico)
python src/analyze.py --input input/sample_c1.csv --computed-at 2026-07-24T00:00:00Z
```

## Amostra sintética de teste
`input/sample_c1.csv` é **dado sintético de teste** (não real; `file_sha256` fictício
`deadbeef…`), conforme ao contrato C1, para validar os contadores e a taxa enquanto o C1
real não está disponível na Fase 1. A conferência manual está em
[`RECONCILIATION.md`](RECONCILIATION.md).

## Estrutura
```
src/analyze.py        # produtor C2 (stdlib only)
input/sample_c1.csv   # fixture sintético (versionado)
output/               # C2 gerado (ignorado pelo git)
```
