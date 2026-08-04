import { Component } from '@angular/core';

@Component({
  selector: 'app-style-guide',
  templateUrl: './style-guide.component.html',
  styleUrls: ['./style-guide.component.scss'],
})
export class StyleGuideComponent {
  spacingSizes = [
    { px: 4 },
    { px: 8 },
    { px: 16 },
    { px: 24 },
    { px: 32 },
    { px: 48 },
  ];
}
