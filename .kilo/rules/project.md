1. **English Only**  
   All comments, logs, docstrings, error messages, and documentation must be in clear English.

2. **Production Code is King**  
   If tests conflict with architecture or business logic — fix or remove the tests. Never distort production code for tests.

3. **Strict Separation of Concerns**  
   Enforce clear boundaries between UI, API, business logic, and data layers.

4. **Single Responsibility**  
   Modules, services, components, and functions must be small and focused on one thing.

5. **Avoid Overengineering**  
   Prefer simple, obvious, and maintainable solutions over complex abstractions.

6. **Composition Over Inheritance**  
   Prefer composition in both backend and frontend.

7. **Follow Existing Patterns**  
    Respect and follow established patterns and conventions in the codebase. Do not introduce new abstractions without strong justification.   

8. **Meaningful & Consistent Naming**  
    Use clear, concise, and consistent names for files, functions, components, and variables.

9. **Type Safety Everywhere**  
   Use strict TypeScript on frontend and Pydantic v2 + type hints on backend. Share types via OpenAPI. Avoid `any` completely.

10. **StrEnum for All Constants**  
   All fixed values and settings must use `Enum` or `StrEnum` instead of dicts and lists. Keep them separately in models. 

11. **Pydantic**  
    All models and validation use Pydantic v2 (DTO/validation layer at system boundaries: bot input, settings schemas, future API). Django ORM remains the persistence layer for standard CRUD operations. 

12. **No `print()` Statements**  
    Use proper logging: `logger = logging.getLogger(__name__)`.

13. Use database migrations for all schema changes
    Database structure must be versioned and reproducible.

14. Keep documentation updated continuously
    Architecture decisions, setup instructions, and API usage must always stay current.
    
15. **Small Modules and Functions**
    Short, focused files and functions give higher ROI in maintenance — they are
    easier to edit, review, and less prone to corruption.

16. **Internationalization is part of DoD**

17. **Workspace Cleanliness**  
    Before creating any file, ask: 1) Is there an exact place for this in the task or module architecture? 2) Is it needed for project operation and future maintenance? If both are no — write only to `.ai/tmp`.

18. **RFC 9457 for API Errors**  
    Maintained APIs (new or reworked JSON endpoints and any future public API) must return errors as RFC 9457 problem documents (`application/problem+json`): standard HTTP status codes, a consistent error structure, and stable `type` tokens. Centralize error handling on both backend and frontend. The frozen legacy JSON routes (`/moderation/api/v1/bulk-action/`, `/api/search/autocomplete`, `/api/preferred-city/`, `/login/issue/` + `/login/status/`) keep their documented legacy shapes and are not retrofitted — see [`docs/01-spec/api-surface.md`](../../docs/01-spec/api-surface.md).

19. **Agent-First**
     The architecture must enable LLM coding agents to safely modify, test, debug, and refactor the application using deterministic, reproducible, and machine-readable verification. Automated verifiability is the primary goal.
