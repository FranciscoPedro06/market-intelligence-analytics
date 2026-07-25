# RECONCILIATION — conferência manual (AC4)

> **Dado sintético de teste**, não real. Fixture: `input/sample_c1.csv`
> (`file_sha256` fictício `deadbeef…`, `source_year_month = 2023-06`).
> Objetivo: reproduzir à mão os contadores e a `on_time_rate` do C2 e comparar com a saída
> de `src/analyze.py`, validando a definição `pontualidade v1.0.0` enquanto o C1 real não
> está disponível (Fase 1).

## Regra aplicada (métrica pontualidade v1.0.0)
- **Base:** chegada. Pontual ⟺ `(actual_arrival − scheduled_arrival) ≤ 15 min` (inclusivo; antecipado = pontual).
- **Denominador (`flights_operated`):** `flight_status = REALIZADO` **E** `actual_arrival` não nulo.
- **Numerador (`flights_on_time`):** subconjunto do denominador que satisfaz a regra dos 15 min.
- **`on_time_rate` = on_time / operated**, `null` se operated = 0.
- **Excluídos do denominador, contados à parte:** `CANCELADO`, `NÃO INFORMADO`, `REALIZADO` sem chegada.
- **`flights_source_total` = operated + missing_arrival + cancelled + not_reported** (nenhuma linha some).

## Linhas do fixture (9 no total)

### Grupo A — `route_id = SBSP-SBRJ` (CGH→SDU), `airline_icao = TAM`, `2023-06`

| Voo | status | sched_arr | actual_arr | atraso (min) | classificação |
|---|---|---|---|---|---|
| 3001 | REALIZADO | 09:00 | 09:10 | +10 | operado, **pontual** |
| 3002 | REALIZADO | 09:00 | 09:15 | +15 | operado, **pontual** (limiar inclusivo) |
| 3003 | REALIZADO | 09:00 | 09:16 | +16 | operado, atrasado |
| 3004 | REALIZADO | 09:00 | 08:50 | −10 | operado, **pontual** (antecipado) |
| 3005 | CANCELADO | 09:00 | — | — | cancelado |
| 3006 | NÃO INFORMADO | 09:00 | — | — | não reportado |
| 3007 | REALIZADO | 09:00 | (vazio) | — | operado sem chegada (missing_arrival) |

Contagem à mão:
- `flights_operated` = 4 (3001, 3002, 3003, 3004)
- `flights_on_time` = 3 (3001, 3002, 3004; 3003 tem +16 → atrasado)
- `on_time_rate` = 3 / 4 = **0.75**
- `flights_cancelled` = 1 (3005)
- `flights_not_reported` = 1 (3006)
- `flights_operated_missing_arrival` = 1 (3007)
- `flights_source_total` = 4 + 1 + 1 + 1 = **7** (= linhas do grupo)

### Grupo B — `route_id = SBRJ-SBSP` (SDU→CGH), `airline_icao = GLO`, `2023-06`

| Voo | status | sched_arr | actual_arr | atraso (min) | classificação |
|---|---|---|---|---|---|
| 4001 | REALIZADO | 11:00 | 11:20 | +20 | operado, atrasado |
| 4002 | REALIZADO | 11:00 | 11:05 | +5 | operado, **pontual** |

Contagem à mão:
- `flights_operated` = 2
- `flights_on_time` = 1 (4002; 4001 tem +20 → atrasado)
- `on_time_rate` = 1 / 2 = **0.5**
- contadores de transparência = 0
- `flights_source_total` = **2**

`route_pair_id` de ambos os grupos = `SBRJ-SBSP` (par ICAO ordenado) → a API somaria as duas
direções para a comparação ↔.

## Comparação com a saída do script
Comando: `python src/analyze.py --input input/sample_c1.csv --computed-at 2026-07-24T00:00:00Z`

| Grupo | operated | on_time | rate | cancelled | not_reported | missing_arr | source_total | à mão bate? |
|---|---|---|---|---|---|---|---|---|
| TAM SBSP-SBRJ | 4 | 3 | 0.75 | 1 | 1 | 1 | 7 | ✅ |
| GLO SBRJ-SBSP | 2 | 1 | 0.5 | 0 | 0 | 0 | 2 | ✅ |

Total de linhas C1 lidas = 9 = 7 + 2 → nenhuma linha perdida (o `assert` interno de
`flights_source_total == linhas_do_grupo` também garante isso em runtime).

**Determinismo verificado:** duas execuções com `--computed-at` diferentes produzem saída
idêntica em todos os campos exceto `computed_at_utc`.
