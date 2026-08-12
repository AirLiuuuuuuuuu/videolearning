# VideoLearn Demo

Python development project.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

For a CPU-only Windows machine, install the official PyTorch CPU build before
installing the project dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-torch-cpu.txt
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Run the starter program:

```powershell
python -m videolearn_demo
```
