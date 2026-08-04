import { Component } from '@angular/core';

@Component({
  selector: 'app-implementation-plan',
  templateUrl: './implementation-plan.component.html',
  styleUrls: ['./implementation-plan.component.scss'],
})
export class ImplementationPlanComponent {
  phases = [
    { num: 1, title: 'Design deliverables', status: 'done', detail: 'style-guide.html, component-library.html (shipped for review).' },
    { num: 2, title: 'Theme port', status: 'in-progress', detail: 'SCSS tokens, Typekit link, shared chrome/card components, validated against component-library.html. This demo is a scoped slice of this phase.' },
    { num: 3, title: 'Data layer', status: 'todo', detail: 'Entities, import:wp script (incl. asset downloader), run it, spot-check row/asset counts against the live site.' },
    { num: 4, title: 'Server GET modules', status: 'todo', detail: 'blog, projects, events, people, tools — GET-only routes, no auth.' },
    { num: 5, title: 'Public pages', status: 'partial', detail: 'Build + wire into app.routes.ts in nav order: Home → Blog → Projects → Events → People → Tools → About → Get Involved. This demo ships a static-only Home.' },
    { num: 6, title: 'Full nav wiring', status: 'todo', detail: 'Replace root redirect, 404 handling.' },
    { num: 7, title: 'QA pass', status: 'todo', detail: 'Full verification pass across all pages.' },
  ];

  pageInventory = [
    { wpPage: 'Home', route: '/', menu: 'n/a (root)' },
    { wpPage: 'About Us ▾ Hub Model', route: '/about', menu: 'main' },
    { wpPage: 'About Us ▾ People', route: '/people', menu: 'main' },
    { wpPage: 'Blog (list + post)', route: '/blog, /blog/:slug', menu: 'main' },
    { wpPage: 'Tools & Resources', route: '/tools', menu: 'main' },
    { wpPage: 'Projects ▾ Catalog', route: '/projects, /projects/:slug', menu: 'main' },
    { wpPage: 'Projects ▾ Workflow', route: '/project-workflow', menu: 'main' },
    { wpPage: 'Workshops & Events', route: '/events, /events/:slug', menu: 'main' },
    { wpPage: 'Get Involved', route: '/get-involved', menu: 'main' },
  ];

  contentTypes = [
    { type: 'Blog posts', endpoint: 'wp/v2/posts or ailab/v1/posts', notes: 'title, date, excerpt, content_html, featured image, categories' },
    { type: 'Projects', endpoint: 'ailab/v1/projects', notes: 'title, content_html, cohort/date, permalink' },
    { type: 'Events', endpoint: 'ailab/v1/events', notes: 'title, date, content_html (location/speakers in body)' },
    { type: 'People', endpoint: 'ailab/v1/people', notes: 'name, title, affiliation, college, email, socials — featured_image often null' },
    { type: 'Tools', endpoint: 'ailab/v1/tools', notes: 'title, content_html — audience/type inferred from copy' },
  ];
}
