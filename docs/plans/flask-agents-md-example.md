# Flask

> Example output of agent-optimized AGENTS.md template applied to Flask

## Purpose
Owns: WSGI application framework - routing, request/response handling, contexts, templates, sessions, configuration
Does not own: database (use Flask-SQLAlchemy), forms (use Flask-WTF), auth (use Flask-Login)

## Design Rationale

- **Problem solved**: Django was too heavy for small apps; direct WSGI was too low-level. Flask fills the gap: minimal core that scales up via extensions.

- **Core insight**: "Microframework" means the core is tiny, but extension points are everywhere. Every major feature (sessions, JSON, templates) is pluggable. You can replace anything without forking Flask.

- **Constraints**:
  - Must work with WSGI servers (Gunicorn, uWSGI) → can't assume async
  - Must be thread-safe → led to context-local proxies (request, g, current_app)
  - Must support async without breaking sync code → `sansio/` separation, contextvars

- **Philosophy**: "Explicit is better than implicit." Flask doesn't auto-discover routes or auto-configure. You wire things up yourself, which means you understand what's happening.

## Code Map

### Find It Fast
| Looking for... | Go to |
|----------------|-------|
| Main Flask app class | `app.py:108` |
| Route decorator implementation | `sansio/scaffold.py` (base class) |
| Request/Response objects | `wrappers.py` |
| Context management (app_context, request_context) | `ctx.py` |
| Global proxies (current_app, request, g, session) | `globals.py` |
| Template rendering | `templating.py` |
| JSON serialization | `json/__init__.py` |
| Session handling | `sessions.py` |
| CLI (flask run) | `cli.py` |
| URL building (url_for) | `helpers.py` |

### Key Relationships
- `werkzeug` → `flask.sansio` → `flask` → user code (never reverse)
- `sansio/` contains async-agnostic core logic, top-level adds WSGI glue
- `Flask` extends `App` (sansio) extends `Scaffold` (routing/handlers)
- Blueprints are deferred - registered at runtime, not import time

## Public API

### Key Exports
| Export | Used By | Change Impact |
|--------|---------|---------------|
| `Flask` | All apps | Core, stable API |
| `request`, `session`, `g`, `current_app` | View functions | Proxies, rarely change |
| `Blueprint` | Large apps | Stable |
| `render_template()`, `jsonify()` | Views | Stable |
| `url_for()`, `redirect()`, `abort()` | Views, templates | Stable |

### Core Types
```python
Flask          # WSGI app - routing, config, contexts
Request        # Per-request data (args, form, json, files)
Response       # Per-response (body, headers, status)
Blueprint      # Modular route/handler registration
AppContext     # Holds app + g, pushed per request
```

## External Dependencies
| Service | Used For | Failure Mode |
|---------|----------|--------------|
| werkzeug | WSGI, routing, exceptions | Fatal - core dependency |
| jinja2 | Template rendering | render_template() fails |
| itsdangerous | Session signing | Sessions unencrypted |
| click | CLI commands | flask run unavailable |
| blinker | Signals (optional) | Signals disabled |

## Data Flow
```
HTTP Request → Flask.__call__()
    → Push AppContext (makes current_app, g available)
    → Match URL → endpoint + view_args
    → request_started signal
    → before_request handlers (can abort)
    → dispatch_request() → view_func(**view_args)
    → make_response() → Response object
    → after_request handlers
    → request_finished signal
    → Pop AppContext
→ HTTP Response
```

## Decisions
| Decision | Why | Rejected |
|----------|-----|----------|
| Werkzeug for WSGI | Mature, tested, handles routing/exceptions | Custom: too much code |
| Signed cookie sessions | Stateless, no server DB | DB sessions: more complex |
| contextvars for globals | Thread+async safe | Thread-local: not async-safe |
| LocalProxy for current_app | Transparent access, lazy | Direct context: awkward API |
| Blueprints optional | Small apps can be flat | Mandatory modules: over-engineering |
| sansio/ separation | Async-agnostic core | Mixed: harder to maintain |

## Entry Points
| Task | Start Here |
|------|------------|
| Create app | `Flask(__name__)` in `app.py` |
| Add route | `@app.route()` or `add_url_rule()` |
| Use blueprints | `Blueprint()` in `blueprints.py` → `app.register_blueprint()` |
| Handle errors | `@app.errorhandler(404)` |
| Access request data | `flask.request` proxy |
| Render templates | `render_template('name.html', **ctx)` |
| Return JSON | `jsonify({'key': 'value'})` |

## Contracts
- `request`, `session`, `g` only available inside request handler or `test_request_context()`
- `current_app`, `g` require at least `app_context()`
- Config changes after server start may not take effect
- `session.modified = True` required for nested dict changes to save
- Blueprints must be registered before first request
- `abort(404)` raises `werkzeug.exceptions.NotFound`

## Patterns

### Basic route
```python
@app.route('/hello')
def hello():
    return f'Hello, {request.args.get("name", "World")}!'
```

### Blueprint organization
```python
api = Blueprint('api', __name__, url_prefix='/api')

@api.route('/status')
def status():
    return jsonify({'ok': True})

app.register_blueprint(api)
```

### Before/after request
```python
@app.before_request
def check_auth():
    if not is_logged_in():
        abort(401)
```

## Boundaries

### Always
- Set `SECRET_KEY` before using sessions
- Use `async def` for async views (not just returning coroutine)
- Register blueprints before `app.run()`

### Never
- Modify `session['nested']['key']` without `session.modified = True`
- Access `request` outside request context
- Use lowercase config keys (`debug` vs `DEBUG`)

### Verify First
- Changing URL rules after app start → may not work

## Pitfalls
- `current_app` in function body is fine - it's a proxy resolved at call time, not definition
- `g` is request-scoped - safe to use, isolated per request
- Config keys are case-sensitive: `DEBUG` works, `debug` silently ignored
- `session['nested']['key'] = x` doesn't save - set `session.modified = True`
- `__name__` with package apps can break resource loading - use `Flask(__name__.split('.')[0])`

## Downlinks
| Area | Node | What's There |
|------|------|--------------|
| json | `json/AGENTS.md` | JSON provider pattern |
| sansio | `sansio/AGENTS.md` | Async-agnostic core |
