# CLAUDE.md — Método de trabajo de este proyecto

> Este archivo se carga automáticamente en cada sesión. Es el **método** con el
> que se construyó todo lo que hay aquí, destilado para que cualquier modelo
> que continúe el proyecto trabaje igual y la calidad no baje. No es historia
> (eso vive en `PLAN.md` §6 y el git log) — son instrucciones operativas.
> Escrito por la sesión que construyó F0/F1 (2026-07-07 → 2026-07-10).

## Dónde vive la verdad

- **`PLAN.md`** — estado operativo VIVO: fase actual, siguiente jugada, hitos.
  **Se lee al empezar toda sesión y se actualiza en cada hito** (vía PR, como
  todo). Es el pase de estafeta entre sesiones: escribe la "siguiente jugada"
  con el detalle suficiente para que una sesión sin contexto la ejecute.
- **`docs/00`–`07`** — el diseño: decisiones (00), features y modelos (04),
  métricas y gates (06), roadmap por fases (07). Ante cualquier decisión de
  modelado, buscar primero qué dice el doc; si se decide algo nuevo,
  registrarlo (addendum en `docs/00-decisiones.md`).
- **`infra/schema.sql`** — fuente canónica del schema. Las migraciones en
  `infra/migrations/` replican el DDL; ambos se actualizan juntos.

## El ciclo de tanda (así se construyó todo)

Una **tanda** = un lote coherente de trabajo = **un PR a `main`**. El ciclo:

1. **Explorar antes de diseñar.** Estado real ≠ estado documentado: verificar
   git log, corridas de Actions y código antes de asumir nada del PLAN.md.
2. **Diseñar con decisiones explícitas.** Cada feature con su fórmula exacta,
   ventana y regla as-of ANTES de escribir código. Las dudas de diseño se
   resuelven contra `docs/04`, no improvisando.
3. **Implementar en commits ordenados** (ops → schema → ingesta → features →
   ml → tests), cada uno con la suite en verde.
4. **Verificar contra sistemas reales, no mocks** (ver sección siguiente).
5. **Revisión adversarial** antes del PR (ver sección siguiente).
6. **PR → merge → medir en producción → PLAN.md actualizado con el hito.**
   La rama de trabajo se reinicia desde `main` tras cada merge
   (`git checkout -B <rama> origin/main`). Nunca push directo a `main`.

El owner ya delegó el flujo completo (merge de PRs y dispatches en Actions)
— ejecutarlo de punta a punta, reportando resultados con números.

## Verificación: la regla que más calidad compró

**Nada se declara terminado sin ejercitarlo end-to-end contra el sistema
real.** Ejemplos que atraparon bugs reales en este proyecto:

- La migración 003 se probó **con el splitter real de `apply_migration`**
  (no con psql) y explotó: un `;` dentro de un COMENTARIO parte los
  statements. Correr toda migración 2× (idempotencia) con ese job.
- La degradación pre-migración se probó **contra una base con el schema de
  `main`** (`git show main:infra/schema.sql | psql ...`): atrapó que pandas
  envuelve errores en `pandas.errors.DatabaseError`, no en el
  `ProgrammingError` de SQLAlchemy.
- Postgres real local para integración: `initdb`/`pg_ctl` como usuario
  `nobody` (root no puede), socket en `/tmp/pg0/sock` (límite de 107 chars
  en el path), schema aplicado, `EDGE_TEST_DATABASE_URL` exportada. El venv
  va en el scratchpad de la sesión (PEP 668 bloquea pip global); requiere
  python3.12.

## Los tests que no se negocian

- **Paridad online/bulk** (`test_ml.py::test_bulk_features_match_online_builder`):
  toda feature nueva se implementa en `builder.py` (online) Y `dataset.py`
  (bulk) y el test compara campo a campo. Es el guard anti train/serve skew
  — la clase de bug que envenena un modelo en silencio.
- **Valores calculados A MANO** en los tests de features (no "el código
  contra sí mismo"): elegir seeds chicos, calcular K-BB%/xFIP/ventanas con
  lápiz, assertar el número exacto.
- **Casos borde deliberados en los seeds**: el umbral exacto (b2b con 3 outs
  justos), el borde de ventana (línea en el día 31), la exclusión de mismo
  día, el dato NULL que no debe volverse cero.
- Los tests de integración usan el marker `integration` y se saltan sin DB;
  la suite unit siempre corre.

## Principios de datos (violarlos mata el proyecto)

- **Nunca fabricar datos.** Sin evidencia → `None`/`NaN`, jamás un cero
  inventado. Un cero solo es verdadero si el archivo estaba VIVO y calla
  (patrón "liga as-of existe" del bloque bullpen). La revisión adversarial
  atrapó exactamente esta violación una vez — buscarla siempre.
- **As-of estricto**: todo corte es `< start_time` (o día UTC < día del
  evento para bloques day-based); constantes de liga también as-of;
  calibración out-of-time. El leakage no da errores: da métricas
  hermosas y falsas.
- **Idempotencia en todos los jobs**: corrida duplicada = no-op (upsert por
  identidad externa, `ON CONFLICT`, skip-existing). Esto permite re-disparar
  sin miedo y es lo que hace seguros los lookbacks del cron.
- **Honestidad en los reportes**: los límites se dicen (gate NOT evaluated,
  n insuficiente, sesgo probable-vs-real documentado), lo rojo se reporta
  con su porqué, y las métricas de cobertura (`sp_coverage`,
  `bullpen_coverage`) existen para que los huecos no sean silenciosos.

## Revisión adversarial (paga siempre)

Antes de cada PR sustantivo: lanzar revisores paralelos por dimensión
(matemática/paridad, ingesta, ops/SQL, entrenamiento) sobre `git diff main`,
y por cada hallazgo un verificador independiente cuyo trabajo es **REFUTARLO**
leyendo el código real (`real=true` solo si el fallo se traza paso a paso).
Solo se corrige lo confirmado. Resultados en este proyecto: 10/13 hallazgos
confirmados en la tanda F1, 2/6 en la F1.1 — ambas veces atraparon bugs que
los 160+ tests no veían. Los refutados baratos de endurecer (constante
nombrada, métrica de cobertura) también se toman.

## Operación en GitHub Actions

- **No hay `gh` CLI ni API directa** — todo vía las herramientas MCP de
  GitHub. Las respuestas de `actions_list` pesan >200KB: se guardan en
  archivo y se parsean con python (hay un helper en el scratchpad; recrearlo
  es trivial: cargar el JSON e imprimir run_number/status/conclusion).
- **Dispatches de a uno**: todos los `workflow_dispatch` comparten un
  concurrency group; un segundo pendiente puede ser cancelado. Esperar el
  verde antes del siguiente.
- **Esperas con timers en background** (`sleep N` con `run_in_background`,
  que re-invoca al terminar) — NUNCA sleep en foreground ni polling apretado.
- **Los crons de GitHub se retrasan 1–4h o se saltan** bajo carga (por eso
  van en minutos raros). El cron diario tiene lookback de 3 días y el audit
  con `--fail-on-gaps` manda email en rojo: la detección ya es automática.
  Un día atrasado se recupera re-corriendo los mismos pasos del cron a mano
  (son idempotentes). Los summaries JSON de cada job están al final del log
  de la corrida (`get_job_logs` con tail).
- **Cómo medir una tanda de features**: guardar el baseline anterior (log
  loss por celda del walk-forward), usar un control que NO debe moverse
  (p.ej. F5 cuando el cambio es solo-ML), y conocer el ruido de corrida:
  ±0.0002 en log loss entre corridas idénticas (lbfgs sin converger en
  runners distintos). Deltas dentro del ruido no son señal.

## Economía de sesión

- **Sesión nueva por tanda.** El contexto largo encarece cada paso; PLAN.md
  es el pase de estafeta. Al cerrar una tanda, dejar la "siguiente jugada"
  lista para una sesión sin memoria.
- Committer/autor de git: `noreply@anthropic.com` / `Claude` (ya en el
  config del repo; si un hook se queja, `--reset-author` y push normal —
  el force-push está bloqueado y casi nunca hace falta: tras un merge la
  rama vieja es ancestro de `main`).
- Reportar al owner en **CST (UTC−6)**. Cron diario 8:17 AM, snapshots
  9:23 AM / 12:23 PM / 3:23 PM / 6:23 PM CST.

## Reglas del producto que ningún modelo debe olvidar

Las de `PLAN.md` §5 — en particular: el LLM explica pero JAMÁS genera
probabilidades ni decide picks; winrate no es la métrica (calibración, EV,
CLV sí); todo lo evaluado se registra; no se promete rentabilidad; y el
proyecto **se mata sin drama** si tras ≥300 picks de paper trading no bate
al mercado. El gate duro de publicación (docs/04 §2.4: log loss < market
prior, n≥200 por temporada) está cableado en `train_f1` — no se puentea.
