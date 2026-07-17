---
name: refine-rejected-tasks
description: Analyze rejected tasks and their validation reasons, refine or fix them, create additional tasks if needed, remove unnecessary ones, and update execution order while following established planning standards
agent: planner
alwaysApply: false
---

# Rejected Tasks Refinement Workflow

## Objective

Изучить отклонённые задачи, проанализировать причины отклонения, внести необходимые доработки, при необходимости создать дополнительные задачи и удалить ненужные, после чего обновить порядок выполнения.

Generate / update:
- исправленные и улучшенные task yaml файлы
- новые семантические задачи (при необходимости)
- актуальный файл `order.yaml`

## Constraints

- Соблюдать требования к планированию задач из `.kilo/commands/plan/plan-tasks.md`
- Не модифицировать исходный код проекта
- Не реализовывать изменения — только планировать и уточнять задачи
- Предпочитать атомарные, независимые и семантически устойчивые задачи
- Сохранять dependency integrity и безопасный порядок выполнения

---

# Workflow

## Step 1 — Load and Study Rejected Tasks

Изучить все отклонённые задачи:
- `.ai/tasks/todo/*_REJECTED.yaml`

Проанализировать:
- содержание каждой задачи
- текущий статус и проблемы

---

## Step 2 — Analyze Rejection Reasons

Изучить причины отклонения в:
- `.ai/tasks/validation/**.md`

Для каждой задачи определить:
- основные причины отклонения
- какие требования не были выполнены
- какие аспекты требуют доработки

---

## Step 3 — Refine Existing Tasks

Для каждой отклонённой задачи:
- внести необходимые исправления
- улучшить objective, semantic anchors, acceptance criteria и validation rules
- сделать задачу атомарной, измеримой и устойчивой к изменениям кода
- сохранить или обновить dependency metadata

Сохранять оригинальное имя файла (убрав `_REJECTED`), если задача остаётся актуальной.

---

## Step 4 — Create Additional Tasks (if needed)

При необходимости создать новые задачи, строго соблюдая:
- `.kilo/commands/plan/plan-tasks.md`
- шаблон задачи `.ai/tasks/templates/task_template.yaml`

Новые задачи должны:
- закрывать выявленные пробелы
- быть независимыми и семантически целостными
- правильно интегрироваться в общий rollout plan

---

## Step 5 — Remove Unnecessary Tasks

Удалить задачи, которые:
- больше не актуальны
- дублируют другие задачи
- потеряли смысл после изменений в проекте
- не соответствуют текущим целям

---

## Step 6 — Update Execution Order

Обновить файл:
- `.ai/tasks/todo/order.yaml`

При обновлении:
- учесть все оставшиеся и новые задачи
- обеспечить корректный dependency-aware порядок
- сохранить нумерацию, соответствующую последовательности rollout
- максимально безопасно распараллелить независимые задачи

Использовать шаблон `.ai/tasks/templates/order_template.yaml` (если доступен).

---

# Expected Output

Результат должен включать:
- исправленные и улучшенные yaml-файлы задач (без `_REJECTED`)
- новые задачи (при необходимости) в формате `TASK_<XXX>_<task_id>_<short_name>.yaml`
- актуализированный `order.yaml` с корректным топологическим порядком
- чистую директорию `todo/` без устаревших или ненужных задач

Результат НЕ должен включать:
- изменения в исходном коде
- реализацию фиксов
- нарушение правил планирования задач
