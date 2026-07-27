---
id: design-system-components
domain: design-system
tags:
  - components
  - buttons
  - cards
  - forms
  - navigation
related:
  - design-system-index
  - tokens
  - ui-patterns
---

# Component Catalog

> Atomic design component patterns with code examples. All components use tokens from `tokens.md`.

## Atomic Components

### Buttons

Primary interactive elements for all CTAs.

#### Primary Button

Main actions, form submissions, save.

```html
<button type="submit" class="px-6 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2">
    Save Changes
</button>
```

| Property | Value |
|----------|-------|
| Background | `bg-blue-600` (Primary token) |
| Text | `text-white` |
| Hover | `hover:bg-blue-700` |
| Size | 40px height (`px-6 py-2`) |
| Pages | All templates |

#### Success Button

Approve actions, positive confirmations.

```html
<button type="submit" class="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2">
    Approve
</button>
```

| Property | Value |
|----------|-------|
| Background | `bg-green-600` (Success token) |
| Text | `text-white` |
| Hover | `hover:bg-green-700` |
| Size | 40px height (`px-4 py-2`) |
| Pages | `admin/moderation/review.html` |

#### Danger Button

Reject actions, destructive operations.

```html
<button type="submit" class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2">
    Reject
</button>
```

| Property | Value |
|----------|-------|
| Background | `bg-red-600` (Error token) |
| Text | `text-white` |
| Hover | `hover:bg-red-700` |
| Size | 40px height (`px-4 py-2`) |
| Pages | `admin/moderation/review.html` |

#### Secondary Button

Cancel, back navigation, alternative actions.

```html
<a href="{% url 'ads:dashboard' %}" class="px-6 py-2 bg-white text-gray-700 rounded-lg font-medium border border-gray-300 hover:bg-gray-50 transition-colors focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2">
    Cancel
</a>
```

| Property | Value |
|----------|-------|
| Background | `bg-white` |
| Text | `text-gray-700` |
| Border | `border-gray-300` |
| Hover | `hover:bg-gray-50` |
| Size | 40px height (`px-6 py-2`) |
| Pages | `ads/edit.html`, `ads/dashboard.html` |

#### Disabled Button

Unavailable actions, read-only states.

```html
<button type="button" disabled class="px-6 py-3 bg-gray-300 text-white rounded-lg font-medium cursor-not-allowed">
    Contact Seller
</button>
```

| Property | Value |
|----------|-------|
| Background | `bg-gray-300` |
| Text | `text-white` |
| Cursor | `cursor-not-allowed` |
| Size | 48px height (`px-6 py-3`) |
| Pages | `ads/detail.html`, `components/consent_banner.html` |

#### Icon Button

Close modals, drawer triggers.

```html
<button type="button" class="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-gray-500" aria-label="Close">
    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
    </svg>
</button>
```

| Property | Value |
|----------|-------|
| Size | 40px × 40px (`p-2` + 20px icon) |
| Icon | 20px (`w-5 h-5`) |
| Focus | `focus:ring-2 focus:ring-gray-500` |
| Required | `aria-label` |
| Pages | `admin/review.html` |

### Form Inputs

Text, number, and textarea inputs with validation states.

#### Text Input

```html
<div class="mb-4">
    <label for="title" class="block font-medium mb-2">Title</label>
    <input 
        type="text" 
        id="title" 
        name="title"
        maxlength="200"
        required
        class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
</div>
```

| Property | Value |
|----------|-------|
| Height | 40px (`py-2` + font) |
| Border | `border-gray-300` |
| Focus | `ring-2 ring-blue-500` |
| Pages | `ads/edit.html` |

#### Textarea

```html
<div class="mb-4">
    <label for="description" class="block font-medium mb-2">Description</label>
    <textarea 
        id="description" 
        name="description"
        rows="6"
        required
        class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y"
    >{{ ad.description }}</textarea>
</div>
```

| Property | Value |
|----------|-------|
| Resize | `resize-y` (vertical only) |
| Pages | `ads/edit.html`, `admin/review.html` |

#### Number Input (Price)

```html
<div class="mb-4">
    <label for="price" class="block font-medium mb-2">Price (BAM)</label>
    <input 
        type="number" 
        id="price" 
        name="price"
        min="0"
        step="0.01"
        class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
</div>
```

| Property | Value |
|----------|-------|
| Step | `0.01` (currency precision) |
| Pages | `ads/edit.html`, filter price range |

#### Error State

```html
<div class="mb-4">
    <label for="title" class="block font-medium mb-2">Title</label>
    <input 
        type="text" 
        id="title" 
        name="title"
        class="w-full px-3 py-2 border border-red-500 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500"
        aria-invalid="true"
        aria-describedby="title-error"
    >
    <p id="title-error" class="mt-1 text-sm text-red-600">Title is required</p>
</div>
```

| Property | Value |
|----------|-------|
| Border | `border-red-500` |
| Focus | `ring-2 ring-red-500` |
| Error text | `text-red-600` |
| ARIA | `aria-invalid`, `aria-describedby` |

### Badges

Status indicators and category tags.

#### Published Status

```html
<span class="px-2 py-1 bg-green-100 text-green-800 rounded text-xs font-medium">
    Published
</span>
```

| Property | Value |
|----------|-------|
| Shape | `rounded` (4px) |
| Background | `bg-green-100` |
| Text | `text-green-800` |
| Pages | `ads/dashboard.html` |

#### Pending Status

```html
<span class="px-2 py-1 bg-yellow-100 text-yellow-800 rounded text-xs font-medium">
    Pending Review
</span>
```

| Property | Value |
|----------|-------|
| Background | `bg-yellow-100` |
| Text | `text-yellow-800` |
| Pages | `ads/dashboard.html` |

#### Rejected/Failed Status

```html
<span class="px-3 py-1 bg-yellow-100 text-yellow-800 rounded-full text-sm font-semibold">
    {{ ad.get_status_display }}
</span>
```

| Property | Value |
|----------|-------|
| Shape | `rounded-full` (pill) |
| Background | `bg-yellow-100` |
| Text | `text-yellow-800` |
| Pages | `admin/review.html` |

#### Category Badge

```html
<span class="inline-flex items-center px-3 py-1 rounded-full text-sm bg-blue-100 text-blue-800">
    Electronics
    <button class="ml-2 text-blue-600 hover:text-blue-800" aria-label="Remove">×</button>
</span>
```

| Property | Value |
|----------|-------|
| Shape | `rounded-full` |
| Background | `bg-blue-100` |
| Text | `text-blue-800` |
| Pages | `filter-ui.md` (planned) |

---

## Molecular Components

### Search Bar

Combined input and button for keyword search.

```html
<form method="get" class="flex gap-2">
    <div class="relative flex-1">
        <input 
            type="search" 
            name="q" 
            placeholder="Search ads..."
            class="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            aria-label="Search listings"
        >
        <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 1114 7 7 0 01-14-14z"></path>
        </svg>
    </div>
    <button type="submit" class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium">
        Search
    </button>
</form>
```

| Property | Value |
|----------|-------|
| Height | 40px |
| Icon size | `w-5 h-5` (20px) |
| Pages | `ads/list.html` |

### Price Display

Prominent price presentation with currency.

```html
<!-- List price -->
<p class="text-blue-600 font-bold text-xl mb-2">450 BAM</p>

<!-- Detail price -->
<p class="text-blue-600 font-bold text-3xl mb-4">450 BAM</p>

<!-- With label -->
<div>
    <span class="text-sm text-gray-500">Price</span>
    <p class="text-blue-600 font-bold text-xl">450 BAM</p>
</div>
```

| Context | Size | Color |
|---------|------|-------|
| List card | `text-xl` | `text-blue-600` |
| Detail page | `text-3xl` | `text-blue-600` |

---

## Organism Components

### Ad Card (List View)

Primary listing card for search results.

```html
<article class="bg-white rounded-lg shadow hover:shadow-md transition-shadow">
    <a href="{% url 'ads:detail' ad.id %}" class="block">
        {% if ad.images.first %}
            <img 
                src="{{ ad.images.first.image_url }}" 
                alt="{{ ad.title }}"
                class="w-full h-48 object-cover rounded-t-lg"
                loading="lazy"
            >
        {% else %}
            <div class="w-full h-48 bg-gray-200 rounded-t-lg flex items-center justify-center">
                <span class="text-gray-500 text-sm">No image</span>
            </div>
        {% endif %}
        
        <div class="p-4">
            <h2 class="font-semibold text-lg text-gray-800 mb-2 line-clamp-2">
                {{ ad.title }}
            </h2>
            
            {% if ad.price %}
                <p class="text-blue-600 font-bold text-xl mb-2">
                    {{ ad.price }} BAM
                </p>
            {% endif %}
            
            <p class="text-sm text-gray-600 mb-3 line-clamp-3">
                {{ ad.description }}
            </p>
            
            <div class="flex justify-between items-center text-xs text-gray-500">
                <span>{{ ad.city.get_name|default:ad.city.name }}</span>
                <span>{{ ad.category.get_name|default:ad.category.name }}</span>
                <time datetime="{{ ad.published_at|date:'Y-m-d' }}">
                    {{ ad.published_at|date:'M d' }}
                </time>
            </div>
        </div>
    </a>
</article>
```

| Property | Value |
|----------|-------|
| Image | `h-48` (192px), 16:9 ratio |
| Padding | `p-4` |
| Radius | `rounded-lg` (except image top) |
| Shadow | `shadow` → `hover:shadow-md` |
| Pages | `ads/partials/ad_list.html` |

### Ad Card (Detail View)

Full-width single ad display.

```html
<article class="bg-white rounded-lg shadow overflow-hidden">
    <!-- Image Gallery -->
    <div class="grid grid-cols-1 {% if ad.images.count > 1 %}md:grid-cols-2{% endif %} gap-2 p-4">
        {% for image in ad.images.all %}
            <img 
                src="{{ image.image_url }}" 
                alt="Photo {{ forloop.counter }} for {{ ad.title }}"
                class="w-full {% if ad.images.count == 1 %}max-h-96{% else %}h-64{% endif %} object-cover rounded-lg"
            >
        {% endfor %}
    </div>
    
    <!-- Content -->
    <div class="p-6">
        <h1 class="text-3xl font-bold text-gray-800 mb-4">{{ ad.title }}</h1>
        
        {% if ad.price %}
            <p class="text-blue-600 font-bold text-3xl mb-4">{{ ad.price }} BAM</p>
        {% endif %}
        
        <div class="prose max-w-none mb-6">
            <p class="text-gray-700 whitespace-pre-wrap">{{ ad.description }}</p>
        </div>
        
        <div class="flex flex-wrap gap-4 text-sm text-gray-600 border-t pt-4">
            <div><span class="font-medium">Location:</span> {{ ad.city.get_name|default:ad.city.name }}</div>
            <div><span class="font-medium">Category:</span> {{ ad.category.get_name|default:ad.category.name }}</div>
            <div><time datetime="{{ ad.published_at|date:'Y-m-d' }}">Published: {{ ad.published_at|date:'M d, Y' }}</time></div>
        </div>
    </div>
    
    <!-- Contact Seller -->
    <div class="p-6 border-t bg-gray-50">
        {% if ad|can_contact %}
            <a href="https://t.me/{{ settings.BOT_USERNAME }}?start=contact_{{ ad.id }}" class="inline-block px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2">
                Contact Seller
            </a>
            <p class="text-xs text-gray-500 mt-2">Message sent through Telegram bot</p>
        {% else %}
            <button type="button" disabled class="px-6 py-3 bg-gray-300 text-white rounded-lg font-medium cursor-not-allowed">
                Contact Seller
            </button>
            <p class="text-xs text-gray-500 mt-2">Seller unavailable for contact</p>
        {% endif %}
    </div>
</article>
```

| Property | Value |
|----------|-------|
| Padding | `p-6` |
| Image | 1-2 column grid responsive |
| Pages | `ads/detail.html` |

### Header Navigation

Site-wide navigation with consistent branding.

```html
<header class="bg-white shadow-sm border-b">
    <div class="container mx-auto px-4 py-4">
        <div class="flex items-center justify-between">
            <h1 class="text-2xl font-bold text-gray-800">
                <a href="/" class="hover:text-gray-600">Mko Bazuna</a>
            </h1>
            
            <nav class="flex items-center gap-4">
                <a href="{% url 'ads:dashboard' %}" class="text-sm text-gray-600 hover:text-gray-800 transition-colors">
                    Dashboard
                </a>
                <a href="{% url 'users:logout' %}" class="text-sm text-gray-600 hover:text-red-600 transition-colors">
                    Logout
                </a>
            </nav>
        </div>
    </div>
</header>
```

| Property | Value |
|----------|-------|
| Background | `bg-white` |
| Height | ~64px (`py-4`) |
| Shadow | `shadow-sm border-b` |
| Pages | All templates |

### Pagination Controls

HTMX-powered page navigation.

```html
<nav class="mt-8 flex justify-center gap-1" aria-label="Page navigation">
    {% if page_obj.has_previous %}
        <a href="?page=1" 
           hx-get="?page=1" 
           hx-target="#ad-list" 
           hx-swap="innerHTML"
           class="px-3 py-2 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50">
            ««
        </a>
        <a href="?page={{ page_obj.previous_page_number }}" 
           class="px-3 py-2 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50">
            «
        </a>
    {% endif %}
    
    <!-- Page numbers -->
    {% for page_num in page_obj.paginator.page_range %}
        {% if page_num == page_obj.number %}
            <span class="px-3 py-2 rounded-lg text-sm font-medium text-white bg-blue-600" aria-current="page">
                {{ page_num }}
            </span>
        {% elif page_num > page_obj.number|add:'-3' and page_num < page_obj.number|add:'3' %}
            <a href="?page={{ page_num }}" 
               class="px-3 py-2 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50">
                {{ page_num }}
            </a>
        {% endif %}
    {% endfor %}
    
    {% if page_obj.has_next %}
        <a href="?page={{ page_obj.next_page_number }}" 
           class="px-3 py-2 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50">
            »
        </a>
        <a href="?page={{ page_obj.paginator.num_pages }}" 
           class="px-3 py-2 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50">
            »»
        </a>
    {% endif %}
</nav>
```

| Property | Value |
|----------|-------|
| Gap | `gap-1` (4px) |
| Active | `bg-blue-600 text-white` |
| Pages | `ads/partials/ad_list.html` |

### Consent Banner

Privacy consent collection at page bottom.

```html
<div id="consent-banner" class="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 shadow-lg z-50" role="dialog" aria-live="polite" aria-label="Privacy consent">
    <div class="container mx-auto px-4 py-4 flex flex-col sm:flex-row items-center justify-between gap-4">
        <div class="text-sm text-gray-700">
            <p>
                This site uses cookies for essential functionality and analytics. 
                By accepting, you consent to all processing. You can still browse ads without accepting.
            </p>
            <p class="text-xs text-gray-500 mt-1">
                <a href="/privacy/" class="underline hover:text-gray-800 transition-colors">Privacy details</a>
            </p>
        </div>
        
        <div class="flex gap-2">
            <form method="post" action="{% url 'consent:accept' %}" class="inline">
                {% csrf_token %}
                <button type="submit" class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500">
                    Accept
                </button>
            </form>
            <form method="post" action="{% url 'consent:decline' %}" class="inline">
                {% csrf_token %}
                <button type="submit" class="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 font-medium text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-gray-500">
                    Decline (Browse-only)
                </button>
            </form>
        </div>
    </div>
</div>
```

| Property | Value |
|----------|-------|
| Position | Fixed bottom |
| Background | `bg-white` |
| Border | `border-t border-gray-200` |
| Shadow | `shadow-lg` |

### Language Switcher

Multi-language interface for Russian, Bosnian, and English content.

```html
<div class="relative inline-block">
    <button type="button" class="px-3 py-2 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 font-medium text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 flex items-center gap-1" aria-label="Language">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5h12M9 3v2m0 4v10m4-10v6m4-2h-4m4-2h-4"></path>
        </svg>
        <span id="current-lang" class="lang-flag ru">{{ LANGUAGE_CODE|default:'ru' }}</span>
    </button>
    
    <div class="absolute right-0 mt-2 w-48 bg-white border border-gray-200 rounded-lg shadow-lg z-50 hidden" id="lang-menu">
        <div class="py-1">
            <a href="?lang=ru" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 hover:text-gray-900 language-link" data-lang="ru">
                <span class="inline-block w-4 h-4 mr-2 flag-icon flag-ru"></span>
                Russian
            </a>
            <a href="?lang=bs" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 hover:text-gray-900 language-link" data-lang="bs">
                <span class="inline-block w-4 h-4 mr-2 flag-icon flag-bs"></span>
                Bosnian
            </a>
            <a href="?lang=en" class="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 hover:text-gray-900 language-link" data-lang="en">
                <span class="inline-block w-4 h-4 mr-2 flag-icon flag-en"></span>
                English
            </a>
        </div>
    </div>
</div>

<script>
document.addEventListener('DOMContentLoaded', function() {
    // Toggle language menu
    document.querySelector('.language-link').addEventListener('click', function(e) {
        e.preventDefault();
        const lang = this.getAttribute('data-lang');
        document.cookie = 'lang_pref=' + lang + '; path=/; max-age=31536000';
        window.location.href = this.href;
    });
});
</script>
```

| Property | Value |
|----------|-------|
| Position | `relative inline-block` |
| Background | `bg-white` |
| Border | `border border-gray-200` |
| Shadow | `shadow-lg` |
| Cookie | Sets `lang_pref` cookie |
| Middleware | Uses `LanguagePreMiddleware` |
| Pages | All templates (header navigation) |

## Component Usage Matrix

| Component | Pages Used | Template | Status |
|-----------|------------|----------|--------|
| Primary Button | All | `edit.html`, `detail.html`, `dashboard.html`, `admin/review.html` | ✅ Implemented |
| Success Button | Admin | `admin/review.html` | ✅ Implemented |
| Danger Button | Admin | `admin/review.html` | ✅ Implemented |
| Secondary Button | Edit, Dashboard | `edit.html`, `dashboard.html` | ✅ Implemented |
| Icon Button | Admin | `admin/review.html` | ✅ Implemented |
| Form Input | Edit | `ads/edit.html` | ✅ Implemented |
| Badge | Dashboard, Admin | `dashboard.html`, `review.html` | ✅ Implemented |
| Ad Card (List) | List, Home | `ads/partials/ad_list.html` | ✅ Implemented |
| Ad Card (Detail) | Detail | `ads/detail.html` | ✅ Implemented |
| Search Bar | List, Home | `ads/list.html` | ✅ Implemented |
| Header | All | All templates | ✅ Implemented |
| Pagination | List | `ads/partials/ad_list.html` | ✅ Implemented |
| Consent Banner | All | `components/consent_banner.html` | ✅ Implemented |
| Language Switcher | All | `components/language_switcher.html` | ✅ Implemented |
| Filter Sidebar | Planned | `filter-ui.md` | 📋 Documented |
| Mobile Drawer | Planned | `filter-ui.md` | 📋 Documented |