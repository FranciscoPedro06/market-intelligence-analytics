# market-intelligence-analytics

Parte do **Market Intelligence Ecosystem** · Produto de dados: *Flight Intelligence Platform*.

## Papel neste ecossistema
Camada de **transformação (Analytics)**: transforma o dado bruto de voo (**C1**) no
**indicador de pontualidade** (**C2**) por rota direcional × companhia × mês. Todo o
cálculo (mapa ICAO→IATA, janela de 15 min, denominador, taxa) é resolvido aqui — a API
apenas serve o número pronto (princípio RT5: a API não calcula nada).

## Escopo (Sprint 1 — Walking Skeleton)
Uma métrica (**pontualidade**), arquivos planos. Sem banco, framework ou orquestrador
(deferido, RT6). Python 3, **somente stdlib** (`csv`, `json`, `datetime`, `argparse`).

## Contratos (fonte da verdade: repo de governança do ecossistema)
- **Entrada — C1 `v1.0.0`**: registro bruto de voo (CSV). Colunas de origem VRA + colunas
  de proveniência (`source_file`, `file_sha256`, `source_year_month`, …). Camada bruta:
  valores como publicados, sem re-mapeamento semântico.
- **Saída — C2 `v1.2.0`**: `output/c2_punctuality.json`, documento com **envelope**
  `{contract, contract_version, records[]}`; um registro por
  **(`route_id` direcional × `airline_icao` × `reference_month`)**. Cada registro carrega
  dimensões (incl. `route_pair_id` não-direcional e IATA derivado), medidas, proveniência
  da métrica e linhagem C1.

  ```json
  { "contract": "C2", "contract_version": "v1.2.0", "records": [ { "route_id": "SBSP-SBRJ", "…": "…" } ] }
  ```
- **Métrica — pontualidade `v1.1.0`**: pontual ⟺ (`actual_arrival − scheduled_arrival`) ≤ 15 min
  (inclusivo; antecipado = pontual). Base = chegada. Denominador = `REALIZADO` com
  `actual_arrival` **e** `scheduled_arrival` não nulos.

> ✅ **C2 `v1.2.0` ratificado pelo Sprint Lead em 2026-08-31 (ADR-0002 / GOV-003).**
> Bump aditivo **de documento**: o esquema do registro é o mesmo do `v1.1.0`; o que muda é o
> envelope, que faz o artefato declarar qual contrato e qual versão carrega. Antes disso a API
> não conseguia confirmar a versão do que consumia. `analytics_version` passa a `1.2.0` — a
> forma da saída mudou, e o determinismo é garantido *por versão da lógica*.

> ✅ **C2 `v1.1.0` e pontualidade `v1.1.0` ratificados pelo Sprint Lead em 2026-07-25**
> e vigentes em `docs/ecosystem/contracts.md` e `docs/product/metrics-definitions.md`.
> A emenda — aditiva, nascida do C1 real — introduziu `flights_operated_missing_schedule`:
> sem `scheduled_arrival` a pontualidade é *indefinida*, e mantê-la no denominador contava o
> voo como atrasado, inventando um fato. Histórico em
> [`docs/CONTRACT-CHANGE-REQUEST.md`](docs/CONTRACT-CHANGE-REQUEST.md).

Contratos, princípios e governança:
https://github.com/FranciscoPedro06/Market-Intelligence-Ecosystem

## Medidas C2 produzidas (todas as do contrato)
| Campo | Regra |
|---|---|
| `flights_operated` | **Denominador**: `REALIZADO` **E** `actual_arrival` **E** `scheduled_arrival` não nulos. |
| `flights_on_time` | **Numerador**: subconjunto com `(actual_arrival − scheduled_arrival) ≤ 15 min`. |
| `on_time_rate` | `on_time / operated`; **`null` se operated = 0** (nunca 0/0); precisão plena. |
| `flights_cancelled` | Transparência: `CANCELADO` (fora do denominador). |
| `flights_not_reported` | Transparência: `NÃO INFORMADO` (fora do denominador). |
| `flights_operated_missing_arrival` | Transparência: `REALIZADO` sem `actual_arrival`. |
| `flights_operated_missing_schedule` | Transparência: `REALIZADO` sem `scheduled_arrival` — pontualidade **indefinida**, nunca contada como atraso. |
| `flights_source_total` | `operated + missing_arrival + missing_schedule + cancelled + not_reported` — fecha a reconciliação; nenhuma linha C1 some. |

Também preenche: `route_id`/`route_pair_id`, `origin/dest_icao/iata`, `airline_icao/name`
(`null` se ausente, nunca inventado), `reference_month`, `timezone`; proveniência da métrica
(`metric_id`, `metric_version`, `on_time_basis=arrival`, `on_time_threshold_minutes=15`, …);
linhagem C1 (`c1_contract_version`, `source_year_month`, `source_lineage[]`); e auditoria
(`analytics_version`, `computed_at_utc`).

## Determinismo
Mesmo input C1 + mesmo `analytics_version` → C2 idêntico em **todos** os campos exceto
`computed_at_utc` (metadado de auditoria). Ordenação estável dos registros por (`route_id`, `airline_icao`, `reference_month`);
`source_lineage` ordenado; sem floats dependentes de ordem.

## Como executar
```bash
# 1. trazer o C1 produzido pelo Collector (input/ é diretório de trabalho, não versionado)
cp ../market-intelligence-collector/output/c1_flights.csv input/c1_flights.csv

# padrão: input/c1_flights.csv -> output/c2_punctuality.json
python src/analyze.py

# explícito
python src/analyze.py --input input/sample_c1.csv --output output/c2_punctuality.json

# saída bit-a-bit reprodutível (fixa o único campo não determinístico)
python src/analyze.py --input input/sample_c1.csv --computed-at 2026-07-24T00:00:00Z
```

## Estado atual (Fase 2 — integração)
Processado o **C1 real** do Collector: **9.527 linhas** (CGH↔SDU, abr–jun/2023,
3 arquivos VRA) → **25 registros C2**. Reconciliação fecha em 9.527 (nenhuma linha perdida)
e a recontagem independente bate em 25/25 grupos. Evidência completa —
incluindo conferência à mão e verificação de determinismo — em
[`RECONCILIATION.md`](RECONCILIATION.md).

## Amostra sintética de teste
`input/sample_c1.csv` é **dado sintético de teste** (não real; `file_sha256` fictício
`deadbeef…`), conforme ao contrato C1. Cobre cada caminho de classificação — limiar
inclusivo, antecipado, cancelado, não informado e os dois casos de ausência — como
regressão da regra, independente do dado real.

## Estrutura
```
src/analyze.py                    # produtor C2 (stdlib only)
input/sample_c1.csv               # fixture sintético (versionado)
input/c1_flights.csv              # C1 real do Collector (não versionado)
output/                           # C2 gerado (ignorado pelo git)
docs/CONTRACT-CHANGE-REQUEST.md   # emenda C2 v1.1.0 p/ o Sprint Lead
```
