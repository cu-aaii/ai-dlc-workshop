import { AppRoute } from './app.routes';

export const AdminRoutes: AppRoute[] = [
  {
    path: '',
    redirectTo: 'dashboard',
    pathMatch: 'full',
    data: { menu: [] },
  },
  {
    path: 'dashboard',
    pathMatch: 'full',
    loadComponent: () =>
      import('./features/admin/dashboard/dashboard.component').then(
        (m) => m.DashboardComponent,
      ),
    data: {
      menu: ['admin'],
      icon: 'dashboard',
      title: 'Dashboard',
      path: 'admin/dashboard',
    },
    title: 'Dashboard',
  },
  {
    path: 'settings',
    pathMatch: 'full',
    loadComponent: () =>
      import('./features/admin/settings/settings.component').then(
        (m) => m.SettingsComponent,
      ),
    data: {
      menu: ['admin'],
      icon: 'settings',
      title: 'Settings',
      path: 'admin/settings',
    },
    title: 'Settings',
  },
  {
    path: 'documentation',
    pathMatch: 'full',
    loadComponent: () =>
      import('./features/admin/documentation/documentation.component').then(
        (m) => m.DocumentationComponent,
      ),
    data: {
      menu: ['admin'],
      icon: 'description',
      title: 'Documentation',
      path: 'admin/documentation',
    },
    title: 'Documentation',
  },
];
