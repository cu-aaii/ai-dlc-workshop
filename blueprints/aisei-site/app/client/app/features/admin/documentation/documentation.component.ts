import { Component, AfterViewInit, ElementRef } from '@angular/core';

@Component({
  selector: 'app-documentation',
  template: `
    <div class="doc-container">
      <h1>Documentation</h1>
      <p class="subtitle">Project architecture, workflows, and technical reference</p>

      <section>
        <h2>Overview</h2>
        <p>
          This project is built on the AII base template — Angular + Hono with an admin dashboard.
        </p>
      </section>

      <section>
        <h2>Architecture</h2>
        <div class="mermaid-container">
          <pre class="mermaid">
flowchart TB
    subgraph Client["Angular Client :4200"]
        UI["Admin Dashboard"]
        SVC["ClientService + HTTP"]
    end

    subgraph Server["Hono Server :4300"]
        API["REST API /api/*"]
        MW["Middleware (logger)"]
    end

    UI --> SVC
    SVC --> API
    API --> MW
          </pre>
        </div>
      </section>

      <section>
        <h2>Tech Stack</h2>
        <table>
          <tr><th>Layer</th><th>Technology</th></tr>
          <tr><td>Client</td><td>Angular 21, Material UI, standalone components</td></tr>
          <tr><td>Server</td><td>Hono, Node.js</td></tr>
          <tr><td>Build</td><td>Angular CLI, TSC, ESM-only</td></tr>
        </table>
      </section>

      <section>
        <h2>WordPress Migration</h2>
        <p>
          Rebuilding <a href="https://innovationhub.ai.cornell.edu/" target="_blank" rel="noopener">innovationhub.ai.cornell.edu</a>
          (WordPress) on this stack — same visual design, full content, no CMS or authentication on the public site.
        </p>
        <h3>Content flow</h3>
        <div class="mermaid-container">
          <pre class="mermaid">
flowchart LR
    WP["WordPress REST API<br/>ailab/v1/*"]
    IMPORT["npm run import:wp<br/>(dev-run script, not an HTTP route)"]
    DB["SQLite<br/>articles / projects / events / people / tools"]
    API["Hono GET routes<br/>/api/blog, /api/projects, ..."]
    PAGES["Angular public pages"]

    WP -- fetch --> IMPORT
    IMPORT -- upsert by slug --> DB
    DB --> API
    API --> PAGES
          </pre>
        </div>
        <h3>Key decisions</h3>
        <ul>
          <li><strong>No auth anywhere</strong> — every route the public site calls is GET-only; nothing writable is exposed.</li>
          <li><strong>Dynamic without a CMS</strong> — content updates by re-running the import script (upsert by slug), not by an admin editor.</li>
          <li><strong>Native Events module</strong> — WordPress's calendar was a 3rd-party embed and wasn't portable.</li>
          <li><strong>Cornell Typekit fonts</strong> kept as a CDN link rather than vendoring licensed font files.</li>
        </ul>
        <p>
          Full plan, page/content inventory, and design references:
          <code>docs/wp-migration/</code> (<code>implementation-plan.md</code>, <code>style-guide.html</code>, <code>component-library.html</code>).
        </p>
      </section>
    </div>
  `,
  styles: `
    :host { display: block; padding: 24px; max-width: 960px; }
    .doc-container { line-height: 1.7; }
    .subtitle { color: #666; font-size: 15px; margin-top: -8px; }
    h2 { margin-top: 32px; border-bottom: 1px solid #e0e0e0; padding-bottom: 8px; }
    h3 { margin-top: 20px; color: #333; }
    code { background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-size: 13px; }
    ul { padding-left: 24px; }
    li { margin-bottom: 4px; }
    table { width: 100%; border-collapse: collapse; margin: 12px 0; }
    th, td { border: 1px solid #e0e0e0; padding: 8px 12px; text-align: left; font-size: 14px; }
    th { background: #f5f5f5; font-weight: 500; }
    .mermaid-container { background: #fafafa; border: 1px solid #e0e0e0; border-radius: 4px; padding: 16px; margin: 12px 0; overflow-x: auto; }
    .mermaid { font-size: 14px; }
  `,
})
export class DocumentationComponent implements AfterViewInit {
  constructor(private el: ElementRef) {}

  ngAfterViewInit() {
    const nodes = this.el.nativeElement.querySelectorAll('.mermaid');
    if (!nodes.length) return;
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js';
    script.onload = () => {
      (window as any).mermaid.initialize({ startOnLoad: false, theme: 'default' });
      (window as any).mermaid.run({ nodes });
    };
    document.head.appendChild(script);
  }
}
