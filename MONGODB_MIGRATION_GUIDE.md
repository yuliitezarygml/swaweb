# MongoDB Setup Guide for SWA Web Application

## Обзор

Проект работает ТОЛЬКО с MongoDB. JSON файлы полностью удалены. Все данные хранятся в MongoDB с соответствующими индексами и оптимизациями.

## Структура файлов

```
mongo/
├── __init__.py
├── connection.py              # Подключение к MongoDB
├── models/
│   ├── __init__.py
│   ├── user.py               # Модель пользователя
│   ├── promo_code.py         # Модель промо-кодов
│   ├── game.py               # Модель игр
│   ├── session.py            # Модель сессий
│   └── device.py             # Модель устройств
├── operations/
│   ├── __init__.py
│   ├── user_ops.py           # Операции с пользователями
│   ├── promo_ops.py          # Операции с промо-кодами
│   ├── game_ops.py           # Операции с играми
│   ├── session_ops.py        # Операции с сессиями
│   └── device_ops.py         # Операции с устройствами
└── utils/
    ├── __init__.py
    └── migration.py          # Утилиты миграции
```

## Запуск с Docker

### 1. Сборка и запуск
```bash
# Запуск всех сервисов
docker-compose up -d

# Проверка логов
docker-compose logs -f webapp
```

### 2. Инициализация данных
Данные создаются автоматически при первом запуске приложения.
MongoDB коллекции инициализируются через `mongodb-init/init-db.js`

## Запуск без Docker

### 1. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 2. Запуск MongoDB
```bash
# Если MongoDB установлен локально
mongod --dbpath /path/to/data

# Или через Docker
docker run -d -p 27017:27017 --name mongodb mongo:7.0
```

### 3. Настройка переменных окружения
```bash
# Установить переменную окружения
export MONGODB_URI="mongodb://localhost:27017/swa_database"
```

### 4. Запуск приложения
```bash
python app.py
```

## Управление данными

Все операции с данными выполняются через MongoDB:
- Создание пользователей - через веб-интерфейс
- Управление промо-кодами - через админ-панель
- Резервное копирование - через mongodump/mongorestore

## Переменные окружения

```bash
# MongoDB подключение
MONGODB_URI=mongodb://mongodb:27017/swa_database

# Или для локального MongoDB
MONGODB_URI=mongodb://localhost:27017/swa_database

# Секретный ключ Flask
SECRET_KEY=your-very-secure-secret-key
```

## Коллекции MongoDB

### users
- **Индексы**: username (unique), email (unique), id (unique)
- **Документы**: Полная информация о пользователях

### promo_codes  
- **Индексы**: code (unique), id (unique)
- **Документы**: Промо-коды с лимитами использования

### games
- **Индексы**: game_id (unique), access_type
- **Документы**: Кеш игр с внешнего API

### sessions
- **Индексы**: session_id (unique), user_id, expires_at (TTL)
- **Документы**: Пользовательские сессии

### devices
- **Индексы**: device_id (unique), user_id
- **Документы**: Устройства пользователей

### stats
- **Индексы**: date, type
- **Документы**: Статистика приложения

## Основные изменения в коде

### Старый способ (JSON):
```python
# Загрузка пользователей
users = get_users()
user = find_user_by_username(username)

# Сохранение
save_users(users)
```

### Новый способ (MongoDB):
```python
# Загрузка пользователей
user = user_ops.get_user_by_username(username)
users = user_ops.get_all_users()

# Сохранение происходит автоматически
user_ops.create_user(user)
user_ops.update_user(user_id, updates)
```

## Преимущества MongoDB

1. **Производительность**: Индексы для быстрого поиска
2. **Масштабируемость**: Поддержка больших объемов данных
3. **ACID транзакции**: Целостность данных
4. **Автоматическое TTL**: Автоочистка expired сессий
5. **Агрегации**: Сложные запросы для аналитики
6. **Репликация**: Высокая доступность

## Устранение проблем

### Ошибка подключения к MongoDB
```bash
# Проверить статус сервиса
docker-compose ps

# Перезапустить MongoDB
docker-compose restart mongodb
```

### Потеря данных при миграции
```bash
# Сделать резервную копию перед миграцией
cp users.json users_backup.json
cp promo_codes.json promo_codes_backup.json

# Восстановить из резервной копии
python migrate_data.py clear
# Вернуть файлы и повторить миграцию
```

### Проблемы с индексами
```bash
# Войти в MongoDB
docker exec -it swa_mongodb mongosh

# Пересоздать индексы
use swa_database
db.users.dropIndexes()
db.users.createIndex({"username": 1}, {unique: true})
```

## Мониторинг

### Mongo Express (Web UI)
- URL: http://localhost:8081
- Логин: admin / admin123

### Логи приложения
```bash
# Логи приложения
docker-compose logs -f webapp

# Логи MongoDB  
docker-compose logs -f mongodb
```

## Переход в продакшн

1. Изменить пароли в `docker-compose.yml`
2. Удалить mongo-express сервис
3. Настроить SSL для MongoDB
4. Включить аутентификацию MongoDB
5. Настроить резервное копирование

## Резервное копирование

```bash
# Создать дамп MongoDB
docker exec swa_mongodb mongodump --db swa_database --out /data/backup

# Восстановить дамп
docker exec swa_mongodb mongorestore /data/backup
```