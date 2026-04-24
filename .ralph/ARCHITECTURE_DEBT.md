# Ralph Architecture Debt & Modernization Plan
_Зафиксировано: $(date +%Y-%m-%d)_

## Текущие проблемы

| Проблема | Severity | Описание |
|----------|----------|----------|
| Монолит | HIGH | ralph.sh 5k+ строк, оркестрация + бизнес-логика вместе |
| Хрупкий state | HIGH | Нет транзакционности tasks.json/progress.md |
| Слабая память | MEDIUM | Только core.md + recent.md (5 записей) |
| Нет security | MEDIUM | Нет Semgrep/Bandit scanning |
| Медленные тесты | MEDIUM | make test 16+ мин, нет fast gate |
| Велосипеды | LOW | Самописные парсеры JSON, prompt builder, retry logic |

## Целевая архитектура (Strangler Pattern)

### Этап 1 — Python Core (заменяет bash логику)
- state_service.py    → транзакционный R/W tasks.json
- review_service.py   → единый парсер lead review JSON  
- verify_service.py   → верификация closure

### Этап 2 — Инфраструктура
- SQLite event log    → аудит вместо flat files
- Qdrant memory       → семантический поиск вместо recent.md

### Этап 3 — Инструменты
- Semgrep             → security scanning в lead review
- Superpowers         → шаблоны промптов
- Fast test gate      → pytest -x -q вместо make test

## Инструменты для интеграции

| Инструмент | Назначение | Лицензия |
|------------|------------|----------|
| Qdrant | Долгосрочная память | Apache-2.0 |
| Semgrep | Security scanning | LGPL-2.1 |
| Superpowers | Шаблоны промптов | MIT |
| Prefect OSS | Оркестрация | Apache-2.0 |

## Принцип миграции
НЕ переписывать ralph.sh целиком.
Strangler: каждый новый модуль заменяет один кусок bash,
старый код остаётся до полной замены.

## Когда начинать
ТОЛЬКО после того как R20 закрыт и ночной прогон стабилен.
