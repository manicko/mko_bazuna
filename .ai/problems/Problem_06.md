У нас постоянные проблемы с тестами из-за языка.
Агенты постоянно путаются в настройках языков в тестах, тесты перестают проходить и агент не понимает - это он сломал или архитектурная проблема.

Это явно архитектурная проблема, раз много агентов с ней сталкиваются. У нас явно некорректно настроены тесты. 
Нужно изучить проблему.
Изучить текущую архитектуру.
Изучить современные практики работы с такими тестами.
Выбрать лучший вариант и стандарт для нашей архитектуры для будущей поддержки.

Ниже описание проблемы


LANGUAGE_CODE = "ru" is set in base.py (line 67).
The test settings (test.py) import from base with from .base import * and do NOT override LANGUAGE_CODE.
The middleware includes apps.core.middleware.language.LanguagePreMiddleware (not django.middleware.locale.LocaleMiddleware). Let me check what this middleware does.
Let me check the LanguagePreMiddleware to understand how language is determined. The middleware name suggests it's a custom middleware that handles language selection. It might use Accept-Language header or fall back to LANGUAGE_CODE.

The key insight is: tests that DON'T set Accept-Language: en get Russian output (the default language), so assert "Clear all filters" in content fails because the rendered text is "Очистить все фильтры".