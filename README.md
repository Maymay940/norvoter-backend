# Norvoter Backend (Django + PostgreSQL + MinIO)

## Описание
Backend-часть системы учёта показаний счётчиков воды. Предоставляет REST API для фронтенда, управляет базой данных и файловым хранилищем.

## Структура backend/

backend/
├── meters/                     # Django-приложение
├── water_meters_project/       # Настройки проекта
├── manage.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .flake8
├── .gitignore
├── pyproject.toml
├── .pre-commit-config.yaml
└── .env.example                # для документации

## Технологии
- [Django 4.2](https://docs.djangoproject.com/en/4.2/)
- [PostgreSQL 15](https://www.postgresql.org/docs/15/)
- [MinIO](https://min.io/docs/minio/linux/index.html)
- [Docker](https://docs.docker.com/)

## Переменные окружения (в `docker-compose.yml`)
| Переменная | Значение |
|------------|----------|
| DB_HOST | postgres |
| DB_NAME | norvoter |
| DB_USER | postgres2 |
| DB_PASSWORD | 1qaz |
| MINIO_ACCESS_KEY | minioadmin |
| MINIO_SECRET_KEY | minioadmin123 |

## Запуск (через Docker)
```bash
 cd backend
 docker-compose up -d
```
## API эндпоинты
- GET /api/meters/ — список счётчиков
- GET /api/requests/ — список заявок
- POST /api/add-reading/ — добавить показания

## Примечания
- Backend не отдаёт HTML, только JSON.
- Все настройки хранятся в docker-compose.yml, .env не используется.
- Миграции применяются автоматически при запуске контейнера.
- Файлы (фото, видео) хранятся в MinIO.
