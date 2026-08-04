import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'lib-masthead',
  imports: [RouterLink],
  template: `
    <div class="cu-masthead">
      <a class="brand" routerLink="/">
        <small>Cornell University</small>
        <strong>AI Innovation Hub</strong>
      </a>
      <img class="seal" src="assets/cornell_seal.svg" alt="Cornell University seal">
      <button class="search-toggle" type="button" aria-label="Search">
        <span aria-hidden="true">&#128269;</span>
      </button>
    </div>
  `,
  styleUrls: ['./masthead.component.scss'],
})
export class MastheadComponent {}
