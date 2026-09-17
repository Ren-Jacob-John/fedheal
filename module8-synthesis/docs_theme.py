"""
FedHeal custom API docs theme — "Hybrid Minimalism x Glassmorphism".

Drop-in replacement for FastAPI's default Swagger UI at /docs. Construct
the FastAPI app with `docs_url=None`, then call `mount_custom_docs(app, ...)`
to register a restyled /docs route. It reuses the same OpenAPI schema and
the same Swagger UI JS engine (loaded from CDN) — only the CSS shell around
it changes, so every endpoint, schema, and "Try it out" call still works
exactly as before.

accent  — the module's signature color (hex). Each FedHeal service gets
          its own accent so operators can tell services apart at a glance,
          while everything else (layout, glass panels, typography) stays
          identical across module1 / module2 / module7.
"""
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

SWAGGER_JS_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"
SWAGGER_PRESET_JS_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-standalone-preset.js"
SWAGGER_BASE_CSS_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"
FONT_URL = (
    "https://fonts.googleapis.com/css2?"
    "family=Inter:wght@400;500;600;700;800&"
    "family=JetBrains+Mono:wght@400;500&display=swap"
)


def _glass_css(accent: str, accent_soft: str) -> str:
    return f"""
    :root {{
      --accent: {accent};
      --accent-soft: {accent_soft};
      --glass-bg: rgba(255, 255, 255, 0.55);
      --glass-bg-strong: rgba(255, 255, 255, 0.72);
      --glass-border: rgba(255, 255, 255, 0.55);
      --ink: #1b1f2a;
      --ink-muted: #5c6270;
      --ink-faint: #8a90a0;
      --radius-lg: 18px;
      --radius-md: 12px;
      --radius-sm: 8px;
      --shadow-glass: 0 8px 32px rgba(31, 38, 78, 0.08), 0 1.5px 4px rgba(31, 38, 78, 0.05);
    }}

    * {{ box-sizing: border-box; }}

    html {{ scroll-behavior: smooth; }}

    body {{
      margin: 0;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 8% 8%, {accent_soft} 0%, transparent 40%),
        radial-gradient(circle at 92% 18%, #e9d8ff 0%, transparent 38%),
        radial-gradient(circle at 25% 90%, #d8f0ff 0%, transparent 42%),
        linear-gradient(180deg, #f7f8fc 0%, #eef0f7 100%);
      background-attachment: fixed;
      min-height: 100vh;
    }}

    ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
    ::-webkit-scrollbar-thumb {{ background: rgba(31,38,78,0.18); border-radius: 8px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}

    .swagger-ui {{ font-family: 'Inter', sans-serif; }}

    /* ---------- Chrome cleanup ---------- */
    .swagger-ui .topbar {{ display: none; }}
    .swagger-ui .scheme-container {{
      background: transparent;
      box-shadow: none;
      padding: 0;
    }}

    /* ---------- Page shell ---------- */
    .swagger-ui .wrapper {{
      max-width: 1040px;
      padding: 48px 24px 96px;
    }}

    /* ---------- Header / info card ---------- */
    .swagger-ui .information-container {{ padding: 0 0 24px; }}
    .swagger-ui .info {{
      margin: 0 0 32px;
      background: var(--glass-bg-strong);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid var(--glass-border);
      border-radius: var(--radius-lg);
      box-shadow: var(--shadow-glass);
      padding: 32px 36px;
    }}
    .swagger-ui .info .title {{
      font-family: 'Inter', sans-serif;
      font-weight: 800;
      font-size: 28px;
      letter-spacing: -0.02em;
      color: var(--ink);
    }}
    .swagger-ui .info .title small {{
      background: var(--accent);
      border-radius: 999px;
      vertical-align: middle;
    }}
    .swagger-ui .info__contact,
    .swagger-ui .info li,
    .swagger-ui .info p {{
      color: var(--ink-muted);
      font-size: 14.5px;
      line-height: 1.6;
    }}
    .swagger-ui .info a {{ color: var(--accent); font-weight: 600; }}

    /* ---------- Section / tag headers ---------- */
    .swagger-ui .opblock-tag {{
      border-bottom: 1px solid rgba(31,38,78,0.08);
      font-family: 'Inter', sans-serif;
      font-weight: 700;
      font-size: 15px;
      letter-spacing: 0.02em;
      text-transform: uppercase;
      color: var(--ink-muted);
      padding: 14px 6px;
      margin: 28px 0 12px;
    }}
    .swagger-ui .opblock-tag:hover {{ background: transparent; }}
    .swagger-ui .opblock-tag small {{ color: var(--ink-faint); text-transform: none; letter-spacing: 0; }}

    /* ---------- Endpoint (opblock) cards — the core glass panels ---------- */
    .swagger-ui .opblock {{
      background: var(--glass-bg);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--glass-border);
      border-radius: var(--radius-md);
      box-shadow: var(--shadow-glass);
      margin: 0 0 14px;
      transition: transform 0.18s ease, box-shadow 0.18s ease;
    }}
    .swagger-ui .opblock:hover {{
      transform: translateY(-2px);
      box-shadow: 0 14px 36px rgba(31, 38, 78, 0.12);
    }}
    .swagger-ui .opblock .opblock-summary {{
      border: none;
      padding: 6px 14px;
    }}
    .swagger-ui .opblock .opblock-summary-method {{
      border-radius: var(--radius-sm);
      font-weight: 700;
      font-size: 12px;
      min-width: 74px;
      text-align: center;
      box-shadow: none;
    }}
    .swagger-ui .opblock .opblock-summary-path {{
      font-family: 'JetBrains Mono', monospace;
      font-weight: 600;
      font-size: 14px;
      color: var(--ink);
    }}
    .swagger-ui .opblock .opblock-summary-description {{
      color: var(--ink-muted);
      font-size: 13px;
    }}

    /* method colors — soft/pastel rather than saturated defaults */
    .swagger-ui .opblock.opblock-get {{ border-left: 4px solid #7aa8ff; }}
    .swagger-ui .opblock.opblock-get .opblock-summary-method {{ background: #eaf1ff; color: #3061d6; }}
    .swagger-ui .opblock.opblock-post {{ border-left: 4px solid #6bd6a8; }}
    .swagger-ui .opblock.opblock-post .opblock-summary-method {{ background: #e8f9f0; color: #1f9d63; }}
    .swagger-ui .opblock.opblock-put {{ border-left: 4px solid #f2c265; }}
    .swagger-ui .opblock.opblock-put .opblock-summary-method {{ background: #fdf3e2; color: #a86a10; }}
    .swagger-ui .opblock.opblock-patch {{ border-left: 4px solid #c9a3f5; }}
    .swagger-ui .opblock.opblock-patch .opblock-summary-method {{ background: #f4ecfe; color: #7c3fc9; }}
    .swagger-ui .opblock.opblock-delete {{ border-left: 4px solid #f2938a; }}
    .swagger-ui .opblock.opblock-delete .opblock-summary-method {{ background: #fdecea; color: #c43d31; }}

    .swagger-ui .opblock .opblock-body {{
      background: transparent;
      border-top: 1px solid rgba(31,38,78,0.06);
    }}
    .swagger-ui .opblock-description-wrapper p,
    .swagger-ui .opblock-external-docs-wrapper p {{
      color: var(--ink-muted);
    }}

    /* ---------- Buttons ---------- */
    .swagger-ui .btn {{
      border-radius: 999px;
      font-weight: 600;
      font-size: 13px;
      border: 1px solid rgba(31,38,78,0.12);
      background: rgba(255,255,255,0.6);
      backdrop-filter: blur(6px);
      box-shadow: none;
      transition: all 0.15s ease;
    }}
    .swagger-ui .btn:hover {{ transform: translateY(-1px); }}
    .swagger-ui .btn.execute {{
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }}
    .swagger-ui .btn.authorize {{
      background: var(--glass-bg-strong);
      border-color: var(--accent);
      color: var(--accent);
    }}
    .swagger-ui .btn.authorize svg {{ fill: var(--accent); }}

    /* ---------- Parameters / models / responses ---------- */
    .swagger-ui table {{ border-collapse: collapse; }}
    .swagger-ui .parameters-col_description input[type=text],
    .swagger-ui textarea {{
      border-radius: var(--radius-sm);
      border: 1px solid rgba(31,38,78,0.15);
      background: rgba(255,255,255,0.7);
      font-family: 'JetBrains Mono', monospace;
      font-size: 13px;
    }}
    .swagger-ui .parameter__name {{ font-weight: 600; color: var(--ink); }}
    .swagger-ui .parameter__type {{ color: var(--ink-faint); }}
    .swagger-ui .response-col_status {{ font-weight: 700; }}

    .swagger-ui .model-box,
    .swagger-ui section.models {{
      background: var(--glass-bg);
      backdrop-filter: blur(16px);
      border: 1px solid var(--glass-border);
      border-radius: var(--radius-md);
      box-shadow: var(--shadow-glass);
    }}
    .swagger-ui section.models {{ margin-top: 24px; }}
    .swagger-ui section.models .model-container {{
      background: transparent;
      border-radius: var(--radius-sm);
    }}
    .swagger-ui .model {{ font-family: 'JetBrains Mono', monospace; font-size: 13px; }}

    .swagger-ui .highlight-code, .swagger-ui .microlight {{
      background: #1b1f2a !important;
      border-radius: var(--radius-sm);
    }}

    /* ---------- Misc polish ---------- */
    .swagger-ui .opblock-tag-section {{ margin-bottom: 4px; }}
    .swagger-ui select {{
      border-radius: var(--radius-sm);
      border: 1px solid rgba(31,38,78,0.15);
      background: rgba(255,255,255,0.7);
    }}
    .swagger-ui .filter .operation-filter-input {{
      border-radius: 999px;
      border: 1px solid rgba(31,38,78,0.15);
      padding: 8px 16px;
    }}
    """


def mount_custom_docs(app: FastAPI, accent: str = "#5b7cfa", accent_soft: str = "#dfe7ff") -> None:
    """Register a glassmorphism-themed /docs route on `app`.

    Call this AFTER `app = FastAPI(..., docs_url=None)` — disabling the
    default docs_url is what frees up the /docs path for this route.
    """
    title = f"{app.title} — Docs"
    openapi_url = app.openapi_url

    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui_html() -> HTMLResponse:
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <link rel="stylesheet" href="{SWAGGER_BASE_CSS_URL}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="{FONT_URL}" rel="stylesheet">
  <style>{_glass_css(accent, accent_soft)}</style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="{SWAGGER_JS_URL}"></script>
  <script src="{SWAGGER_PRESET_JS_URL}"></script>
  <script>
    window.onload = () => {{
      window.ui = SwaggerUIBundle({{
        url: "{openapi_url}",
        dom_id: "#swagger-ui",
        presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
        layout: "BaseLayout",
        deepLinking: true,
        displayRequestDuration: true,
        docExpansion: "list",
        filter: true,
        persistAuthorization: true,
        tryItOutEnabled: true,
      }});
    }};
  </script>
</body>
</html>"""
        return HTMLResponse(html)
