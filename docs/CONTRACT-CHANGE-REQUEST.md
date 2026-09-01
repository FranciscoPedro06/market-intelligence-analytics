# Solicitação de emenda de contrato — C2 `v1.0.0` → `v1.1.0`

> **Status:** ✅ **APLICADA** — aprovada e aplicada pelo Sprint Lead em **2026-07-25**.
> `C2 v1.1.0` e `pontualidade v1.1.0` estão vigentes em `Market-Intelligence-Ecosystem`
> (`docs/ecosystem/contracts.md`, `docs/product/metrics-definitions.md`).
> **Origem:** Analytics Engineer, Sprint 1 / Fase 2 (integração com o C1 real).
> **Destinatário:** Sprint Lead (guardião dos contratos).
> **Motivo:** contratos são do ecossistema — nenhum repositório emenda sozinho um contrato
> que compartilha. O Analytics implementou o comportamento (`analytics_version 1.1.0`) e
> solicitou a emenda; a governança foi atualizada em seguida.
>
> Documento mantido como **registro histórico** da decisão (rastreabilidade: por que o
> denominador mudou entre `v1.0.0` e `v1.1.0`). Não requer mais nenhuma ação.

## 1. O achado

Ao processar o C1 real (9.527 linhas, CGH↔SDU, abr–jun/2023), **39 linhas** (0,41%) são
`flight_status = REALIZADO` **com** `actual_arrival` mas **sem** `scheduled_arrival`.

A definição congelada é:

```
pontual(v) ⟺ (chegada_real(v) − chegada_prevista(v)) ≤ 15 minutos
```

Sem `chegada_prevista`, o predicado é **indefinido** — não é falso.

O C2 `v1.0.0` define o denominador como “`REALIZADO` **E** `actual_arrival` não nulo”, o que
inclui essas linhas. Como jamais podem satisfazer o numerador, elas eram **contadas como
atrasadas** — o sistema afirmava que o voo não foi pontual quando a fonte não permite dizê-lo.
Isso colide com a garantia “**Nulos nunca inventados**” (contracts.md) e com o DoD
“registros inválidos/ausentes tratados de forma transparente — **nunca inventados**”.

Efeito observado: **ACN publicava `on_time_rate = 0.0000`** (“0% pontual”) em todos os seus
6 grupos, com 21 de seus 22 voos indefinidos; AZU `SBSP-SBRJ` subestimada em até **2,09 pp**.

> **Errata — 2026-08-31 (GOV-004).** A contagem “21 de seus **22** voos” está **errada no
> original**: a ACN tem **21 voos** nesta rota/amostra, e **os 21** são indefinidos. Verificado
> contra o C2 real: 6 grupos ACN, `flights_source_total` = 21, `flights_operated_missing_schedule`
> = 21, denominador 0 — conferindo com `EVIDENCE.md` do Collector (5 + 8 + 8 = 21 `REALIZADO`,
> 0 `CANCELADO`).
>
> Registrado como **errata, não reescrita**: o número errado é preservado acima porque este
> documento é o registro histórico do pedido de emenda tal como submetido ao Sprint Lead. **A
> conclusão da CCR não depende dele** — com 21 ou 22 voos, o argumento é o mesmo: voos com
> pontualidade indefinida estavam sendo contados como atrasados.

## 2. Emenda aplicada

Simétrica ao tratamento **já existente** para o caso espelho (`flights_operated_missing_arrival`).

### 2.1 `docs/ecosystem/contracts.md` — C2, tabela “Campos — Medidas”

Alterar a linha:

| Campo | Notas (v1.0.0) | Notas (v1.1.0) |
|---|---|---|
| `flights_operated` | `flight_status = REALIZADO` **E** `actual_arrival` não nulo. | `flight_status = REALIZADO` **E** `actual_arrival` não nulo **E** `scheduled_arrival` não nulo. |

Acrescentar a linha (**campo novo, aditivo**):

| Campo | Tipo | Notas |
|---|---|---|
| `flights_operated_missing_schedule` | integer (≥0) | Transparência: `REALIZADO` com chegada real mas **sem chegada prevista** — pontualidade indefinida. Fora do denominador, nunca contado como atrasado. |

Alterar a fórmula de fechamento:

```diff
- flights_source_total = operated + missing_arrival + cancelled + not_reported
+ flights_source_total = operated + missing_arrival + missing_schedule
+                      + cancelled + not_reported
```

### 2.2 `docs/product/metrics-definitions.md` — pontualidade `v1.1.0`

Em **“Taxa de pontualidade”**, o denominador passa a exigir também chegada prevista:

```diff
- Denominador = voos operados (REALIZADO) que possuem chegada real registrada.
+ Denominador = voos operados (REALIZADO) que possuem chegada real
+ e chegada prevista registradas (sem previsão, a pontualidade é indefinida).
```

Em **“Exclusões (fora do denominador)”**, acrescentar:

> - Voos `REALIZADO` **sem chegada prevista** — `pontual(v)` é indefinido sem o horário de
>   comparação; excluídos do denominador e registrados como dado ausente transparente.
>   Nunca contados como atrasados.

## 3. Compatibilidade

- **Aditiva para leitores.** Nenhum campo do C2 `v1.0.0` foi removido ou renomeado. A API
  (RT5: não calcula, apenas serve) continua funcionando sem alteração; o novo contador só
  precisa ser exibido se o time quiser expor a transparência.
- **Valores mudam** em 6 dos 25 grupos (ver `RECONCILIATION.md` §4) — é justamente a correção
  pretendida. 7 grupos passam a `on_time_rate = null`, valor **já previsto** pelo C2 `v1.0.0`
  para denominador 0.
- **Sem ampliação de escopo.** Nenhuma métrica nova; apenas o recorte da pontualidade
  existente. Cancelamento segue fora de escopo.

## 4. Alternativas descartadas

| Alternativa | Por que não |
|---|---|
| Manter no denominador (literal ao `v1.0.0`) | Publica “ACN = 0% pontual”, afirmando o que a fonte não diz. Viola “nulos nunca inventados”. |
| Reaproveitar `flights_operated_missing_arrival` | Evitaria campo novo, mas contradiz o texto do contrato (“`REALIZADO` **sem** `actual_arrival`”) e conflaria duas causas distintas de ausência. |

## 5. Rastreabilidade

- Implementação: `src/analyze.py` — commit `feat: exclude unmeasurable flights from denominator (C2 v1.1.0)`.
- Evidência: `RECONCILIATION.md` §4 (impacto quantificado) e §3 (recontagem independente, 25/25 grupos).
- Cobertura: `input/sample_c1.csv`, voos `3008` (sem previsão) e `5901` (grupo 100% indefinido → `null`).
- Campos emitidos hoje: `metric_version = v1.1.0`, `analytics_version = 1.1.0`.
