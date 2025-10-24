import { Component } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent {
  private apiURL = 'https://homevibe-angular3.onrender.com';
  title = 'image-search-frontend';
  file: File | null = null;
  preview: string | ArrayBuffer | null = null;
  loading = false;
  errorMessage = '';
  detections: any[] = []; // 👈 detected objects
  requestId: string = '';
  matches: { [id: number]: any[] } = {};  // 👈 simpler structure
  imageNaturalWidth = 1;
  imageNaturalHeight = 1;
  imageDisplayWidth = 500;
  imageDisplayHeight = 300;

  constructor(private http: HttpClient) {}

  resetApp() {
    sessionStorage.clear(); // 🧹 clear all stored data
    window.location.reload(); // 🔄 reload page with default image
  }

  ngOnInit() { // ⭐ restore preview if available in sessionStorage
    const saved = sessionStorage.getItem('uploadedImage');
    if (saved) {
      this.preview = saved;
    }

        // ⭐ restore detections if available
    const savedDetections = sessionStorage.getItem('detections');
    if (savedDetections) {
      this.detections = JSON.parse(savedDetections);
    }

    // ⭐ restore matches if available
    const savedMatches = sessionStorage.getItem('matches');
    if (savedMatches) {
      this.matches = JSON.parse(savedMatches);
    }
  }

  onImageLoad(img: HTMLImageElement) {
    this.imageNaturalWidth = img.naturalWidth;
    this.imageNaturalHeight = img.naturalHeight;

    // Get the rendered (display) size from CSS scaling
    this.imageDisplayWidth = 500;
    this.imageDisplayHeight = 300;

    console.log("Image loaded:", {
      natural: [this.imageNaturalWidth, this.imageNaturalHeight],
      display: [this.imageDisplayWidth, this.imageDisplayHeight]
  });
  }

  onFileChange(event: any) {
    if (event.target.files && event.target.files.length > 0) {
      this.file = event.target.files[0];

      // ✅ Reset state when a new file is chosen
      this.preview = null;
      this.detections = [];
      this.matches = {};
      this.errorMessage = '';

      // ⭐ clear session storage on new upload
      sessionStorage.removeItem('uploadedImage');
      sessionStorage.removeItem('detections');
      sessionStorage.removeItem('matches');

      const reader = new FileReader();
      reader.onload = () => {
        this.preview = reader.result;

        // ⭐ save preview in sessionStorage so it persists after refresh
        sessionStorage.setItem('uploadedImage', this.preview as string);

        // ✅ Automatically trigger detection once preview is ready
        this.detect();
      };
      reader.readAsDataURL(this.file as Blob);
    }
  }

  detect() {
    if (!this.file) return;
    this.loading = true;
    this.errorMessage = '';

    // 🔥 Reset before sending new request
    this.detections = [];
    this.matches = {};

    const formData = new FormData();
    formData.append('file', this.file);

    this.http.post<any>(`${this.apiURL}/api/detect`, formData).subscribe({
      next: (res) => {
        // ✅ Save requestId globally
        this.requestId = res.request_id;

        // ✅ Add cache-busting to crop URLs
        this.detections = (res.detections || []).map((d: any) => ({
          ...d,
          crop_url: `${d.crop_url}?t=${new Date().getTime()}`
        }));

        // ⭐ persist detections
        sessionStorage.setItem('detections', JSON.stringify(this.detections));

        this.loading = false;

        // Run similarity search for each detection
        setTimeout(() => {
          this.detections.forEach((d, index) => {
            if (d && d.id !== undefined) {
              setTimeout(() => this.searchCrop(this.requestId, d.id), index * 500);
            }
          });
        }, 200);
      },
      error: (err) => {
        console.error(err);
        this.errorMessage = 'Detection failed';
        this.loading = false;
      }
  });
}

  searchCrop(requestId: string, id: number) {
    this.http.get<any>(`${this.apiURL}/api/search_similar_crop/${requestId}/${id}`).subscribe({
      next: (res) => {
        if (res.error) {
          console.warn("Crop not found:", id);
          return; // skip silently
        }
        // ✅ Store matches directly by detection id
        this.matches[id] = res.matches || [];

        // ⭐ persist matches
        sessionStorage.setItem('matches', JSON.stringify(this.matches));
      },

      error: (err) => {
        console.error("Search failed for crop:", id, err);
        this.errorMessage = 'Search failed';
      }
    });
  }


  // --- Marker positioning ---
  getMarkerX(d: any): number {
    if (!d || d.x === undefined) return 0;

    const img = document.querySelector('#uploadedImg') as HTMLImageElement;
    if (!img) return 0;

    const scaleX = img.clientWidth / this.imageNaturalWidth;
    return d.x * scaleX;
  }

  getMarkerY(d: any): number {
    if (!d || d.y === undefined) return 0;

    const img = document.querySelector('#uploadedImg') as HTMLImageElement;
    if (!img) return 0;

    const scaleY = img.clientHeight / this.imageNaturalHeight;
    return d.y * scaleY;
  }

}