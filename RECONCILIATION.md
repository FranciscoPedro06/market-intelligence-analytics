# RECONCILIATION — evidência de reconciliação (AC4 · AC5)

> **Dado oficial real** (AC1), não simulado. Input: `C1 v1.0.0` produzido pelo Collector
> (`market-intelligence-collector/output/c1_flights.csv`), **9.527 linhas**, rota-alvo
> CGH↔SDU, abril–junho/2023.
> Output: `C2 v1.1.0` → `output/c2_punctuality.json`, **25 registros**.
> Comando: `python src/analyze.py --input input/c1_flights.csv --computed-at 2026-07-24T00:00:00Z`

## 1. Linhagem do input (fixa o dado exato reconciliado)

| `source_file` | `source_year_month` | `file_sha256` (prefixo) | linhas |
|---|---|---|---|
| `VRA_2023_04.csv` | `2023-04` | `2240b33bc9f9…` | 2.982 |
| `VRA_2023_05.csv` | `2023-05` | `7b2b6cefa157…` | 3.372 |
| `VRA_2023_06.csv` | `2023-06` | `0cee6a880dd6…` | 3.173 |

Composição do C1: `REALIZADO` 9.093 · `CANCELADO` 434 · `NÃO INFORMADO` 0.
Rotas: `SBSP-SBRJ` 4.768 · `SBRJ-SBSP` 4.759. Companhias: TAM, GLO, AZU, ACN, PTB.

## 2. Regra aplicada (pontualidade `v1.1.0`)

- **Base:** chegada. Pontual ⟺ `(actual_arrival − scheduled_arrival) ≤ 15 min` (inclusivo; antecipado = pontual).
- **Denominador (`flights_operated`):** `REALIZADO` **E** `actual_arrival` **E** `scheduled_arrival` presentes.
- **Numerador (`flights_on_time`):** subconjunto do denominador que satisfaz a regra dos 15 min.
- **`on_time_rate` = on_time / operated**, **`null` se operated = 0** (nunca 0/0, nunca 0.0 fabricado).
- **Fora do denominador, contados à parte:** `CANCELADO`, `NÃO INFORMADO`,
  `REALIZADO` sem chegada real, `REALIZADO` sem chegada prevista.

> **Mudança v1.0.0 → v1.1.0** (§4): linhas sem `scheduled_arrival` saíram do denominador.
> Ver `docs/CONTRACT-CHANGE-REQUEST.md`.

## 3. Reconciliação — recontagem independente

Recontagem feita por script **independente**, escrito direto de `metrics-definitions.md`,
sem reutilizar a lógica de `src/analyze.py` (evita que um erro comum valide a si mesmo).

**Resultado: 25/25 grupos idênticos, 0 divergências, 9.527 linhas recontadas.**

| route_id | air | mês | oper | on_time | on_time_rate | canc | n/inf | s/ chegada | s/ previsão | total |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SBRJ-SBSP | ACN | 2023-04 | 0 | 0 | `null` | 0 | 0 | 0 | 3 | 3 |
| SBRJ-SBSP | ACN | 2023-05 | 0 | 0 | `null` | 0 | 0 | 0 | 4 | 4 |
| SBRJ-SBSP | ACN | 2023-06 | 0 | 0 | `null` | 0 | 0 | 0 | 4 | 4 |
| SBRJ-SBSP | AZU | 2023-04 | 300 | 225 | 0.7500 | 13 | 0 | 0 | 0 | 313 |
| SBRJ-SBSP | AZU | 2023-05 | 365 | 291 | 0.7973 | 2 | 0 | 0 | 0 | 367 |
| SBRJ-SBSP | AZU | 2023-06 | 336 | 279 | 0.8304 | 1 | 0 | 0 | 0 | 337 |
| SBRJ-SBSP | GLO | 2023-04 | 512 | 382 | 0.7461 | 21 | 0 | 0 | 0 | 533 |
| SBRJ-SBSP | GLO | 2023-05 | 568 | 477 | 0.8398 | 43 | 0 | 0 | 0 | 611 |
| SBRJ-SBSP | GLO | 2023-06 | 528 | 452 | 0.8561 | 38 | 0 | 0 | 0 | 566 |
| SBRJ-SBSP | PTB | 2023-05 | 0 | 0 | `null` | 0 | 0 | 0 | 1 | 1 |
| SBRJ-SBSP | TAM | 2023-04 | 601 | 497 | 0.8270 | 38 | 0 | 0 | 0 | 639 |
| SBRJ-SBSP | TAM | 2023-05 | 672 | 550 | 0.8185 | 31 | 0 | 0 | 1 | 704 |
| SBRJ-SBSP | TAM | 2023-06 | 649 | 563 | 0.8675 | 26 | 0 | 0 | 2 | 677 |
| SBSP-SBRJ | ACN | 2023-04 | 0 | 0 | `null` | 0 | 0 | 0 | 2 | 2 |
| SBSP-SBRJ | ACN | 2023-05 | 0 | 0 | `null` | 0 | 0 | 0 | 4 | 4 |
| SBSP-SBRJ | ACN | 2023-06 | 0 | 0 | `null` | 0 | 0 | 0 | 4 | 4 |
| SBSP-SBRJ | AZU | 2023-04 | 291 | 254 | 0.8729 | 22 | 0 | 0 | 6 | 319 |
| SBSP-SBRJ | AZU | 2023-05 | 362 | 319 | 0.8812 | 5 | 0 | 0 | 0 | 367 |
| SBSP-SBRJ | AZU | 2023-06 | 326 | 285 | 0.8742 | 10 | 0 | 0 | 8 | 344 |
| SBSP-SBRJ | GLO | 2023-04 | 513 | 411 | 0.8012 | 20 | 0 | 0 | 0 | 533 |
| SBSP-SBRJ | GLO | 2023-05 | 568 | 493 | 0.8680 | 43 | 0 | 0 | 0 | 611 |
| SBSP-SBRJ | GLO | 2023-06 | 530 | 451 | 0.8509 | 36 | 0 | 0 | 0 | 566 |
| SBSP-SBRJ | TAM | 2023-04 | 603 | 492 | 0.8159 | 37 | 0 | 0 | 0 | 640 |
| SBSP-SBRJ | TAM | 2023-05 | 677 | 597 | 0.8818 | 26 | 0 | 0 | 0 | 703 |
| SBSP-SBRJ | TAM | 2023-06 | 653 | 579 | 0.8867 | 22 | 0 | 0 | 0 | 675 |

**Fechamento (nenhuma linha C1 sumiu):**
`Σ flights_source_total = 9.527` = linhas do C1. Por bucket:
9.054 operados + 39 sem previsão + 434 cancelados + 0 não informados = **9.527** ✅
(o `assert` interno de `flights_source_total == linhas_do_grupo` garante isso em runtime, por grupo).

### Conferência à mão — amostra (TAM · SBSP-SBRJ · 2023-06)

Filtrando o C1 por `airline_icao=TAM`, `origin_icao=SBSP`, `dest_icao=SBRJ`,
`reference_date` em 2023-06 (`file_sha256 = 0cee6a880dd6…`):

- linhas no recorte: **675**
- `CANCELADO`: **22** → fora do denominador
- `REALIZADO` com ambas as chegadas: **653** → denominador
- destes, com `(real − prevista) ≤ 15 min`: **579** → numerador
- `579 / 653 = 0,88668…` → **`on_time_rate = 0.8867`** ✅ bate com o C2

## 4. Registros inválidos/ausentes — tratamento transparente

**39 linhas** (0,41% do C1) são `REALIZADO` com chegada real mas **sem chegada prevista**.
Para elas `pontual(v)` é **indefinido** — sem previsão não há o que comparar.

Mantê-las no denominador (comportamento `v1.0.0`) as tornava permanentemente inalcançáveis
pelo numerador, ou seja, **contadas como atrasadas** — afirmando algo que a fonte não diz.
Elas agora saem do denominador e aparecem em `flights_operated_missing_schedule`.
**Excluídas do cálculo, nunca do relatório.**

Distribuição: ACN 21 · AZU 14 · TAM 3 · PTB 1.

Impacto da correção (o que mudaria se fossem mantidas no denominador):

| Grupo | v1.0.0 (fabricado) | v1.1.0 (correto) | Δ |
|---|---|---|---|
| ACN — 6 grupos, 21 voos | `0.0000` ("0% pontual") | `null` (0 voos mensuráveis) | qualitativa |
| PTB — 1 grupo, 1 voo | `0.0000` | `null` | qualitativa |
| AZU SBSP-SBRJ 2023-04 | 0.8552 | **0.8729** | +1,76 pp |
| AZU SBSP-SBRJ 2023-06 | 0.8533 | **0.8742** | +2,09 pp |
| TAM SBRJ-SBSP 2023-06 | 0.8648 | **0.8675** | +0,27 pp |
| TAM SBRJ-SBSP 2023-05 | 0.8172 | **0.8185** | +0,12 pp |

ACN e PTB são operadores marginais no corredor (21 e 1 voo); a comparação-âncora
TAM × GLO × AZU não tem sua ordenação alterada, mas a margem de AZU sobre GLO em
`SBSP-SBRJ 2023-06` passa de +0,24 pp para +2,33 pp — material para a pergunta da Sprint.

## 5. Determinismo (AC5)

Duas execuções sobre o mesmo C1 (mesmos `file_sha256`), com `--computed-at` diferentes:
**saída idêntica em todos os campos exceto `computed_at_utc`** ✅ — verificado por
comparação estrutural do JSON com o campo de auditoria removido.

Reexecutar não duplica: no máximo um registro por (`route_id`, `airline_icao`,
`reference_month`) — 25 grupos, 25 registros, chaves únicas.

## 6. Cobertura de teste sintético

`input/sample_c1.csv` (11 linhas, `file_sha256` fictício `deadbeef…`) exercita cada caminho
de classificação, incluindo os dois adicionados em `v1.1.0`:

| Caso | Voo | Esperado | Obtido |
|---|---|---|---|
| atraso +10 min | 3001 | pontual | ✅ |
| atraso +15 min (limiar inclusivo) | 3002 | pontual | ✅ |
| atraso +16 min | 3003 | atrasado | ✅ |
| chegada antecipada (−10 min) | 3004 | pontual | ✅ |
| `CANCELADO` | 3005 | fora do denominador | ✅ |
| `NÃO INFORMADO` | 3006 | fora do denominador | ✅ |
| `REALIZADO` sem chegada real | 3007 | `missing_arrival` | ✅ |
| `REALIZADO` sem chegada prevista | 3008 | `missing_schedule` | ✅ |
| grupo 100% não mensurável | 5901 (ACN) | `on_time_rate = null` | ✅ |

Resultado: TAM `SBSP-SBRJ` 4/3 → 0.75 (8 linhas) · GLO `SBRJ-SBSP` 2/1 → 0.5 (2 linhas) ·
ACN `SBRJ-SBSP` 0/0 → `null` (1 linha). Total 11 = 8+2+1 ✅
