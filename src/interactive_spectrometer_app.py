
import os, io
import numpy as np
import cv2
import yaml
import streamlit as st
import matplotlib.pyplot as plt

st.set_page_config(page_title="Interactive Educational Spectrometer", layout="wide")
EPS = 1e-9

# -------- Helpers --------
def load_yaml_bytes(yaml_bytes):
    try:
        text = yaml_bytes.decode("utf-8")
    except Exception:
        text = yaml_bytes.decode("latin-1")
    data = yaml.safe_load(text) or {}
    return data

def map_pixels_to_nm(xs, coeffs):
    coeffs = np.array(coeffs, dtype=float)
    return np.polyval(coeffs[::-1], xs)

def extract_spectrum(image_bgr, y0, y1):
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    y0 = max(0, int(y0))
    y1 = min(h, int(y1)) if y1 >= 0 else h
    if y0 >= y1:
        y0, y1 = 0, h
    roi = gray[y0:y1, :]
    spec = roi.mean(axis=0)
    spec = (spec - spec.min()) / max(EPS, (spec.max() - spec.min()))
    return spec, (y0, y1)

def draw_roi_preview(image_bgr, y0, y1):
    img = image_bgr.copy()
    h, w, _ = img.shape
    y0p = max(0, min(h-1, int(y0)))
    y1p = max(0, min(h-1, int(y1))) if y1 >= 0 else h-1
    if y0p > y1p:
        y0p, y1p = 0, h-1
    cv2.rectangle(img, (0, y0p), (w-1, y1p), (0, 255, 0), 2)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

def save_csv_png(out_dir, x, y, csv_name, png_name, xlab, ylab, title):
    os.makedirs(out_dir, exist_ok=True)
    # CSV
    import csv
    csv_path = os.path.join(out_dir, csv_name)
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([xlab, ylab])
        for a, b in zip(x, y):
            w.writerow([a, b])
    # Plot
    fig, ax = plt.subplots()
    ax.plot(x, y)
    ax.set_xlabel(xlab)
    ax.set_ylabel(ylab)
    ax.set_title(title)
    fig.tight_layout()
    png_path = os.path.join(out_dir, png_name)
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

def autocalibrate_from_frame(frame_bgr, y0, y1, degree=2):
    expected_nm = np.array([436.0, 546.0, 577.0, 579.0], dtype=float)
    spec, (ry0, ry1) = extract_spectrum(frame_bgr, y0, y1)
    xs = np.arange(len(spec), dtype=float)
    peaks = simple_find_peaks(spec, threshold=0.3, min_distance=12, max_peaks=len(expected_nm))
    if len(peaks) < 2:
        return None, (ry0, ry1), []
    deg = min(int(degree), max(1, len(peaks)-1))
    X = xs[peaks]
    E = expected_nm[:len(peaks)]
    coeffs = np.polyfit(X, E, deg=deg)[::-1]
    return coeffs.tolist(), (ry0, ry1), peaks.tolist()

def grab_frame_usb(index):
    cap = cv2.VideoCapture(int(index))
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None

# -------- UI --------
st.title("Interactive Educational Spectrometer")

with st.sidebar:
    st.header("Inputs & Settings")

    # Source selection
    source = st.radio("Source", ["Upload image", "Webcam"], index=0, help="Choose to upload a still image or capture one frame from a USB camera.")
    uploaded_img = None
    cam_index = 0
    if source == "Upload image":
        uploaded_img = st.file_uploader("Upload spectrum image (png/jpg)", type=["png","jpg","jpeg"])
    else:
        cam_index = st.number_input("USB camera index", min_value=0, value=0, step=1)

    # Calibration controls
    st.subheader("Calibration (pixel → wavelength)")
    cal_choice = st.radio("Calibration source", ["Default (identity)", "Upload YAML", "Auto-calibrate from current frame"], index=0)
    uploaded_cal = None
    if cal_choice == "Upload YAML":
        uploaded_cal = st.file_uploader("Upload calibration YAML", type=["yaml","yml"])

    poly_degree = st.number_input("Polynomial degree (for auto-cal)", min_value=1, max_value=5, value=2, step=1)

    # ROI
    st.subheader("ROI (rows to average)")
    y0 = st.number_input("y0 (top row)", value=40, step=1)
    y1 = st.number_input("y1 (bottom row; -1 = image bottom)", value=200, step=1)

    # Output folder
    out_dir = st.text_input("Output folder", value="runs/streamlit")
    os.makedirs(out_dir, exist_ok=True)

    # Reference CSV upload for absorbance
    st.subheader("Absorbance reference")
    ref_csv_upload = st.file_uploader("Upload reference CSV (wavelength_nm,intensity)", type=["csv"], help="Upload a previously saved reference CSV to compute absorbance.")

# Keep state
if "frame_bgr" not in st.session_state:
    st.session_state["frame_bgr"] = None
if "cal_coeffs" not in st.session_state:
    st.session_state["cal_coeffs"] = [0.0, 1.0, 0.0]
if "last_spectrum" not in st.session_state:
    st.session_state["last_spectrum"] = None
if "last_wavelengths" not in st.session_state:
    st.session_state["last_wavelengths"] = None

# Acquire frame
colA, colB = st.columns(2, gap="large")
with colA:
    st.subheader("1) Load or capture frame")
    if source == "Upload image":
        if uploaded_img is not None:
            img_bytes = np.frombuffer(uploaded_img.read(), np.uint8)
            frame = cv2.imdecode(img_bytes, cv2.IMREAD_COLOR)
            if frame is not None:
                st.session_state["frame_bgr"] = frame
                st.success("Image loaded.")
    else:
        if st.button("Grab webcam frame"):
            frame = grab_frame_usb(cam_index)
            if frame is None:
                st.error("No frame captured. Try another index, or close apps using the camera.")
            else:
                st.session_state["frame_bgr"] = frame
                st.success("Captured one frame from webcam.")

    frame = st.session_state.get("frame_bgr")
    if frame is not None:
        st.image(draw_roi_preview(frame, y0, y1), caption="Current frame with ROI")

with colB:
    st.subheader("2) Choose calibration")
    # Decide calibration coefficients
    coeffs = [0.0, 1.0, 0.0]
    cal_choice_local = st.session_state.get("cal_choice_local", None)
    if cal_choice_local is None:
        cal_choice_local = "Default (identity)"
    if cal_choice == "Default (identity)":
        coeffs = [0.0, 1.0, 0.0]
    elif cal_choice == "Upload YAML":
        if uploaded_cal is not None:
            data = load_yaml_bytes(uploaded_cal.getvalue())
            coeffs = data.get("calibration", {}).get("coeffs", [0.0, 1.0, 0.0])
            st.info(f"Loaded coeffs: {coeffs}")
        else:
            st.warning("Upload a YAML with {'calibration': {'coeffs': [...]}}.")
    else:  # auto-calibrate
        if st.button("Run auto-calibration from current frame"):
            frame = st.session_state.get("frame_bgr")
            if frame is None:
                st.warning("Load/capture a frame first.")
            else:
                cal, (ry0, ry1), peaks = autocalibrate_from_frame(frame, y0, y1, degree=poly_degree)
                if cal is None:
                    st.error("Auto-calibration failed (need ≥2 strong peaks). Try adjusting ROI or exposure.")
                else:
                    coeffs = cal
                    y0, y1 = ry0, ry1
                    st.success(f"Auto-cal OK: coeffs={coeffs}; ROI=({ry0},{ry1}); peaks={peaks}")
    st.session_state["cal_coeffs"] = coeffs

st.markdown("---")
st.subheader("3) Process")

col1, col2, col3 = st.columns(3)
with col1:
    if st.button("Extract spectrum (CSV+PNG)"):
        frame = st.session_state.get("frame_bgr")
        if frame is None:
            st.warning("Load/capture a frame first.")
        else:
            spec, (ry0, ry1) = extract_spectrum(frame, y0, y1)
            xs = np.arange(len(spec))
            lam = map_pixels_to_nm(xs, st.session_state["cal_coeffs"])
            st.session_state["last_spectrum"] = spec
            st.session_state["last_wavelengths"] = lam
            csvp, pngp = save_csv_png(out_dir, lam, spec, "spectrum_image.csv", "spectrum_image.png",
                                      "wavelength_nm", "intensity", "Spectrum")
            st.success(f"Saved: {csvp} and {pngp}")
            fig, ax = plt.subplots()
            ax.plot(lam, spec); ax.set_xlabel("Wavelength (nm)"); ax.set_ylabel("Normalized intensity"); ax.set_title("Spectrum")
            st.pyplot(fig)

with col2:
    if st.button("Save as reference (CSV+PNG)"):
        if st.session_state.get("last_spectrum") is None or st.session_state.get("last_wavelengths") is None:
            st.warning("Extract the spectrum first.")
        else:
            lam = st.session_state["last_wavelengths"]
            spec = st.session_state["last_spectrum"]
            csvp, pngp = save_csv_png(out_dir, lam, spec, "reference_image.csv", "reference_image.png",
                                      "wavelength_nm", "intensity", "Reference")
            st.success(f"Saved reference: {csvp} and {pngp}")

with col3:
    if st.button("Compute absorbance (CSV+PNG)"):
        if st.session_state.get("last_spectrum") is None or st.session_state.get("last_wavelengths") is None:
            st.warning("Extract the sample spectrum first.")
        else:
            if ref_csv_upload is None:
                st.warning("Upload a reference CSV (wavelength_nm,intensity) in the sidebar.")
            else:
                try:
                    ref_bytes = ref_csv_upload.getvalue()
                    ref_text = ref_bytes.decode("utf-8", errors="ignore")
                    import io as _io
                    r = np.genfromtxt(_io.StringIO(ref_text), delimiter=",", names=True, dtype=float)
                    cols = r.dtype.names
                    if "wavelength_nm" not in cols or "intensity" not in cols:
                        st.error("Reference CSV must have headers: wavelength_nm,intensity")
                    else:
                        lam = st.session_state["last_wavelengths"]
                        spec = st.session_state["last_spectrum"]
                        ref_lam, ref_I = r["wavelength_nm"], r["intensity"]
                        ref_on = np.interp(lam, ref_lam, ref_I, left=ref_I[0], right=ref_I[-1])
                        A = -np.log10((spec + EPS) / (ref_on + EPS))
                        csvp, pngp = save_csv_png(out_dir, lam, A, "absorbance_image.csv", "absorbance_image.png",
                                                  "wavelength_nm", "absorbance", "Absorbance")
                        st.success(f"Saved absorbance: {csvp} and {pngp}")
                        fig, ax = plt.subplots()
                        ax.plot(lam, A); ax.set_xlabel("Wavelength (nm)"); ax.set_ylabel("Absorbance A(λ)"); ax.set_title("Absorbance")
                        st.pyplot(fig)
                except Exception as e:
                    st.error(f"Failed to read reference CSV: {e}")

st.markdown("---")
st.caption("Tip: Use a CFL/Hg lamp for auto‑calibration (peaks near 436, 546, 577, 579 nm). Keep cuvette and ROI identical for reference and sample.")
