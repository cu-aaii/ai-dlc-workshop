import { Route } from '@angular/router';

export interface RouteData {
  menu: string[];
  title?: string;
  icon?: string;
  path?: string;
  [key: string]: any;
}

export interface AppRoute extends Route {
  data: RouteData;
  children?: AppRoute[];
}

export const routes: AppRoute[] = [
  {
    path: '',
    pathMatch: 'full',
    loadComponent: () =>
      import('./features/home/home.component').then((m) => m.HomeComponent),
    title: 'Home',
    data: { menu: ['main'] },
  },
  {
    path: 'component-library',
    loadComponent: () =>
      import('./features/component-library/component-library.component').then(
        (m) => m.ComponentLibraryComponent,
      ),
    title: 'Component Library',
    data: { menu: ['main'] },
  },
  {
    path: 'style-guide',
    loadComponent: () =>
      import('./features/style-guide/style-guide.component').then(
        (m) => m.StyleGuideComponent,
      ),
    title: 'Style Guide',
    data: { menu: ['main'] },
  },
  {
    path: 'implementation-plan',
    loadComponent: () =>
      import('./features/implementation-plan/implementation-plan.component').then(
        (m) => m.ImplementationPlanComponent,
      ),
    title: 'Implementation Plan',
    data: { menu: ['main'] },
  },
  {
    path: '**',
    redirectTo: '',
    pathMatch: 'full',
    data: { menu: [] },
  },
];
