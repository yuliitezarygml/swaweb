# Docker Setup for SWA Web Application

## Структура

- **webapp**: Flask приложение на порту 5000
- **mongodb**: MongoDB 7.0 на порту 27017
- **mongo-express**: Web интерфейс для MongoDB на порту 8081

## Быстрый старт

```bash
# Запуск всех сервисов
docker-compose up -d

# Просмотр логов
docker-compose logs -f

# Остановка
docker-compose down

# Полная очистка (с удалением данных)
docker-compose down -v
```

## Доступ к сервисам

- **Веб-приложение**: http://localhost:5000
- **Mongo Express**: http://localhost:8081
  - Логин: admin
  - Пароль: admin123

## База данных

**MongoDB подключение:**
- Host: mongodb (внутри Docker) / localhost:27017 (снаружи)
- Database: swa_database
- Admin: admin/admin123

**Созданные коллекции:**
- `users` - пользователи
- `promo_codes` - промо-коды
- `games` - кеш игр
- `sessions` - сессии
- `stats` - статистика
- `devices` - устройства
- `slots` - слоты

## Переменные окружения

В `docker-compose.yml` можно изменить:
- `SECRET_KEY` - секретный ключ Flask
- `MONGODB_URI` - URI подключения к MongoDB
- Пароли MongoDB

## Разработка

Для разработки можете использовать volume mapping:
```yaml
volumes:
  - .:/app
```

## Производство

Обязательно измените:
1. `SECRET_KEY` на случайный ключ
2. Пароли MongoDB
3. Удалите mongo-express сервис