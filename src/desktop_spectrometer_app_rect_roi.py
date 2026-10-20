
import os
import sys
import csv
import time
import math
import platform
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from dataclasses import dataclass

import numpy as np
import cv2
from PIL import Image, ImageTk
import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

EPS = 1e-9

@dataclass
class Calibration:
    poly_degree: int = 2
    coeffs: np.ndarray = None

    def map_pixels_to_nm(self, x_pixels: np.ndarray) -> np.ndarray:
        if self.coeffs is None:
            return x_pixels.astype(float)
        return np.polyval(self.coeffs[::-1], x_pixels)

def save_yaml(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        import yaml as _y
        _y.safe_dump(data, f, sort_keys=False)

def load_yaml(path):
    with open(path, "r") as f:
        import yaml as _y
        return _y.safe_load(f) or {}

def extract_spectrum_rect(image_bgr: np.ndarray, x0: int, x1: int, y0: int, y1: int):
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    x0 = max(0, int(x0))
    x1 = w if (x1 is None or int(x1) < 0) else min(w, int(x1))
    y0 = max(0, int(y0))
    y1 = h if (y1 is None or int(y1) < 0) else min(h, int(y1))
    if x0 >= x1: x0, x1 = 0, w
    if y0 >= y1: y0, y1 = 0, h
    roi = gray[y0:y1, x0:x1]
    spec = roi.mean(axis=0)
    rng = max(EPS, float(spec.max() - spec.min()))
    spec = (spec - spec.min()) / rng
    return spec, (x0, x1, y0, y1)

def save_xy_csv_png(outdir, x, y, cols, tag, title, ylabel):
    os.makedirs(outdir, exist_ok=True)
    csv_path = os.path.join(outdir, f"{tag}.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for a, b in zip(x, y):
            w.writerow([a, b])
    fig, ax = plt.subplots()
    ax.plot(x, y)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    fig.tight_layout()
    png_path = os.path.join(outdir, f"{tag}.png")
    fig.savefig(png_path, dpi=150)
    plt.close(fig)
    return csv_path, png_path

def simple_find_peaks(y, threshold=0.3, min_distance=10, max_peaks=6):
    y = np.asarray(y, dtype=float)
    cand = []
    for i in range(1, len(y)-1):
        if y[i] > y[i-1] and y[i] > y[i+1] and y[i] >= threshold:
            cand.append(i)
    cand = sorted(cand, key=lambda i: y[i], reverse=True)
    picked = []
    for i in cand:
        if all(abs(i - j) >= min_distance for j in picked):
            picked.append(i)
        if len(picked) >= max_peaks:
            break
    picked.sort()
    return np.array(picked, dtype=int)

def auto_calibrate_from_spectrum(xs, spec, degree=2):
    expected_nm = np.array([436.0, 546.0, 577.0, 579.0], dtype=float)
    peaks = simple_find_peaks(spec, threshold=0.3, min_distance=12, max_peaks=len(expected_nm))
    if len(peaks) < 2:
        return None, []
    deg = min(int(degree), max(1, len(peaks)-1))
    X = xs[peaks]
    E = expected_nm[:len(peaks)]
    coeffs = np.polyfit(X.astype(float), E.astype(float), deg=deg)[::-1]
    return coeffs.tolist(), peaks.tolist()

class SpectrometerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Educational Spectrometer — Desktop (Rectangular ROI)")
        self.geometry("1200x760")

        self.current_frame_bgr = None
        self.last_spectrum = None
        self.last_wavelengths = None
        self.reference_csv_path = None
        self.calibration = Calibration(poly_degree=2, coeffs=np.array([0.0, 1.0, 0.0], dtype=float))

        self.roi_x0 = 0
        self.roi_x1 = -1
        self.roi_y0 = 40
        self.roi_y1 = 200

        self.out_dir = os.path.join(os.getcwd(), "runs", "desktop")
        os.makedirs(self.out_dir, exist_ok=True)

        self.cap = None
        self.camera_running = False
        self.camera_index = tk.IntVar(value=0)

        self.preview_w = 720
        self.preview_h = 405
        self.preview_scale_x = 1.0
        self.preview_scale_y = 1.0
        self.drag_start = None
        self.drag_rect_id = None

        self._build_ui()
        self._update_status("Ready. Load image or start camera. Left‑drag to set rectangular ROI.")

    def _build_ui(self):
        main = ttk.Frame(self)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        left = ttk.Frame(main)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(left, width=self.preview_w, height=self.preview_h, bg="#111")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

        right = ttk.Frame(main, width=440)
        right.pack(side=tk.RIGHT, fill=tk.Y)

        src_group = ttk.LabelFrame(right, text="Source")
        src_group.pack(fill=tk.X, pady=(0,8))
        ttk.Button(src_group, text="Open Image...", command=self.on_open_image).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Label(src_group, text="Camera index:").pack(side=tk.LEFT, padx=(12,4))
        ttk.Spinbox(src_group, from_=0, to=9, width=4, textvariable=self.camera_index).pack(side=tk.LEFT, padx=2)
        ttk.Button(src_group, text="Start Camera", command=self.on_start_camera).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(src_group, text="Capture Frame", command=self.on_capture_frame).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(src_group, text="Stop Camera", command=self.on_stop_camera).pack(side=tk.LEFT, padx=4, pady=4)

        roi_group = ttk.LabelFrame(right, text="ROI (rectangle: x0:x1, y0:y1)")
        roi_group.pack(fill=tk.X, pady=(0,8))
        self.x0_var = tk.IntVar(value=self.roi_x0)
        self.x1_var = tk.IntVar(value=self.roi_x1)
        self.y0_var = tk.IntVar(value=self.roi_y0)
        self.y1_var = tk.IntVar(value=self.roi_y1)
        ttk.Label(roi_group, text="x0").grid(row=0, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(roi_group, textvariable=self.x0_var, width=8).grid(row=0, column=1, padx=4, pady=2)
        ttk.Label(roi_group, text="x1 (-1=right)").grid(row=0, column=2, sticky="e", padx=4, pady=2)
        ttk.Entry(roi_group, textvariable=self.x1_var, width=8).grid(row=0, column=3, padx=4, pady=2)
        ttk.Label(roi_group, text="y0").grid(row=1, column=0, sticky="e", padx=4, pady=2)
        ttk.Entry(roi_group, textvariable=self.y0_var, width=8).grid(row=1, column=1, padx=4, pady=2)
        ttk.Label(roi_group, text="y1 (-1=bottom)").grid(row=1, column=2, sticky="e", padx=4, pady=2)
        ttk.Entry(roi_group, textvariable=self.y1_var, width=8).grid(row=1, column=3, padx=4, pady=2)
        ttk.Button(roi_group, text="Apply ROI", command=self.on_apply_roi).grid(row=2, column=0, columnspan=4, padx=6, pady=4)

        cal_group = ttk.LabelFrame(right, text="Calibration (pixel → nm)")
        cal_group.pack(fill=tk.X, pady=(0,8))
        self.poly_deg_var = tk.IntVar(value=self.calibration.poly_degree)
        ttk.Label(cal_group, text="Degree").grid(row=0, column=0, sticky="e", padx=4, pady=2)
        ttk.Spinbox(cal_group, from_=1, to=5, width=4, textvariable=self.poly_deg_var).grid(row=0, column=1, padx=4, pady=2)
        ttk.Button(cal_group, text="Load YAML...", command=self.on_load_cal_yaml).grid(row=0, column=2, padx=4, pady=2)
        ttk.Button(cal_group, text="Save YAML...", command=self.on_save_cal_yaml).grid(row=0, column=3, padx=4, pady=2)
        ttk.Button(cal_group, text="Auto‑calibrate (CFL/Hg)", command=self.on_auto_cal).grid(row=1, column=0, columnspan=4, padx=4, pady=4)
        self.cal_label = ttk.Label(cal_group, text="Coeffs: [0.0, 1.0, 0.0]")
        self.cal_label.grid(row=2, column=0, columnspan=4, sticky="w", padx=4, pady=2)

        out_group = ttk.LabelFrame(right, text="Output")
        out_group.pack(fill=tk.X, pady=(0,8))
        self.out_var = tk.StringVar(value=self.out_dir)
        ttk.Entry(out_group, textvariable=self.out_var, width=36).pack(side=tk.LEFT, padx=4, pady=4)
        ttk.Button(out_group, text="Browse...", command=self.on_browse_outdir).pack(side=tk.LEFT, padx=4, pady=4)

        act_group = ttk.LabelFrame(right, text="Process")
        act_group.pack(fill=tk.X, pady=(0,8))
        ttk.Button(act_group, text="Extract Spectrum (CSV+PNG)", command=self.on_extract_spectrum).pack(fill=tk.X, padx=6, pady=4)
        ttk.Button(act_group, text="Save as Reference (CSV+PNG)", command=self.on_save_reference).pack(fill=tk.X, padx=6, pady=4)
        ttk.Button(act_group, text="Load Reference CSV…", command=self.on_load_reference_csv).pack(fill=tk.X, padx=6, pady=4)
        ttk.Button(act_group, text="Compute Absorbance (CSV+PNG)", command=self.on_compute_absorbance).pack(fill=tk.X, padx=6, pady=4)

        self.status = ttk.Label(self, text="Status", anchor="w")
        self.status.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=4)

    def _update_status(self, msg):
        self.status.config(text=msg)
        self.update_idletasks()

    def _show_frame_on_canvas(self, bgr):
        self.current_frame_bgr = bgr
        h, w, _ = bgr.shape
        scale = min(self.preview_w / w, self.preview_h / h)
        disp_w, disp_h = int(w * scale), int(h * scale)
        self.preview_scale_x = w / max(1, disp_w)
        self.preview_scale_y = h / max(1, disp_h)

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        rgb = cv2.resize(rgb, (disp_w, disp_h), interpolation=cv2.INTER_AREA)

        x0 = self.x0_var.get()
        x1 = self.x1_var.get()
        y0 = self.y0_var.get()
        y1 = self.y1_var.get()

        x0p = int(max(0, min(disp_w-1, (0 if x0 < 0 else x0 / self.preview_scale_x))))
        x1p = int(max(0, min(disp_w-1, (disp_w-1 if x1 < 0 else x1 / self.preview_scale_x))))
        y0p = int(max(0, min(disp_h-1, (0 if y0 < 0 else y0 / self.preview_scale_y))))
        y1p = int(max(0, min(disp_h-1, (disp_h-1 if y1 < 0 else y1 / self.preview_scale_y))))

        if x0p > x1p: x0p, x1p = x1p, x0p
        if y0p > y1p: y0p, y1p = y1p, y0p

        rgb_draw = rgb.copy()
        cv2.rectangle(rgb_draw, (x0p, y0p), (x1p, y1p), (0,255,0), 2)

        im = Image.fromarray(rgb_draw)
        self.tk_im = ImageTk.PhotoImage(im)
        self.canvas.config(width=disp_w, height=disp_h)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_im)

    def _open_png(self, path):
        try:
            if platform.system() == "Windows":
                os.startfile(path)  # type: ignore
            elif platform.system() == "Darwin":
                subprocess.run(["open", path], check=False)
            else:
                subprocess.run(["xdg-open", path], check=False)
        except Exception:
            pass

    def on_canvas_press(self, event):
        self.drag_start = (event.x, event.y)

    def on_canvas_drag(self, event):
        if self.drag_start is None:
            return
        x0, y0 = self.drag_start
        x1, y1 = event.x, event.y
        if self.drag_rect_id is not None:
            self.canvas.delete(self.drag_rect_id)
        self.drag_rect_id = self.canvas.create_rectangle(min(x0,x1), min(y0,y1),
                                                         max(x0,x1), max(y0,y1),
                                                         outline="lime", width=2)

    def on_canvas_release(self, event):
        if self.drag_start is None:
            return
        x0c, y0c = self.drag_start
        x1c, y1c = event.x, event.y
        self.drag_start = None
        if self.drag_rect_id is not None:
            self.canvas.delete(self.drag_rect_id)
            self.drag_rect_id = None

        x0p, x1p = sorted([x0c, x1c])
        y0p, y1p = sorted([y0c, y1c])
        x0_img = int(x0p * self.preview_scale_x)
        x1_img = int(x1p * self.preview_scale_x)
        y0_img = int(y0p * self.preview_scale_y)
        y1_img = int(y1p * self.preview_scale_y)

        self.x0_var.set(x0_img)
        self.x1_var.set(x1_img)
        self.y0_var.set(y0_img)
        self.y1_var.set(y1_img)

        if self.current_frame_bgr is not None:
            self._show_frame_on_canvas(self.current_frame_bgr)
        self._update_status(f"ROI set to x0={x0_img}, x1={x1_img}, y0={y0_img}, y1={y1_img}")

    def on_open_image(self):
        path = filedialog.askopenfilename(title="Open image", filetypes=[("Images", "*.png;*.jpg;*.jpeg"), ("All", "*.*")])
        if not path:
            return
        bgr = cv2.imread(path, cv2.IMREAD_COLOR)
        if bgr is None:
            messagebox.showerror("Error", "Failed to read image.")
            return
        self.on_stop_camera()
        self._show_frame_on_canvas(bgr)
        self._update_status(f"Loaded image: {os.path.basename(path)}")

    def on_start_camera(self):
        try:
            idx = int(self.camera_index.get())
        except Exception:
            idx = 0
        self.on_stop_camera()
        self.cap = cv2.VideoCapture(idx)
        if not self.cap.isOpened():
            messagebox.showerror("Camera", f"Cannot open camera index {idx}.")
            self._update_status("Camera not available.")
            self.cap = None
            return
        self.camera_running = True
        self._update_status(f"Camera started (index {idx}).")
        self.after(30, self._camera_loop)

    def _camera_loop(self):
        if not self.camera_running or self.cap is None:
            return
        ok, frame = self.cap.read()
        if ok:
            self._show_frame_on_canvas(frame)
        self.after(30, self._camera_loop)

    def on_capture_frame(self):
        if self.current_frame_bgr is None:
            messagebox.showinfo("Capture", "No frame to capture. Start camera or load image first.")
            return
        self.on_stop_camera()
        self._update_status("Frame captured (camera stopped).")

    def on_stop_camera(self):
        self.camera_running = False
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
        self.cap = None

    def on_apply_roi(self):
        if self.current_frame_bgr is not None:
            self._show_frame_on_canvas(self.current_frame_bgr)
        self._update_status(f"ROI set to x0={self.x0_var.get()}, x1={self.x1_var.get()}, y0={self.y0_var.get()}, y1={self.y1_var.get()}")

    def on_load_cal_yaml(self):
        path = filedialog.askopenfilename(title="Load calibration YAML", filetypes=[("YAML", "*.yaml;*.yml")])
        if not path:
            return
        try:
            data = load_yaml(path)
            coeffs = data.get("calibration", {}).get("coeffs", None)
            deg = data.get("calibration", {}).get("poly_degree", 2)
            if coeffs is None:
                raise ValueError("No 'calibration.coeffs' in YAML.")
            self.calibration = Calibration(poly_degree=int(deg), coeffs=np.array(coeffs, dtype=float))
            self.poly_deg_var.set(int(deg))
            self.cal_label.config(text=f"Coeffs: {list(map(lambda x: round(float(x),6), self.calibration.coeffs.tolist()))}")
            self._update_status(f"Loaded calibration from {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("YAML", f"Failed to load calibration: {e}")

    def on_save_cal_yaml(self):
        path = filedialog.asksaveasfilename(title="Save calibration YAML", defaultextension=".yaml", filetypes=[("YAML", "*.yaml")])
        if not path:
            return
        data = {
            "calibration": {
                "poly_degree": int(self.poly_deg_var.get()),
                "coeffs": [float(x) for x in (self.calibration.coeffs if self.calibration.coeffs is not None else np.array([0.0,1.0,0.0]))]
            },
            "roi": {"x0": int(self.x0_var.get()), "x1": int(self.x1_var.get()),
                    "y0": int(self.y0_var.get()), "y1": int(self.y1_var.get())}
        }
        try:
            save_yaml(path, data)
            self._update_status(f"Saved calibration to {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("YAML", f"Failed to save calibration: {e}")

    def on_auto_cal(self):
        if self.current_frame_bgr is None:
            messagebox.showinfo("Auto‑cal", "Load or capture a frame first.")
            return
        x0, x1 = int(self.x0_var.get()), int(self.x1_var.get())
        y0, y1 = int(self.y0_var.get()), int(self.y1_var.get())
        spec, (rx0, rx1, ry0, ry1) = extract_spectrum_rect(self.current_frame_bgr, x0, x1, y0, y1)
        xs = np.arange(rx0, rx1, dtype=float)
        coeffs, peaks = auto_calibrate_from_spectrum(xs, spec, degree=int(self.poly_deg_var.get()))
        if coeffs is None:
            messagebox.showerror("Auto‑cal", "Need ≥2 strong peaks. Adjust ROI/exposure and try again.")
            return
        self.calibration = Calibration(poly_degree=int(self.poly_deg_var.get()), coeffs=np.array(coeffs, dtype=float))
        self.x0_var.set(rx0); self.x1_var.set(rx1); self.y0_var.set(ry0); self.y1_var.set(ry1)
        self.cal_label.config(text=f"Coeffs: {list(map(lambda x: round(float(x),6), coeffs))}")
        self._update_status(f"Auto‑calibration OK. Peaks @ ROI columns: {peaks}")

    def _ensure_frame(self):
        if self.current_frame_bgr is None:
            messagebox.showinfo("Process", "Load/capture a frame first.")
            return False
        return True

    def _timestamped_outdir(self, base):
        t = time.strftime("%Y%m%d_%H%M%S")
        d = os.path.join(base, t)
        os.makedirs(d, exist_ok=True)
        return d

    def on_extract_spectrum(self):
        if not self._ensure_frame():
            return
        x0, x1 = int(self.x0_var.get()), int(self.x1_var.get())
        y0, y1 = int(self.y0_var.get()), int(self.y1_var.get())
        spec, (rx0, rx1, ry0, ry1) = extract_spectrum_rect(self.current_frame_bgr, x0, x1, y0, y1)
        xs = np.arange(rx0, rx1, dtype=float)
        lam = self.calibration.map_pixels_to_nm(xs)
        outdir = self._timestamped_outdir(self.out_var.get())
        csvp, pngp = save_xy_csv_png(outdir, lam, spec, ["wavelength_nm","intensity"], "spectrum_image", "Spectrum", "Normalized intensity")
        self.last_spectrum = spec
        self.last_wavelengths = lam
        self.x0_var.set(rx0); self.x1_var.set(rx1); self.y0_var.set(ry0); self.y1_var.set(ry1)
        self._update_status(f"Saved spectrum → {csvp}")
        self._open_png(pngp)

    def on_save_reference(self):
        if self.last_spectrum is None or self.last_wavelengths is None:
            messagebox.showinfo("Reference", "Extract a spectrum first.")
            return
        outdir = self._timestamped_outdir(self.out_var.get())
        csvp, pngp = save_xy_csv_png(outdir, self.last_wavelengths, self.last_spectrum,
                                     ["wavelength_nm","intensity"], "reference_image", "Reference", "Normalized intensity")
        self._update_status(f"Saved reference → {csvp}")
        self._open_png(pngp)

    def on_load_reference_csv(self):
        path = filedialog.askopenfilename(title="Load reference CSV", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            data = np.genfromtxt(path, delimiter=",", names=True, dtype=float)
            if "wavelength_nm" not in data.dtype.names or "intensity" not in data.dtype.names:
                raise ValueError("CSV must have headers: wavelength_nm,intensity")
            self.reference_csv_path = path
            self._update_status(f"Loaded reference CSV: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Reference CSV", f"Failed to load: {e}")

    def on_compute_absorbance(self):
        if not self._ensure_frame():
            return
        if self.reference_csv_path is None:
            messagebox.showinfo("Absorbance", "Load a reference CSV first.")
            return
        try:
            r = np.genfromtxt(self.reference_csv_path, delimiter=",", names=True, dtype=float)
            ref_lam, ref_I = r["wavelength_nm"], r["intensity"]
        except Exception as e:
            messagebox.showerror("Absorbance", f"Bad reference CSV: {e}")
            return
        x0, x1 = int(self.x0_var.get()), int(self.x1_var.get())
        y0, y1 = int(self.y0_var.get()), int(self.y1_var.get())
        spec, (rx0, rx1, ry0, ry1) = extract_spectrum_rect(self.current_frame_bgr, x0, x1, y0, y1)
        xs = np.arange(rx0, rx1, dtype=float)
        lam = self.calibration.map_pixels_to_nm(xs)
        ref_on = np.interp(lam, ref_lam, ref_I, left=ref_I[0], right=ref_I[-1])
        A = -np.log10((spec + EPS) / (ref_on + EPS))
        outdir = self._timestamped_outdir(self.out_var.get())
        csvp, pngp = save_xy_csv_png(outdir, lam, A, ["wavelength_nm","absorbance"], "absorbance_image", "Absorbance", "Absorbance A(λ)")
        self.x0_var.set(rx0); self.x1_var.set(rx1); self.y0_var.set(ry0); self.y1_var.set(ry1)
        self._update_status(f"Saved absorbance → {csvp}")
        self._open_png(pngp)

    def on_browse_outdir(self):
        d = filedialog.askdirectory(title="Choose output folder", mustexist=True)
        if d:
            self.out_var.set(d)

def main():
    app = SpectrometerApp()
    app.mainloop()

if __name__ == "__main__":
    main()
