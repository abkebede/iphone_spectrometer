# Educational Spectrometer — **Desktop (Tkinter) App**
A desktop GUI (no Streamlit) for a low‑cost educational spectrometer. Open an **image** or capture a **webcam** frame, set a **vertical ROI**, apply or save **wavelength calibration**, and export **CSV + PNG** for spectrum and **absorbance**.

---

## TL;DR (Quick Start)
**Windows (Anaconda Prompt recommended)**
```powershell
conda create -n eduspec python=3.11 -y
conda activate eduspec
python -m pip install -r desktop_requirements.txt
python desktop_spectrometer_app.py
```
**macOS / Linux**
```bash
python3 -m pip install -r desktop_requirements.txt
python3 desktop_spectrometer_app.py
```

---

## Step‑by‑Step Setup (Windows)
> These steps assume the files are in `C:\Users\<you>\Documents\edu-spec\`.

1) **Open Anaconda Prompt** and activate (or create) an environment
```powershell
conda create -n eduspec python=3.11 -y
conda activate eduspec
```
2) **Verify you’re using the env’s Python**
```powershell
python -V
where python
python -c "import sys; print(sys.executable)"
```
3) **Install dependencies**
- If you have this file in the same folder:
```powershell
python -m pip install --upgrade pip
python -m pip install -r desktop_requirements.txt
```
- Or install directly:
```powershell
python -m pip install numpy opencv-python matplotlib PyYAML Pillow
```
- (Optional, conda alternative)
```powershell
conda install -n eduspec -c conda-forge numpy matplotlib pyyaml pillow opencv -y
```
4) **Run the app**
```powershell
python desktop_spectrometer_app.py
```
> If `python` opens the Microsoft Store by mistake, use the exact env interpreter:
```powershell
"%CONDA_PREFIX%\python.exe" desktop_spectrometer_app.py
```

### Step‑by‑Step Setup (macOS / Linux)
1) **Install dependencies**
```bash
python3 -m pip install --upgrade pip
python3 -m pip install -r desktop_requirements.txt
```
> If Tkinter is missing on Linux: `sudo apt-get install python3-tk`
2) **Run the app**
```bash
python3 desktop_spectrometer_app.py
```

---

## Using the App (Guided Steps)

### 1) Choose a Source
- **Open Image…** to select a PNG/JPG **or**
- **Start Camera** (set camera index if needed), then **Capture Frame** to freeze a single frame.  
  > Tip: Try index `0`, then `1` or `2` if you have multiple cameras. Close Zoom/Teams if the camera is busy.

### 2) Set the ROI (Rows to Average)
- **Mouse method:** click‑drag on the preview to draw a **green band** over the spectrum.
- **Numeric method:** enter `y0` (top) and `y1` (bottom, `-1` = image bottom) and click **Apply ROI**.

### 3) Calibrate (Pixel → Wavelength)
- **Load YAML…** if you have a saved calibration, **or**
- **Auto‑calibrate (CFL/Hg)** to fit λ(x) using bright mercury lines (~**436**, **546**, **577**, **579** nm).  
  Set **Degree** (2 is typical). After success, **Save YAML…** to reuse next time.

> You can start with the identity mapping `[0, 1, 0]` and calibrate later.

### 4) Extract Spectrum (CSV + PNG)
Click **Extract Spectrum (CSV+PNG)**. The app saves:
- `spectrum_image.csv` (columns: `wavelength_nm,intensity`)
- `spectrum_image.png` (plot), and opens the PNG.

### 5) Reference & Absorbance (Beer–Lambert)
**A(λ) = −log10(I_sample / I_ref)**
1. With **blank/solvent**, click **Extract Spectrum**, then **Save as Reference**.  
   This creates `reference_image.csv/png`.
2. For the **sample** (same geometry/ROI), click **Load Reference CSV…** and select the file from step 1.
3. Click **Compute Absorbance (CSV+PNG)** to produce `absorbance_image.csv/png`.

> Keep **cuvette position** and **ROI** identical for reference and sample. Use the same illumination/exposure.

---

## Output Files & Folders
- You choose the **Output folder** (default: `runs/desktop`).
- Each action creates a **timestamped** subfolder, for example:
```
runs/desktop/2025-11-04_14-32-10/
  spectrum_image.csv       # wavelength_nm,intensity
  spectrum_image.png
  reference_image.csv      # wavelength_nm,intensity
  reference_image.png
  absorbance_image.csv     # wavelength_nm,absorbance
  absorbance_image.png
```

---

## Troubleshooting
- **“Python was not found…” on Windows** → You used `python3`. Use `python` in Anaconda Prompt, or `"%CONDA_PREFIX%\python.exe"`.
- **`ModuleNotFoundError: cv2` / other libs** → Re‑run the **install** step inside the same environment used to launch.
- **Camera not found** → Try index 1 or 2; ensure no other app is using the webcam.
- **Auto‑calibration fails** → Need ≥2 strong peaks; adjust ROI/exposure; place a CFL/Hg lamp in frame; narrow the ROI.
- **Absorbance CSV rejected** → Headers must be exactly `wavelength_nm,intensity`.
- **Nothing saved** → Pick a writeable output folder; the app creates timestamped subfolders automatically.

---

## License & Attribution
This app is intended for teaching labs and student projects. Please cite **“Educational Spectrometer — Desktop App (v0.2.3‑desktop)”** in course materials.
