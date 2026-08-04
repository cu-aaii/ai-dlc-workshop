import { Component } from '@angular/core';
import { MastheadComponent } from '../../shared/layout/masthead/masthead.component';
import { FooterComponent } from '../../shared/layout/footer/footer.component';

@Component({
  selector: 'app-component-library',
  imports: [MastheadComponent, FooterComponent],
  templateUrl: './component-library.component.html',
  styleUrls: ['./component-library.component.scss'],
})
export class ComponentLibraryComponent {}
