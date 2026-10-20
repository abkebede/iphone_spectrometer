# Affordable Spectrometer

An open-source educational spectroscopy project developed by **Abebe Kebede, with Joshua Neal**. The repository packages Python desktop software, calibration resources, example measurements, and supporting documentation for a low-cost visible-light spectrometer.

## What the software does

The supplied Python applications support a practical image-based spectroscopy workflow:

- open a spectrum image or acquire a frame from a webcam;
- select a spectral region of interest (ROI);
- extract intensity as a function of image position;
- calibrate detector/image pixels to wavelength;
- use reference spectral lines for calibration, including CFL/Hg lines;
- export spectra as CSV and PNG files;
- save and reload calibration/configuration information; and
- calculate absorbance from sample and reference spectra using
  **A(lambda) = -log10(I_sample / I_ref)**.

The repository preserves the original scientific Python programs supplied with the project. No scientific algorithms in those source files were rewritten during repository preparation.

## Quick start

Python 3.11 is recommended.

```bash
python -m pip install -r requirements.txt
python src/desktop_spectrometer_app.py
```

For the rectangular-ROI implementation:

```bash
python src/desktop_spectrometer_app_rect_roi.py
```

On Linux, Tkinter may need to be installed separately through the operating system package manager.

## Repository structure

```text
Affordable-Spectrometer/
|-- README.md
|-- CITATION.cff
|-- requirements.txt
|-- src/                 # Python spectrometer applications
|-- docs/                # calibration/reference documentation
|-- config/              # reusable configuration files
|-- examples/runs/       # example spectrum and absorbance outputs
|-- images/              # project and instructional images
`-- legacy/              # placeholder/earlier packaged app files retained for provenance
```

## Calibration and spectrum extraction

The desktop documentation supplied with the project describes wavelength calibration from pixel position and an automatic CFL/Hg calibration workflow using prominent mercury lines near 436, 546, 577, and 579 nm. A polynomial mapping converts pixel coordinate to wavelength. See `docs/original_desktop_readme.md` for the detailed operating procedure.

## Output

The applications can generate spectrum files with wavelength and intensity columns and absorbance files derived from a reference measurement. The supplied `examples/runs/` directory contains experimental CSV and PNG outputs from the project package.

## Requirements

- NumPy
- OpenCV (`opencv-python`)
- Matplotlib
- PyYAML
- Pillow
- Tkinter (normally supplied with Python on Windows/macOS; OS package may be required on Linux)

## Scholarly and educational use

This repository is intended to make the Affordable Spectrometer visible as a reproducible **digital, computational, scientific-instrumentation, and educational research product**. It provides executable source code together with calibration information and example outputs so that the workflow can be inspected, taught, tested, and extended.

## Citation

Citation metadata are supplied in `CITATION.cff`. A DOI can be added later if a GitHub release is archived through a DOI-granting repository such as Zenodo.

## License

No open-source license was specified in the supplied project package. A license has therefore **not** been assigned during repository preparation. The project owner should select an appropriate license before inviting unrestricted reuse or modification.
