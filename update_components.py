#!/usr/bin/env python3

with open('docs/06-design-system/components.md', 'r') as f:
    content = f.read()

# Insert Language Switcher after Consent Banner (before "## Component Usage Matrix")
consent_end = content.find('### Consent Banner')
if consent_end != -1:
    end_of_consent = content.find('\n### Component Usage Matrix', consent_end)
    if end_of_consent != -1:
        language_switcher = '''

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
| Position | Fixed bottom |
| Background | `bg-white` |
| Border | `border-t border-gray-200` |
| Shadow | `shadow-lg` |
| Language flags | Displayed with country codes (ru, bs, en) |
| Pages | All templates |'''
        updated_content = content[:end_of_consent] + language_switcher + '\n' + content[end_of_consent:]

        # Update Component Usage Matrix - add Language Switcher row
        matrix_start = updated_content.find('| Mobile Drawer | Planned | `filter-ui.md` | 📋 Documented |')
        if matrix_start != -1:
            # Find the next line after Mobile Drawer to insert Language Switcher
            lines = updated_content.split('\n')
            for i in range(matrix_start, len(lines)):
                if '| Mobile Drawer | Planned | `filter-ui.md` | 📋 Documented |' in lines[i]:
                    lines.insert(i + 1, '| Language Switcher | All | `components/language_switcher.html` | ✅ Implemented |')
                    updated_content = '\n'.join(lines)
                    break

        # Write back to file
        with open('docs/06-design-system/components.md', 'w') as f:
            f.write(updated_content)
        
        print('Successfully updated components.md')
    else:
        print('Could not find Component Usage Matrix after Consent Banner')
else:
    print('Could not find Consent Banner section')