
*  Django + PostgreSQL
*  Django Admin 
*  Filtration: django-filter, django-mptt
*  Search: django-haystack + Whoosh
*  API: DRF
*  Telegram bot: telethon
*  Background jobs: Celery + Redis
*  Frontend: Django Templates + HTMX + Alpine.js (или SPA на DRF API), Tailwind CSS + daisyUI

```
# Core / Web
django==5.1.2                    

# Database / Drivers
psycopg2-binary==2.9.9            

# Authentication
django-allauth==0.63.6            

# Models / Utils
django-mptt==0.16.0               # Древовидные категории
django-filter==24.3               # Фильтры в списках / API


# Search
django-haystack==3.3.0
whoosh==2.7.4                     # Локальный поиск без ES

# API 
djangorestframework==3.15.2


# Telegram integration
telethon>=1.36.0                  


# Tasks 
celery==5.4.0                     # Фоновые задачи
redis==5.1.1                      # Брокер/кеш


# Frontend / Styling 
django-tailwind==4.4.2            # Tailwind + daisyUI + standalone CLI 
django-htmx==1.19.0               


# Images / Media
pillow>=10.4.0                    

# Testing / Dev tools
pytest==8.3.3                     # Тесты
pytest-django==4.9.0              # Django fixtures / client для pytest
pytest-factoryboy==2.7.0          # Фабрики моделей


# Linting / Formatting 
ruff==0.9.0                       

```

