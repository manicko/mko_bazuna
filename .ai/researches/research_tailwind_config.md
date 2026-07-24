# Research Report: django-tailwind Configuration

## Executive Summary
CSS is not loading on the site because `output.css` does not exist. The Tailwind build process is incomplete.

## 1. Tailwind Configuration Locations

### Django Settings (src/backend/config/settings/base.py:75, 171)
```python
INSTALLED_APPS = [
    ...
    "tailwind",                    # django-tailwind core package
    "theme",                       # Project's theme app
    ...
]

TAILWIND_APP_NAME = "theme"
```

### Theme App Structure
```
src/theme/
├── __init__.py
├── apps.py (ThemeConfig)
└── static/
    └── theme/
        └── css/
            └── input.css (4 lines with @tailwind directives)
```

### input.css Content
```css
/* Tailwind input stylesheet */
@tailwind base;
@tailwind components;
@tailwind utilities;
```

## 2. Missing Configuration Files

- **tailwind.config.js**: NOT FOUND - No configuration for Tailwind CLI
- **output.css**: NOT FOUND - No compiled CSS exists anywhere in the project

## 3. Root Cause Analysis

### Problem in Dockerfile (docker/Dockerfile:66-67)
```dockerfile
RUN tailwindcss build && \
    uv run python src/backend/manage.py collectstatic --noinput
```

**Issues:**
1. `tailwindcss build` runs without any config file
2. No output destination specified for the build
3. Django management command `tailwind build` is NOT being called
4. Without configuration, Tailwind CLI has no input/output paths

### Why This Fails
- Tailwind CLI needs `tailwind.config.js` to know:
  - Where input.css is located
  - Where to put output.css  
  - What content to include (JIT mode, purge, etc.)
- django-tailwind expects to use `python manage.py tailwind build` which handles paths automatically

## 4. Expected Behavior

django-tailwind in standalone binary mode should:
1. Read configuration from tailwind.config.js (or use defaults)
2. Build input.css → output.css with Tailwind directives
3. Place output.css in theme/static/theme/css/
4. collectstatic copies it to STATIC_ROOT/staticfiles/